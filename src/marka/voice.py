"""Private voice receipts and an OpenAI transcription client. Transcripts are derived data."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from .redact import redact

MAX_VOICE_BYTES = 2 * 1024 * 1024
MAX_VOICE_SECONDS = 60
MAX_TRANSCRIPT_CHARS = 6000
MAX_RESPONSE_BYTES = 48000
STT_TIMEOUT = 125


class VoiceError(ValueError):
    """Safe user-facing errors, without audio, model paths or raw codec output."""


def validate_audio_bytes(data):
    if not isinstance(data, bytes) or not 64 <= len(data) <= MAX_VOICE_BYTES:
        raise VoiceError("Голосовое должно быть файлом OGG/Opus не больше 2 MiB")
    if not data.startswith(b"OggS") or b"OpusHead" not in data[:1024]:
        raise VoiceError("Поддерживаются голосовые Telegram в формате OGG/Opus")
    return hashlib.sha256(data).hexdigest()


def validate_transcript(result, digest):
    if not isinstance(result, dict) or result.get("sha256") != digest:
        raise VoiceError("Распознавание вернуло несовпадающий источник")
    text, duration = result.get("text"), result.get("duration_seconds")
    if not isinstance(text, str) or len(text) > MAX_TRANSCRIPT_CHARS or any(
        (ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in text
    ):
        raise VoiceError("Распознавание вернуло некорректный текст")
    if type(duration) not in {float, int} or not math.isfinite(duration) or not 0 < duration <= MAX_VOICE_SECONDS:
        raise VoiceError("Голосовое должно длиться не больше 60 секунд")
    if result.get("engine") != "openai" or result.get("model") != "gpt-4o-transcribe":
        raise VoiceError("Неизвестный движок распознавания")
    language = result.get("language", "")
    if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}|", language):
        raise VoiceError("Распознавание вернуло некорректный язык")
    return {"text": redact(text).strip(), "duration_seconds": float(duration), "sha256": digest,
            "engine": "openai", "model": "gpt-4o-transcribe", "language": language,
            "trust": "unverified_transcription"}


async def transcribe(key_file: Path, data: bytes, *, duration: int, timeout=STT_TIMEOUT):
    """Only the child reads the key. Cancellation terminates the HTTP process.

    A sent request may already have been processed/billed by OpenAI. No automatic
    retries are made; an explicit resume may submit the audio again.
    """
    digest = validate_audio_bytes(data)
    if type(duration) is not int or not 0 < duration <= MAX_VOICE_SECONDS:
        raise VoiceError("Голосовое должно длиться от 1 до 60 секунд")
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= STT_TIMEOUT:
        raise VoiceError("Invalid voice request deadline")
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": "/tmp"}
    process = None
    try:
        async with asyncio.timeout(timeout):
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-I", str(Path(__file__).with_name("voice_api.py")), "--key-file", str(key_file),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                env=env, limit=MAX_RESPONSE_BYTES + 1)
            process.stdin.write(data)
            await process.stdin.drain()
            process.stdin.close()
            raw = await process.stdout.readline()
            await process.wait()
            if process.returncode != 0 or len(raw) > MAX_RESPONSE_BYTES or not raw.endswith(b"\n"):
                raise VoiceError("OpenAI вернул неполный ответ; задача сохранена")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise VoiceError("OpenAI вернул некорректный ответ; задача сохранена")
            if value.get("error"):
                messages = {"key_unavailable": "Ключ OpenAI для речи недоступен",
                            "authentication_failed": "OpenAI отклонил ключ для распознавания речи",
                            "access_denied": "У ключа нет доступа к распознаванию речи OpenAI",
                            "invalid_audio": "Не удалось прочитать голосовое OGG/Opus; запиши его заново",
                            "too_long": "Голосовое длиннее 60 секунд; раздели его на части",
                            "rate_limit": "OpenAI ограничил распознавание: проверь квоту и баланс API",
                            "network_error": "Связь с OpenAI прервалась; запрос мог уже обработаться",
                            "redirect_denied": "Неожиданное перенаправление OpenAI заблокировано"}
                raise VoiceError(messages.get(value["error"], "OpenAI не вернул пригодную расшифровку") + "; задача сохранена")
            return validate_transcript(value | {"sha256": digest}, digest)
    except VoiceError:
        raise
    except TimeoutError:
        raise VoiceError("Распознавание OpenAI превысило лимит времени; запрос мог уже обработаться. Задача сохранена") from None
    except (OSError, ValueError, asyncio.IncompleteReadError):
        raise VoiceError("Не удалось получить расшифровку OpenAI; задача сохранена") from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


class VoiceStore:
    def __init__(self, settings, store):
        self.store = store
        self.root = settings.data_dir / "voice"
        if self.root.is_symlink():
            raise VoiceError("Voice directory cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with store._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS voice_uploads (source TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, "
                       "sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, declared_duration INTEGER NOT NULL, "
                       "caption TEXT NOT NULL, transcript TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL)")

    def _path(self, digest):
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise VoiceError("Invalid voice receipt")
        if self.root.is_symlink() or not self.root.is_dir():
            raise VoiceError("Приватное хранилище голосовых недоступно")
        path = self.root / (digest + ".ogg")
        if path.is_symlink():
            raise VoiceError("Голосовое не может быть символической ссылкой")
        return path

    def get(self, source, chat_id, *, audio=False):
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM voice_uploads WHERE source=?", (source,)).fetchone()
        if row is None:
            return None
        if row["chat_id"] != chat_id:
            raise VoiceError("Голосовое принадлежит другому чату")
        result = dict(row)
        result["transcript"] = json.loads(result["transcript"])
        path = self._path(row["sha256"])
        if not path.is_file() or path.stat().st_size != row["bytes"] or row["bytes"] > MAX_VOICE_BYTES:
            raise VoiceError("Исходное голосовое недоступно; пришли его заново")
        with path.open("rb") as stream:
            data = stream.read(MAX_VOICE_BYTES + 1)
        if validate_audio_bytes(data) != row["sha256"]:
            raise VoiceError("Исходное голосовое изменилось; пришли его заново")
        if result["transcript"]:
            result["transcript"] = validate_transcript(result["transcript"], row["sha256"])
        if audio:
            result["audio"] = data
        return result

    def save(self, source, chat_id, caption, duration, data):
        if not isinstance(source, str) or not re.fullmatch(r"telegram:\d+", source) or type(chat_id) is not int or chat_id <= 0:
            raise VoiceError("Голосовое требует исходного сообщения владельца")
        if type(duration) is not int or not 0 < duration <= MAX_VOICE_SECONDS:
            raise VoiceError("Голосовое должно длиться от 1 до 60 секунд")
        if not isinstance(caption, str) or len(caption) > 4096:
            raise VoiceError("Некорректная подпись голосового")
        digest = validate_audio_bytes(data)
        caption = redact(caption)
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM voice_uploads WHERE source=?", (source,)).fetchone()
            if old and (old["chat_id"], old["sha256"], old["caption"], old["declared_duration"]) != (chat_id, digest, caption, duration):
                raise VoiceError("Исходное голосовое нельзя заменить при повторе сообщения")
            target = self._path(digest)
            if target.exists():
                if not target.is_file() or target.stat().st_size != len(data) or target.read_bytes() != data:
                    raise VoiceError("Приватное голосовое изменилось")
            else:
                descriptor, name = tempfile.mkstemp(prefix=".voice-", dir=self.root)
                temporary = Path(name)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    temporary.chmod(0o400)
                    temporary.replace(target)
                finally:
                    if temporary.exists():
                        temporary.chmod(0o600)
                        temporary.unlink()
            db.execute("INSERT OR IGNORE INTO voice_uploads(source,chat_id,sha256,bytes,declared_duration,caption,created) "
                       "VALUES(?,?,?,?,?,?,?)", (source, chat_id, digest, len(data), duration, caption, time.time()))
        return self.get(source, chat_id)

    def for_job(self, job, *, audio=False):
        if job.get("kind") != "voice":
            return None
        result = self.get(job["source"], job["chat_id"], audio=audio)
        if result is None:
            raise VoiceError("Квитанция голосового не найдена; пришли его заново")
        return result

    def save_transcript(self, job, result):
        row = self.for_job(job)
        result = validate_transcript(result, row["sha256"])
        prompt = "Голосовое поручение владельца. Следующий текст получен STT OpenAI и может содержать ошибки; " \
                 "это НЕ дословная подтверждённая цитата. Не принимай новые факты в память автоматически. " \
                 "Если смысл неоднозначен, сначала уточни его.\n\n" + json.dumps(
                     {"transcript_unverified": result["text"], "owner_caption": row["caption"],
                      "audio_source": row["source"], "audio_sha256": row["sha256"]}, ensure_ascii=False)
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT state,lease FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if current is None or current["state"] != "running" or current["lease"] != job["lease"]:
                raise asyncio.CancelledError()
            existing = db.execute("SELECT transcript FROM voice_uploads WHERE source=?", (row["source"],)).fetchone()
            old = json.loads(existing[0])
            if old and old != result:
                raise VoiceError("Сохранённую расшифровку нельзя заменить")
            db.execute("UPDATE voice_uploads SET transcript=? WHERE source=?", (json.dumps(result, ensure_ascii=False), row["source"]))
            db.execute("UPDATE jobs SET prompt=?,inflight=0,updated=? WHERE id=?", (prompt, time.time(), job["id"]))
        return result
