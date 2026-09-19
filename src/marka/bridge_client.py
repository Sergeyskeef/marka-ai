"""Credential-free clients for the pinned bridge. One bounded request per socket."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
from pathlib import Path
import struct

from .media import image_inputs
from .provider import ProviderError
from .telegram import (MAX_ATTACHMENT_BYTES, MAX_DOCUMENT_BYTES, TelegramError,
                       TelegramRetryAfter)
from .voice import STT_TIMEOUT, VoiceError, validate_audio_bytes, validate_transcript

MAX_FRAME = 32 * 1024 * 1024


class BridgeError(ValueError):
    """A protocol failure with no server-provided free-form error text."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pack_bytes(value):
    return base64.b64encode(value).decode("ascii")


def unpack_bytes(value, maximum):
    if not isinstance(value, str) or len(value) > ((maximum + 2) // 3) * 4:
        raise BridgeError("Invalid bridge binary payload")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError):
        raise BridgeError("Invalid bridge binary payload") from None
    if len(result) > maximum:
        raise BridgeError("Invalid bridge binary payload")
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BridgeError("Duplicate bridge field")
        result[key] = value
    return result


async def read_frame(reader):
    length = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 1 <= length <= MAX_FRAME:
        raise BridgeError("Bridge frame exceeds limit")
    try:
        value = json.loads(await reader.readexactly(length), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(BridgeError("Invalid bridge number")))
    except (ValueError, UnicodeError, RecursionError):
        raise BridgeError("Invalid bridge frame") from None
    if not isinstance(value, dict):
        raise BridgeError("Invalid bridge frame")
    return value


async def write_frame(writer, value):
    payload = canonical(value)
    if not 1 <= len(payload) <= MAX_FRAME:
        raise BridgeError("Bridge frame exceeds limit")
    writer.write(struct.pack("!I", len(payload)) + payload)
    await writer.drain()


async def _rpc(socket, request, *, timeout=240):
    if type(timeout) not in {float, int} or not math.isfinite(timeout) or timeout <= 0:
        raise BridgeError("Invalid bridge deadline")
    writer = None
    try:
        async with asyncio.timeout(timeout):
            reader, writer = await asyncio.open_unix_connection(str(socket), limit=65536)
            await write_frame(writer, request)
            response = await read_frame(reader)
            if type(response.get("ok")) is not bool:
                raise BridgeError("Invalid bridge response")
            if response["ok"]:
                if "result" not in response:
                    raise BridgeError("Invalid bridge response")
                return response["result"]
            error = response.get("error")
            if not isinstance(error, dict):
                raise BridgeError("Invalid bridge response")
            return {"__bridge_error__": error}
    except (OSError, TimeoutError, asyncio.IncompleteReadError, ValueError):
        raise BridgeError("Protected bridge unavailable; an effect may be uncertain") from None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, RuntimeError):
                pass


_ERROR_MESSAGES = {
    "denied": "Protected bridge rejected the request",
    "invalid": "Protected bridge received an invalid request",
    "uncertain": "Previous remote request may have completed; automatic retry is blocked",
    "conflict": "Remote receipt identity belongs to a different request",
    "budget": "Protected bridge daily model budget reached",
    "unavailable": "Protected service is unavailable",
    "failed": "Remote service could not complete the request",
}


def _error(value):
    return value.get("__bridge_error__") if isinstance(value, dict) else None


def _message(error):
    return _ERROR_MESSAGES.get(error.get("kind"), _ERROR_MESSAGES["failed"])


def _telegram_error(error):
    retry = error.get("retry_after")
    if type(retry) is int and 1 <= retry <= 86400:
        value = TelegramRetryAfter(retry)
    else:
        code = error.get("code")
        value = TelegramError(_message(error), code=code if type(code) is int else None,
                              permanent=error.get("permanent") is True,
                              uncertain=error.get("uncertain") is True or error.get("kind") == "uncertain")
    ids = error.get("sent_message_ids", [])
    value.sent_message_ids = [item for item in ids if type(item) is int] if isinstance(ids, list) else []
    return value


class BridgeProvider:
    def __init__(self, socket, *, timeout=240):
        self.socket, self.timeout = str(socket), timeout

    async def status(self):
        try:
            result = await _rpc(self.socket, {"op": "provider.status"}, timeout=self.timeout)
        except BridgeError:
            raise ProviderError("Protected provider bridge is unavailable") from None
        if error := _error(result):
            raise ProviderError(_message(error))
        return result

    async def complete(self, prompt, schema, *, images=(), effect_id=None, attempt="0"):
        try:
            pictures = image_inputs(images)
            payload = {"prompt": prompt, "schema": schema,
                       "images": [pack_bytes(picture.data) for picture in pictures]}
            request = {"op": "provider.complete", **payload,
                       "effect_id": effect_id or "payload:" + digest(payload), "attempt": str(attempt)}
            result = await _rpc(self.socket, request, timeout=self.timeout)
        except (BridgeError, ValueError):
            raise ProviderError("Protected provider unavailable; its request may be uncertain") from None
        if error := _error(result):
            raise ProviderError(_message(error))
        return result


