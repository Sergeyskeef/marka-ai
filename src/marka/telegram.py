"""Small Telegram Bot API transport; delivery uncertainty stays explicit.

No automatic retries: a timed-out send may already have reached Telegram.
See https://core.telegram.org/bots/api for the protocol.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import secrets
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request


MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MESSAGE_UNITS = 3500
_READ_METHODS = frozenset({"getMe", "getUpdates", "getWebhookInfo", "getFile"})
TEXT_ATTACHMENT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".log", ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".xml", ".sql", ".sh", ".ps1", ".go", ".rs", ".java", ".c", ".h", ".cpp",
})


class TelegramError(RuntimeError):
    """Safe error text suitable for logs; never contains the API URL or token."""

    def __init__(self, message: str, *, code: int | None = None,
                 permanent: bool = False, uncertain: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.permanent = permanent
        self.uncertain = uncertain
        self.sent_message_ids: list[int] = []


class TelegramRetryAfter(TelegramError):
    def __init__(self, seconds: int) -> None:
        self.seconds = max(1, int(seconds))
        super().__init__(f"Telegram rate limit; retry after {self.seconds}s", code=429)


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: bytes


@dataclass(frozen=True, slots=True)
class Message:
    update_id: int
    chat_id: int
    user_id: int
    text: str
    private: bool


@dataclass(frozen=True, slots=True)
class Attachment:
    update_id: int
    chat_id: int
    user_id: int
    file_id: str
    file_unique_id: str
    file_name: str
    mime_type: str
    file_size: int | None
    caption: str
    private: bool


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def valid_private_message(message: Message | Attachment) -> bool:
    """Telegram private conversation IDs must match the authenticated sender."""
    return message.private and message.user_id > 0 and message.chat_id == message.user_id


def _message_envelope(update):
    if not isinstance(update, dict) or not _is_int(update.get("update_id")):
        return None
    if update["update_id"] < 0:
        return None
    if any(key in update for key in ("edited_message", "channel_post", "edited_channel_post")):
        return None
    raw = update.get("message")
    if not isinstance(raw, dict):
        return None
    if any(key in raw for key in (
        "forward_origin", "forward_date", "forward_from", "forward_from_chat",
        "forward_sender_name", "sender_chat", "via_bot",
    )) or raw.get("is_automatic_forward"):
        return None
    sender, chat = raw.get("from"), raw.get("chat")
    if not isinstance(sender, dict) or not isinstance(chat, dict):
        return None
    if sender.get("is_bot") is not False or not isinstance(chat.get("type"), str) or chat.get("type") not in {"private", "group", "supergroup"}:
        return None
    if not _is_int(sender.get("id")) or sender["id"] <= 0 or not _is_int(chat.get("id")):
        return None
    return raw, sender, chat


def parse_message(update: Any) -> Message | None:
    """Accept original human text messages, never forwarded or edited updates."""
    envelope = _message_envelope(update)
    if envelope is None:
        return None
    raw, sender, chat = envelope
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return Message(update["update_id"], chat["id"], sender["id"], text,
                   chat.get("type") == "private")


def parse_attachment(update: Any) -> Attachment | None:
    """Parse metadata only. The app must verify its paired owner before download."""
    envelope = _message_envelope(update)
    if envelope is None:
        return None
    raw, sender, chat = envelope
    if chat.get("type") != "private" or chat["id"] != sender["id"]:
        return None
    document = raw.get("document")
    if not isinstance(document, dict):
        return None
    identifier, unique = document.get("file_id"), document.get("file_unique_id", "")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", identifier):
        return None
    if not isinstance(unique, str) or (unique and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", unique)):
        return None
    size = document.get("file_size")
    if size is not None and (not _is_int(size) or size < 0 or size > 2**52):
        return None
    name, mime, caption = document.get("file_name", "attachment.bin"), document.get("mime_type", ""), raw.get("caption", "")
    if (not isinstance(name, str) or not 1 <= len(name) <= 255 or not isinstance(mime, str) or len(mime) > 200
            or not isinstance(caption, str) or len(caption) > 4096
            or any(0xD800 <= ord(c) <= 0xDFFF for c in name + mime + caption)):
        return None
    # Never let sender-supplied filenames become paths or HTTP headers. The app
    # still prefixes a unique update ID before persisting into the workspace.
    name = re.sub(r'[\\/:<>"|?*\x00-\x1f\x7f]', "_", name).strip(". ") or "attachment.bin"
    return Attachment(update["update_id"], chat["id"], sender["id"], identifier, unique,
                      name, mime, size, caption, True)


def attachment_problem(attachment: Attachment) -> str | None:
    if not isinstance(attachment, Attachment) or not valid_private_message(attachment):
        return "Attachment requires the owner's private conversation"
    if attachment.file_size is not None and attachment.file_size > MAX_ATTACHMENT_BYTES:
        return "Attachment exceeds the 512 KiB limit"
    if Path(attachment.file_name).suffix.lower() not in TEXT_ATTACHMENT_EXTENSIONS:
        return "Supported attachments are UTF-8 text, Markdown, CSV, JSON and source-code files; PDF, images and audio are not supported"
    return None


def decode_text_attachment(attachment: Attachment, data: bytes) -> str:
    """Decode data only; a source-code attachment is never executed on receipt."""
    problem = attachment_problem(attachment)
    if problem:
        raise TelegramError(problem, permanent=True)
    if not isinstance(data, bytes) or len(data) > MAX_ATTACHMENT_BYTES:
        raise TelegramError("Attachment exceeds the 512 KiB limit", permanent=True)
    if attachment.file_size is not None and len(data) != attachment.file_size:
        raise TelegramError("Attachment size did not match its metadata", permanent=True)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise TelegramError("Attachment must use UTF-8 text encoding", permanent=True) from None
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text) or "\x7f" in text:
        raise TelegramError("Attachment contains binary or unsupported control characters", permanent=True)
    return text


def split_message(text: str, limit: int = MESSAGE_UNITS) -> list[str]:
    """Split without losing text and count Telegram's UTF-16 entity units."""
    if not isinstance(text, str) or not text:
        raise TelegramError("Telegram message is empty", permanent=True)
    if not _is_int(limit) or limit < 2 or limit > MESSAGE_UNITS:
        raise ValueError("Message chunk limit must be between 2 and 3500")
    chunks: list[str] = []
    start = units = 0
    for index, char in enumerate(text):
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise TelegramError("Telegram text contains invalid Unicode", permanent=True)
        size = 2 if codepoint > 0xFFFF else 1
        if units + size > limit:
            chunks.append(text[start:index])
            start, units = index, 0
        units += size
    chunks.append(text[start:])
    return chunks


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        # A redirect must never carry the bot token to another destination.
        return None


