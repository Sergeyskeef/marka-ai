"""Pinned credential bridge and independent, durable owner-input journal.

This service is installed separately from mutable Mark releases. Its journal,
credentials and socket directory must never be writable by the bot UID.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import struct
import tempfile
import time

from .bridge_client import (BridgeError, canonical, digest, pack_bytes, read_frame,
                            unpack_bytes, write_frame)
from .media import MAX_IMAGE_BYTES, image_inputs, validate_image
from .provider import CodexProvider
from .telegram import (MAX_ATTACHMENT_BYTES, MAX_DOCUMENT_BYTES, MAX_IMAGE_DOWNLOAD_BYTES,
                       TelegramClient, TelegramError, TelegramRetryAfter, _message_envelope,
                       parse_attachment, parse_image, parse_message, parse_voice, split_message)
from .voice import MAX_VOICE_BYTES, STT_TIMEOUT, transcribe, validate_audio_bytes


class Rejected(Exception):
    def __init__(self, kind="invalid", **details):
        self.error = {"kind": kind, **details}


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Rejected()
    return value


def _text(value, maximum, *, empty=False):
    if not isinstance(value, str) or (not empty and not value) or len(value.encode("utf-8")) > maximum:
        raise Rejected()
    return value


def _identity(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:@/-]{1,240}", value):
        raise Rejected()
    return value


def _secret(path, maximum=4096):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size > maximum
                    or (os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
                raise ValueError()
            return stream.read(maximum + 1).decode("ascii").strip()
    except (OSError, ValueError, UnicodeError):
        raise BridgeError("Protected credential file is unavailable") from None


class Journal:
    """Canonical bridge state; FULL synchronous WAL commits precede remote ACKs."""
    def __init__(self, path, owner_id, initial_offset=0):
        self.path = Path(path)
        self.owner_id = _integer(owner_id, 1, 2**63 - 1)
        _integer(initial_offset, 0, 2**63 - 1)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise BridgeError("Invalid protected journal path")
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS updates(
                    update_id INTEGER PRIMARY KEY,raw TEXT NOT NULL,owner_id INTEGER NOT NULL,
                    control TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS files(
                    file_id TEXT NOT NULL,update_id INTEGER NOT NULL,kind TEXT NOT NULL,
                    PRIMARY KEY(file_id,update_id,kind));
                CREATE TABLE IF NOT EXISTS downloads(
                    file_id TEXT NOT NULL,sha256 TEXT NOT NULL,kind TEXT NOT NULL,
                    PRIMARY KEY(file_id,sha256,kind));
                CREATE TABLE IF NOT EXISTS effects(
                    scope TEXT NOT NULL,effect_id TEXT NOT NULL,attempt TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,state TEXT NOT NULL,result TEXT,error TEXT,
                    created REAL NOT NULL,updated REAL NOT NULL,
                    PRIMARY KEY(scope,effect_id,attempt));
                CREATE INDEX IF NOT EXISTS effects_budget ON effects(created,scope);
                CREATE TABLE IF NOT EXISTS retry_authorizations(
                    update_id INTEGER PRIMARY KEY,scope TEXT NOT NULL,effect_id TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO metadata VALUES('next_offset',?)", (str(initial_offset),))
            db.execute("INSERT OR IGNORE INTO metadata VALUES('owner_id',?)", (str(owner_id),))
            if db.execute("SELECT value FROM metadata WHERE key='owner_id'").fetchone()[0] != str(owner_id):
                raise BridgeError("Protected journal belongs to a different owner")
        self.path.chmod(0o600)

    def recover_pending(self):
        """Run only after the bridge holds its exclusive process lock."""
        with self.connect() as db:
            db.execute("UPDATE effects SET state='uncertain',error=?,updated=? WHERE state='pending'",
                       (json.dumps({"kind": "uncertain", "uncertain": True}), time.time()))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=10000")
            with db:
                yield db
        finally:
            db.close()

    @property
    def offset(self):
        with self.connect() as db:
            return int(db.execute("SELECT value FROM metadata WHERE key='next_offset'").fetchone()[0])

    def ingest(self, values):
        if not isinstance(values, list) or len(values) > 100:
            raise Rejected()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            offset = int(db.execute("SELECT value FROM metadata WHERE key='next_offset'").fetchone()[0])
            for update in values:
                if not isinstance(update, dict):
                    raise Rejected()
                identifier = _integer(update.get("update_id"), 0, 2**63 - 2)
                offset = max(offset, identifier + 1)
                envelope = _message_envelope(update)
                if envelope is None:
                    continue
                raw, sender, chat = envelope
                if sender["id"] != self.owner_id or chat["id"] != self.owner_id or chat["type"] != "private":
                    continue
                command = raw.get("text", "").strip().split(maxsplit=1)[0] if isinstance(raw.get("text"), str) and raw["text"].strip() else ""
                command = command.split("@", 1)[0].lower()
                control = command[1:] if command in {"/rescue", "/rollback"} else ""
                encoded = canonical(update).decode()
                if len(encoded.encode()) > 2 * 1024 * 1024:
                    raise Rejected()
                previous = db.execute("SELECT raw FROM updates WHERE update_id=?", (identifier,)).fetchone()
                if previous is not None and previous[0] != encoded:
                    raise Rejected("conflict")
                db.execute("INSERT OR IGNORE INTO updates VALUES(?,?,?,?,?)",
                           (identifier, encoded, self.owner_id, control, time.time()))
                for parser, kind in ((parse_attachment, "document"), (parse_image, "image"), (parse_voice, "voice")):
                    attachment = parser(update)
                    if attachment is not None:
                        db.execute("INSERT OR IGNORE INTO files VALUES(?,?,?)", (attachment.file_id, identifier, kind))
            db.execute("UPDATE metadata SET value=? WHERE key='next_offset'", (str(offset),))

    def updates(self, offset):
        with self.connect() as db:
            rows = db.execute("SELECT raw FROM updates WHERE update_id>=? AND control='' ORDER BY update_id LIMIT 100",
                              (offset,)).fetchall()
        results, total = [], 0
        for row in rows:
            size = len(row[0].encode())
            if total + size > 8 * 1024 * 1024:
                break
            results.append(json.loads(row[0]))
            total += size
        return results

    def owns_file(self, identifier, kind):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM files JOIN updates USING(update_id) WHERE file_id=? AND kind=? "
                              "AND owner_id=? AND control='' LIMIT 1", (identifier, kind, self.owner_id)).fetchone() is not None

    def downloaded(self, identifier, kind, data):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO downloads VALUES(?,?,?)",
                       (identifier, hashlib.sha256(data).hexdigest(), kind))

    def owns_audio(self, source, data):
        if not isinstance(source, str) or not re.fullmatch(r"telegram:[0-9]{1,19}", source):
            return False
        identifier = int(source.split(":")[1])
        if identifier >= 2**63:
            return False
        with self.connect() as db:
            return db.execute("SELECT 1 FROM files JOIN updates USING(update_id) JOIN downloads USING(file_id,kind) "
                              "WHERE update_id=? AND owner_id=? AND control='' AND kind='voice' AND sha256=? LIMIT 1",
                              (identifier, self.owner_id, hashlib.sha256(data).hexdigest())).fetchone() is not None

    def begin(self, scope, effect_id, attempt, payload_hash, daily_calls):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM effects WHERE scope=? AND effect_id=? ORDER BY created",
                              (scope, effect_id)).fetchall()
            for row in rows:
                if row["payload_hash"] != payload_hash:
                    raise Rejected("conflict")
            for row in rows:
                if row["state"] == "done":
                    return True, json.loads(row["result"])
            previous = next((row for row in rows if row["attempt"] == attempt), None)
            if previous is not None:
                row = previous
                if row["state"] == "failed":
                    error = json.loads(row["error"])
                    retry_after = error.get("retry_after")
                    if scope.startswith("telegram.") and type(retry_after) is int and not error.get("uncertain"):
                        remaining = math.ceil(row["updated"] + retry_after - now)
                        if remaining <= 0:
                            # A definite 429 without partial sends performed no
                            # remote effect; the normal delivery queue may retry.
                            db.execute("UPDATE effects SET state='pending',error=NULL,updated=? WHERE scope=? AND effect_id=? AND attempt=?",
                                       (now, scope, effect_id, attempt))
                            return False, None
                        error["retry_after"] = remaining
                    raise Rejected(**error)
                if row["state"] == "uncertain" and row["error"]:
                    raise Rejected(**json.loads(row["error"]))
                raise Rejected("uncertain", uncertain=True)
            if rows:
                # Changing a lease/string cannot authorize another paid effect.
                # Only a fresh original owner resume/extend message is a retry proof.
                match = re.fullmatch(r"owner-([0-9]{1,19})", attempt)
                if match is None or int(match[1]) >= 2**63:
                    raise Rejected("uncertain", uncertain=True)
                owner_update = db.execute("SELECT raw,created FROM updates WHERE update_id=? AND owner_id=? AND control=''",
                                          (int(match[1]), self.owner_id)).fetchone()
                if owner_update is None or owner_update["created"] < rows[-1]["created"]:
                    raise Rejected("uncertain", uncertain=True)
                message = parse_message(json.loads(owner_update["raw"]))
                words = message.text.split() if message else []
                if len(words) < 2 or words[0].split("@", 1)[0].lower() not in {"/resume", "/extend"}:
                    raise Rejected("uncertain", uncertain=True)
                claimed = db.execute("SELECT scope,effect_id FROM retry_authorizations WHERE update_id=?", (int(match[1]),)).fetchone()
                if claimed is not None and (claimed["scope"], claimed["effect_id"]) != (scope, effect_id):
                    raise Rejected("uncertain", uncertain=True)
                db.execute("INSERT OR IGNORE INTO retry_authorizations VALUES(?,?,?)", (int(match[1]), scope, effect_id))
            if scope in {"provider", "voice"}:
                count = db.execute("SELECT COUNT(*) FROM effects WHERE scope=? AND created>=?",
                                   (scope, int(now // 86400) * 86400)).fetchone()[0]
                if count >= daily_calls:
                    raise Rejected("budget")
            db.execute("INSERT INTO effects VALUES(?,?,?,?, 'pending',NULL,NULL,?,?)",
                       (scope, effect_id, attempt, payload_hash, now, now))
        return False, None

    def finish(self, scope, effect_id, attempt, *, result=None, error=None):
        state = "done" if error is None else "uncertain" if error.get("uncertain") else "failed"
        with self.connect() as db:
            db.execute("UPDATE effects SET state=?,result=?,error=?,updated=? WHERE scope=? AND effect_id=? AND attempt=?",
                       (state, canonical(result).decode() if error is None else None,
                        canonical(error).decode() if error is not None else None, time.time(), scope, effect_id, attempt))

    def status(self):
        with self.connect() as db:
            return {"journal_updates": db.execute("SELECT COUNT(*) FROM updates").fetchone()[0],
                    "uncertain_effects": db.execute("SELECT COUNT(*) FROM effects WHERE state IN ('pending','uncertain')").fetchone()[0],
                    "pending_controls": db.execute("SELECT COUNT(*) FROM updates WHERE control<>''").fetchone()[0]}


def _safe_error(exc, *, effect=False):
    if isinstance(exc, Rejected):
        return exc.error
    if isinstance(exc, TelegramError):
        uncertain = exc.uncertain or bool(exc.sent_message_ids)
        result = {"kind": "uncertain" if uncertain else "failed", "code": exc.code,
                  "permanent": exc.permanent, "uncertain": uncertain,
                  "sent_message_ids": list(exc.sent_message_ids)}
        if isinstance(exc, TelegramRetryAfter) and not uncertain:
            result["retry_after"] = exc.seconds
        return result
    return {"kind": "uncertain" if effect else "unavailable", "uncertain": effect}


class Bridge:
    def __init__(self, config, *, telegram=None, provider=None, speech=transcribe):
        required = {"socket", "journal", "owner_id", "token_file", "codex_home", "voice_key_file",
                    "model", "daily_calls", "provider_timeout", "initial_offset"}
        if not isinstance(config, dict) or set(config) != required:
            raise BridgeError("Invalid protected bridge configuration")
        self.config = config
        self.owner_id = _integer(config["owner_id"], 1, 2**63 - 1)
        self.daily_calls = _integer(config["daily_calls"], 1, 10000)
        provider_timeout = config["provider_timeout"]
        if type(provider_timeout) not in {int, float} or not math.isfinite(provider_timeout) or not 1 <= provider_timeout <= 600:
            raise BridgeError("Invalid protected provider deadline")
        for name in ("socket", "journal", "token_file", "codex_home", "voice_key_file"):
            if not isinstance(config[name], str) or not config[name] or not Path(config[name]).is_absolute():
                raise BridgeError("Invalid protected bridge configuration")
        if config["model"] is not None and (not isinstance(config["model"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", config["model"])):
            raise BridgeError("Invalid protected bridge model")
        self.journal = Journal(config["journal"], self.owner_id, config["initial_offset"])
        self.telegram = telegram or TelegramClient(_secret(config["token_file"]))
        self.provider = provider or CodexProvider(home=Path(config["codex_home"]), model=config["model"], timeout=provider_timeout)
        self.speech = speech
        self.changed = asyncio.Event()
        self.poll_ready = False
        self.poll_error = False
        self.last_poll = 0.0
        self.provider_info = {"authenticated": None, "auth_method": "unverified", "version": None}
        # Four bounded frames can coexist; reject excess sockets before they
        # form an unbounded queue of buffers while a damaged client reconnects.
        self._slots = asyncio.Semaphore(4)
        self._connections = 0
        self._serving = False

    async def poll_once(self):
        values = await self.telegram.get_updates(self.journal.offset, timeout=25)
        self.journal.ingest(values)
        self.last_poll, self.poll_ready, self.poll_error = time.time(), True, False
        if values:
            self.changed.set()

    async def poll(self):
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.poll_error = True
                await asyncio.sleep(3)

    def _fields(self, request, names):
        if set(request) != {"op", *names}:
            raise Rejected()

    async def _effect(self, scope, request, payload, operation):
        effect_id = _identity(request["effect_id"])
        attempt = _identity(request["attempt"])
        replay, result = self.journal.begin(scope, effect_id, attempt, digest(payload), self.daily_calls)
        if replay:
            return result
        try:
            result = await operation()
            self.journal.finish(scope, effect_id, attempt, result=result)
            return result
        except BaseException as exc:
            error = _safe_error(exc, effect=True)
            self.journal.finish(scope, effect_id, attempt, error=error)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise Rejected(**error) from None

    async def dispatch(self, request):
        try:
            return {"ok": True, "result": await self._dispatch(request)}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {"ok": False, "error": _safe_error(exc)}

    async def _dispatch(self, request):
        if not isinstance(request, dict):
            raise Rejected()
        op = request.get("op")
        if op == "status":
            self._fields(request, [])
            return {"ready": self.poll_ready and not self.poll_error, "poll_ready": self.poll_ready,
                    "telegram_available": self.poll_ready and not self.poll_error,
                    "poll_error": self.poll_error, "last_poll": self.last_poll,
                    "voice_available": Path(self.config["voice_key_file"]).is_file(),
                    "model_requested": self.config["model"], "model_resolved": None,
                    "provider": self.provider_info, "daily_model_limit": self.daily_calls,
                    "daily_voice_limit": self.daily_calls, **self.journal.status()}
        if op == "provider.status":
            self._fields(request, [])
            value = await self.provider.status()
            self.provider_info = {"authenticated": value.get("authenticated") is True,
                                  "auth_method": "chatgpt" if value.get("auth_method") == "chatgpt" else "unavailable",
                                  "version": value.get("version") if isinstance(value.get("version"), str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", value["version"]) else None}
            return {**self.provider_info, "model_requested": self.config["model"], "model_resolved": None}
        if op in {"telegram.get_me", "telegram.webhook"}:
            self._fields(request, [])
            if op == "telegram.get_me":
                value = await self.telegram.get_me()
                return {key: value[key] for key in ("id", "is_bot", "first_name", "username") if key in value}
            value = await self.telegram.call("getWebhookInfo", {})
            # Do not return a potentially credential-bearing webhook URL.
            return {"url": "configured" if value.get("url") else "", "pending_update_count": value.get("pending_update_count", 0)}
        if op == "telegram.get_updates":
            self._fields(request, ["offset", "timeout"])
            offset = _integer(request["offset"], 0, 2**63 - 1)
            timeout = _integer(request["timeout"], 0, 50)
            self.changed.clear()
            values = self.journal.updates(offset)
            if not values and timeout:
                try:
                    await asyncio.wait_for(self.changed.wait(), timeout)
                except TimeoutError:
                    pass
                values = self.journal.updates(offset)
            return values
        if op == "telegram.download":
            self._fields(request, ["file_id", "max_bytes", "expected_size", "image", "voice"])
            identifier = request["file_id"]
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", identifier):
                raise Rejected()
            image, voice = request["image"], request["voice"]
            if type(image) is not bool or type(voice) is not bool or image and voice:
                raise Rejected()
            kind = "voice" if voice else "image" if image else "document"
            maximum = _integer(request["max_bytes"], 1, MAX_IMAGE_DOWNLOAD_BYTES if image or voice else MAX_ATTACHMENT_BYTES)
            expected = request["expected_size"]
            if expected is not None:
                _integer(expected, 0, maximum)
            if not self.journal.owns_file(identifier, kind):
                raise Rejected("denied", permanent=True)
            value = await self.telegram.download_file(identifier, max_bytes=maximum, expected_size=expected, image=image, voice=voice)
            if not isinstance(value, bytes) or len(value) > maximum:
                raise Rejected()
            self.journal.downloaded(identifier, kind, value)
            return {"data": pack_bytes(value)}
        if op == "provider.complete":
            self._fields(request, ["prompt", "schema", "images", "effect_id", "attempt"])
            prompt = _text(request["prompt"], 1024 * 1024)
            schema = request["schema"]
            if not isinstance(schema, dict) or schema.get("type") != "object" or len(canonical(schema)) > 262144:
                raise Rejected()
            if not isinstance(request["images"], list) or len(request["images"]) > 2:
                raise Rejected()
            pictures = image_inputs([validate_image(unpack_bytes(value, MAX_IMAGE_BYTES)) for value in request["images"]])
            payload = {"prompt": prompt, "schema": schema, "images": [picture.sha256 for picture in pictures]}
            return await self._effect("provider", request, payload,
                                      lambda: self.provider.complete(prompt, schema, images=pictures))
        if op == "voice.transcribe":
            self._fields(request, ["audio", "source", "attempt", "duration", "timeout"])
            audio = unpack_bytes(request["audio"], MAX_VOICE_BYTES)
            audio_hash = validate_audio_bytes(audio)
            duration = _integer(request["duration"], 1, 60)
            timeout = request["timeout"]
            if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= STT_TIMEOUT:
                raise Rejected()
            if not self.journal.owns_audio(request["source"], audio):
                raise Rejected("denied")
            identity = {"effect_id": request["source"], "attempt": request["attempt"]}
            payload = {"sha256": audio_hash, "duration": duration}
            return await self._effect("voice", identity, payload, lambda: self.speech(
                Path(self.config["voice_key_file"]), audio, duration=duration, timeout=timeout))
        if op in {"telegram.send_message", "telegram.send_document"}:
            names = ["chat_id", "effect_id", "attempt"] + (["text"] if op.endswith("send_message") else ["filename", "data", "caption"])
            self._fields(request, names)
            if type(request["chat_id"]) is not int or request["chat_id"] != self.owner_id:
                raise Rejected("denied", permanent=True)
            if op.endswith("send_message"):
                text = _text(request["text"], 262144)
                split_message(text)
                return await self._effect("telegram.message", request, {"chat_id": self.owner_id, "text": text},
                                          lambda: self.telegram.send_message(self.owner_id, text))
            caption = _text(request["caption"], 4096, empty=True)
            if len(caption.encode("utf-16-le")) // 2 > 1024:
                raise Rejected()
            filename = _text(request["filename"], 1024)
            # Only a filename is accepted. No RPC value is ever opened as a path.
            filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:180] or "document.bin"
            if filename in {".", ".."}:
                filename = "document.bin"
            data = unpack_bytes(request["data"], MAX_DOCUMENT_BYTES)
            payload = {"chat_id": self.owner_id, "filename": filename, "caption": caption,
                       "sha256": hashlib.sha256(data).hexdigest()}

            async def send():
                with tempfile.TemporaryDirectory(prefix="marka-bridge-document-") as temporary:
                    path = Path(temporary) / filename
                    path.write_bytes(data)
                    path.chmod(0o600)
                    return await self.telegram.send_document(self.owner_id, path, caption=caption)
            return await self._effect("telegram.document", request, payload, send)
        raise Rejected("denied", permanent=True)

    async def handle(self, reader, writer):
        if self._connections >= 8:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, RuntimeError):
                pass
            return
        self._connections += 1
        operation = disconnected = None
        try:
            peer = writer.get_extra_info("socket")
            if peer is not None and hasattr(socket, "SO_PEERCRED"):
                _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid not in {0, 10001, 10002}:
                    raise Rejected("denied")
            async with self._slots:
                request = await asyncio.wait_for(read_frame(reader), 15)
                operation = asyncio.create_task(self.dispatch(request))
                # A closed client cancels official CLI/STT child processes. Blocking
                # Telegram HTTP work may finish later; its durable receipt is uncertain.
                disconnected = asyncio.create_task(reader.read(1))
                done, _ = await asyncio.wait((operation, disconnected), return_when=asyncio.FIRST_COMPLETED)
                if operation in done:
                    response = operation.result()
                    await asyncio.wait_for(write_frame(writer, response), 30)
                else:
                    operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
        except (Exception, asyncio.CancelledError):
            if operation is not None and not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
        finally:
            self._connections -= 1
            if disconnected is not None:
                disconnected.cancel()
                await asyncio.gather(disconnected, return_exceptions=True)
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, RuntimeError):
                pass

    async def serve(self):
        if os.name == "nt" or os.getuid() != 10002:
            raise BridgeError("Protected bridge requires its dedicated service UID")
        import fcntl
        path = Path(self.config["socket"])
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 10002 or info.st_gid != 10001 or stat.S_IMODE(info.st_mode) != 0o750:
            raise BridgeError("Protected socket directory permissions are invalid")
        journal_info = self.journal.path.parent.lstat()
        if (not stat.S_ISDIR(journal_info.st_mode) or journal_info.st_uid != 10002
                or stat.S_IMODE(journal_info.st_mode) != 0o700):
            raise BridgeError("Protected journal directory permissions are invalid")
        lock_path = self.journal.path.with_suffix(".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.journal.recover_pending()
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 10002:
                    raise BridgeError("Invalid protected socket")
                path.unlink()
            server = await asyncio.start_unix_server(self.handle, path=str(path), limit=65536)
            os.chmod(path, 0o660)
            os.chown(path, 10002, 10001)
            poller = asyncio.create_task(self.poll())
            self._serving = True
            try:
                async with server:
                    await server.serve_forever()
            finally:
                self._serving = False
                poller.cancel()
                await asyncio.gather(poller, return_exceptions=True)
                path.unlink(missing_ok=True)
        finally:
            os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description="Run the protected Mark credential bridge")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        os.umask(0o077)
        info = args.config.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise BridgeError("Invalid protected bridge configuration")
        if os.name != "nt" and (info.st_uid != 0 or info.st_mode & 0o022):
            raise BridgeError("Bridge configuration must be root-owned and read-only")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        asyncio.run(Bridge(config).serve())
    except KeyboardInterrupt:
        pass
    except Exception:
        # A raw exception could contain a credential filename, Telegram URL or key.
        print("Protected bridge stopped; inspect configuration and protected journal")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