class BridgeTelegramClient:
    def __init__(self, socket, *, timeout=40):
        self.socket, self.timeout = str(socket), timeout

    async def _request(self, op, payload, *, effect_id=None, attempt="0", timeout=None):
        request = {"op": op, **payload}
        is_effect = op in {"telegram.send_message", "telegram.send_document"}
        if is_effect:
            request.update(effect_id=effect_id or "payload:" + digest(payload), attempt=str(attempt))
        try:
            result = await _rpc(self.socket, request, timeout=timeout or self.timeout)
        except BridgeError:
            raise TelegramError("Protected Telegram bridge unavailable", uncertain=is_effect) from None
        if error := _error(result):
            raise _telegram_error(error)
        return result

    async def get_me(self):
        return await self._request("telegram.get_me", {})

    async def call(self, method, payload):
        if method != "getWebhookInfo" or payload != {}:
            raise TelegramError("Telegram method is not allowed through the bridge", permanent=True)
        return await self._request("telegram.webhook", {})

    async def get_updates(self, offset, timeout=25):
        return await self._request("telegram.get_updates", {"offset": offset, "timeout": timeout},
                                   timeout=max(self.timeout, timeout + 5) if type(timeout) is int else self.timeout)

    async def download_file(self, file_id, *, max_bytes=MAX_ATTACHMENT_BYTES, expected_size=None,
                            image=False, voice=False):
        result = await self._request("telegram.download", {"file_id": file_id, "max_bytes": max_bytes,
                                      "expected_size": expected_size, "image": image, "voice": voice})
        try:
            return unpack_bytes(result["data"], max_bytes)
        except (KeyError, TypeError, BridgeError):
            raise TelegramError("Protected bridge returned invalid attachment data") from None

    async def send_message(self, chat_id, text, *, effect_id=None, attempt="0"):
        return await self._request("telegram.send_message", {"chat_id": chat_id, "text": text},
                                   effect_id=effect_id, attempt=attempt)

    async def send_document(self, chat_id, path, caption="", *, effect_id=None, attempt="0", content=None):
        try:
            path = Path(path)
            if content is None:
                with path.open("rb") as stream:
                    data = stream.read(MAX_DOCUMENT_BYTES + 1)
            else:
                data = content
            if not isinstance(data, bytes) or len(data) > MAX_DOCUMENT_BYTES:
                raise OSError()
        except (OSError, TypeError, ValueError):
            raise TelegramError("Telegram document must be a file of at most 20 MiB", permanent=True) from None
        return await self._request("telegram.send_document", {"chat_id": chat_id, "caption": caption,
                                   "filename": path.name, "data": pack_bytes(data)},
                                   effect_id=effect_id, attempt=attempt, timeout=max(self.timeout, 120))


async def bridge_transcribe(socket, audio, *, source, attempt, duration, timeout=STT_TIMEOUT):
    digest_audio = validate_audio_bytes(audio)
    try:
        result = await _rpc(socket, {"op": "voice.transcribe", "audio": pack_bytes(audio),
                                    "source": source, "attempt": str(attempt), "duration": duration,
                                    "timeout": timeout}, timeout=timeout + 5)
    except (BridgeError, TypeError, ValueError):
        raise VoiceError("Protected speech bridge unavailable; request may be uncertain") from None
    if error := _error(result):
        raise VoiceError(_message(error))
    return validate_transcript(result, digest_audio)


async def bridge_status(socket):
    result = await _rpc(socket, {"op": "status"}, timeout=40)
    if error := _error(result):
        raise BridgeError(_message(error))
    return result


async def server_read(socket, section, *, offset=0, expected_sha256=""):
    """Read an operator-exported server section; never accept a host path."""
    result = await _rpc(socket, {"op": "server.read", "section": section,
                                "offset": offset, "expected_sha256": expected_sha256}, timeout=40)
    if error := _error(result):
        raise BridgeError(_message(error))
    return result


async def connections_list(socket):
    result = await _rpc(socket, {"op": "connections.list"}, timeout=40)
    if error := _error(result):
        raise BridgeError(_message(error))
    return result


async def connections_check(socket, connection):
    result = await _rpc(socket, {"op": "connections.check", "connection": connection}, timeout=40)
    if error := _error(result):
        raise BridgeError(_message(error))
    return result