def _http_request(request: urllib.request.Request, timeout: float) -> HTTPResponse:
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        limit = getattr(request, "_marka_response_limit", MAX_RESPONSE_BYTES)
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("Telegram response exceeds size limit")
        return HTTPResponse(response.code, body)


class TelegramClient:
    def __init__(self, token: str, api_base: str = "https://api.telegram.org",
                 timeout: float = 35, *,
                 transport: Callable[[urllib.request.Request, float], HTTPResponse] | None = None) -> None:
        if not isinstance(token, str) or not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token):
            raise TelegramError("Telegram bot token has an invalid format", permanent=True)
        parsed = urllib.parse.urlsplit(api_base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise TelegramError("Telegram API base must be an HTTPS origin", permanent=True)
        if parsed.path not in {"", "/"}:
            raise TelegramError("Telegram API base must not include a path", permanent=True)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Telegram timeout must be positive")
        self._token = token
        self._base = api_base.rstrip("/")
        self._timeout = timeout
        self._transport = transport or _http_request

    async def _request(self, method: str, body: bytes, content_type: str,
                       *, timeout: float | None = None) -> Any:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", method):
            raise TelegramError("Invalid Telegram API method", permanent=True)
        uncertain = method not in _READ_METHODS
        request = urllib.request.Request(
            f"{self._base}/bot{self._token}/{method}", data=body,
            headers={"Content-Type": content_type, "User-Agent": "marka-ai/telegram"},
            method="POST",
        )
        try:
            response = await asyncio.to_thread(self._transport, request, timeout or self._timeout)
        except Exception:
            # Network exception strings may contain credentials from the URL.
            raise TelegramError("Telegram connection failed; delivery may be uncertain" if uncertain
                                else "Telegram connection failed", uncertain=uncertain) from None
        try:
            data = json.loads(response.body)
        except (ValueError, UnicodeError):
            raise TelegramError("Telegram returned an invalid response", code=response.status,
                                uncertain=uncertain) from None
        if not isinstance(data, dict):
            raise TelegramError("Telegram returned an invalid response", code=response.status,
                                uncertain=uncertain)
        if response.status == 200 and data.get("ok") is True and "result" in data:
            return data["result"]
        error_code = data.get("error_code", response.status)
        if not _is_int(error_code):
            error_code = response.status
        if error_code == 429:
            parameters = data.get("parameters")
            seconds = parameters.get("retry_after", 1) if isinstance(parameters, dict) else 1
            raise TelegramRetryAfter(seconds if _is_int(seconds) and seconds > 0 else 1)
        safe_messages = {
            400: "Telegram rejected the request",
            401: "Telegram authentication failed; check the bot token",
            403: "Telegram access forbidden; check the bot's chat access",
            404: "Telegram API endpoint was not found",
            409: "Telegram polling conflict; check another poller or an active webhook",
        }
        raise TelegramError(safe_messages.get(error_code, "Telegram API request failed"),
                            code=error_code, permanent=400 <= error_code < 500,
                            uncertain=uncertain and error_code >= 500)

    async def call(self, method: str, payload: dict[str, Any]) -> Any:
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            raise TelegramError("Invalid Telegram request payload", permanent=True) from None
        return await self._request(method, body, "application/json")

    async def get_me(self) -> dict[str, Any]:
        result = await self.call("getMe", {})
        if not isinstance(result, dict) or not _is_int(result.get("id")) or result.get("is_bot") is not True:
            raise TelegramError("Telegram returned an invalid bot identity")
        return result

    async def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        if not _is_int(offset) or offset < 0 or not _is_int(timeout) or not 0 <= timeout <= 50:
            raise TelegramError("Invalid Telegram polling parameters", permanent=True)
        body = json.dumps({"offset": offset, "timeout": timeout, "limit": 100,
                           "allowed_updates": ["message"]}).encode("utf-8")
        result = await self._request("getUpdates", body, "application/json",
                                     timeout=max(self._timeout, timeout + 5))
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise TelegramError("Telegram returned invalid updates")
        return result

    async def download_file(self, file_id: str, *, max_bytes=MAX_ATTACHMENT_BYTES, expected_size=None) -> bytes:
        """Download a bounded original file from Telegram, after owner validation.

        The file URL follows the official getFile contract. No redirect or
        custom API origin is accepted for downloads containing the bot token.
        """
        if (not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", file_id)
                or not _is_int(max_bytes) or not 1 <= max_bytes <= MAX_ATTACHMENT_BYTES):
            raise TelegramError("Invalid Telegram attachment request", permanent=True)
        if expected_size is not None and (not _is_int(expected_size) or not 0 <= expected_size <= max_bytes):
            raise TelegramError("Attachment exceeds the download limit", permanent=True)
        if self._base != "https://api.telegram.org":
            raise TelegramError("Attachment downloads require the official Telegram HTTPS origin", permanent=True)
        metadata = await self.call("getFile", {"file_id": file_id})
        if not isinstance(metadata, dict) or metadata.get("file_id") != file_id:
            raise TelegramError("Telegram returned invalid attachment metadata")
        size = metadata.get("file_size")
        if size is not None and (not _is_int(size) or not 0 <= size <= max_bytes):
            raise TelegramError("Attachment exceeds the download limit", permanent=True)
        if size is not None and expected_size is not None and size != expected_size:
            raise TelegramError("Attachment metadata size changed", permanent=True)
        path = metadata.get("file_path")
        if (not isinstance(path, str) or not 1 <= len(path) <= 1024
                or not re.fullmatch(r"[A-Za-z0-9_.\-/]+", path)
                or any(part in {"", ".", ".."} or part.startswith(".") for part in path.split("/"))):
            raise TelegramError("Telegram returned an unsafe attachment path", permanent=True)
        request = urllib.request.Request(
            f"https://api.telegram.org/file/bot{self._token}/{path}",
            headers={"User-Agent": "marka-ai/telegram", "Accept-Encoding": "identity"}, method="GET")
        request._marka_response_limit = max_bytes
        try:
            response = await asyncio.to_thread(self._transport, request, self._timeout)
        except Exception:
            raise TelegramError("Telegram attachment download failed") from None
        if not isinstance(response, HTTPResponse) or not isinstance(response.body, bytes):
            raise TelegramError("Telegram returned an invalid attachment response")
        if response.status != 200:
            raise TelegramError("Telegram attachment download failed", code=response.status,
                                permanent=400 <= response.status < 500)
        data = response.body
        if len(data) > max_bytes:
            raise TelegramError("Attachment exceeds the download limit", permanent=True)
        declared = expected_size if expected_size is not None else size
        if declared is not None and len(data) != declared:
            raise TelegramError("Attachment download was incomplete or changed")
        return data

    async def send_message(self, chat_id: int, text: str) -> list[int]:
        if not _is_int(chat_id):
            raise TelegramError("Invalid Telegram chat ID", permanent=True)
        sent: list[int] = []
        for chunk in split_message(text):
            try:
                result = await self.call("sendMessage", {
                    "chat_id": chat_id, "text": chunk,
                    "link_preview_options": {"is_disabled": True},
                })
            except TelegramError as error:
                # A partial multi-message send must not be blindly replayed.
                error.sent_message_ids = list(sent)
                raise
            if not isinstance(result, dict) or not _is_int(result.get("message_id")):
                error = TelegramError("Telegram returned an invalid send receipt", uncertain=True)
                error.sent_message_ids = list(sent)
                raise error
            sent.append(result["message_id"])
        return sent

    async def send_document(self, chat_id: int, path: Path, caption: str = "") -> int:
        if not _is_int(chat_id):
            raise TelegramError("Invalid Telegram chat ID", permanent=True)
        try:
            caption_units = len(caption.encode("utf-16-le")) // 2 if isinstance(caption, str) else 1025
        except UnicodeError:
            raise TelegramError("Telegram document caption contains invalid Unicode", permanent=True) from None
        if caption_units > 1024:
            raise TelegramError("Telegram document caption exceeds 1024 UTF-16 units", permanent=True)
        path = Path(path)
        try:
            if not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
                raise TelegramError("Telegram document must be a file of at most 20 MiB", permanent=True)
            with path.open("rb") as source:
                content = source.read(MAX_DOCUMENT_BYTES + 1)
        except TelegramError:
            raise
        except OSError:
            raise TelegramError("Telegram document could not be read", permanent=True) from None
        if len(content) > MAX_DOCUMENT_BYTES:
            raise TelegramError("Telegram document exceeds 20 MiB", permanent=True)
        boundary = "marka-" + secrets.token_hex(24)
        # ASCII fallback prevents path/header injection while preserving the extension.
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", path.name)[:180] or "document.bin"
        fields = bytearray()
        for name, value in (("chat_id", str(chat_id)), ("caption", caption)):
            fields.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            fields.extend(value.encode("utf-8"))
            fields.extend(b"\r\n")
        fields.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
        fields.extend(content)
        fields.extend(f"\r\n--{boundary}--\r\n".encode())
        result = await self._request("sendDocument", bytes(fields), f"multipart/form-data; boundary={boundary}")
        if not isinstance(result, dict) or not _is_int(result.get("message_id")):
            raise TelegramError("Telegram returned an invalid document receipt", uncertain=True)
        return result["message_id"]
