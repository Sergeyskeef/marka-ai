"""A small liveness receipt; the external guardian performs independent checks."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import time
import traceback
import uuid

from . import __version__

COMPONENTS = {"startup", "supervisor", "polling", "worker", "delivery", "maintenance", "heartbeat", "signal"}
ERRORS = set("CancelledError TimeoutError RuntimeError ValueError TypeError OSError PermissionError OperationalError IntegrityError DatabaseError ProviderError BridgeError TelegramError TelegramRetryAfter VoiceError AttributeError KeyError IndexError MemoryError KeyboardInterrupt SystemExit".split())
MODULES = set("app health queue store bridge_client telegram engine learning backup provider semantic media config".split())


def delivery_effect(item, *, document: bytes | None = None) -> str:
    """Bind the original durable source AND payload, never a reusable SQLite row ID."""
    payload = {"source": item["source"], "chat_id": item["chat_id"], "text": item["text"],
               "document": item.get("document", ""),
               "document_sha256": hashlib.sha256(document).hexdigest() if document is not None else None}
    # Preserve identities for existing messages/documents across the migration.
    if item.get("media_kind", "document") != "document":
        payload["media_kind"] = item["media_kind"]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    return "delivery:" + digest


class Heartbeat:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "heartbeat.json"
        self.boot_id = uuid.uuid4().hex
        self.started = self.worker_progress = time.time()
        self.phase = "starting"
        self.job_id = ""
        self.job_deadline = None

    def progress(self, job=None):
        self.worker_progress = time.time()
        self.job_id = job["id"] if job else ""
        self.job_deadline = job.get("deadline") or None if job else None

    def write(self):
        value = {"version": 1, "runtime_version": __version__, "pid": os.getpid(), "boot_id": self.boot_id,
                 "started": self.started, "tick": time.time(), "worker_progress": self.worker_progress,
                 "job_id": self.job_id, "job_deadline": self.job_deadline, "phase": self.phase}
        temporary = self.path.with_name("heartbeat-" + self.boot_id + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def record_exit(self, component, event, error=None, *, signal_number=None):
        """Persist only enumerated technical fields, never messages or traceback text."""
        frames = []
        if error is not None:
            for frame in traceback.extract_tb(error.__traceback__, limit=12):
                path = Path(frame.filename)
                if path.parent.name == "marka" and path.stem in MODULES:
                    frames.append({"module": path.stem, "line": frame.lineno})
        name = type(error).__name__ if error is not None else None
        value = {"version": 1, "runtime_version": __version__, "at": time.time(),
                 "boot_id": self.boot_id, "started": self.started,
                 "component": component if component in COMPONENTS else "supervisor",
                 "event": event if event in {"failed", "cancelled", "returned", "requested", "signal"} else "failed",
                 "exception": name if name in ERRORS else ("other" if error is not None else None),
                 "signal": signal_number if signal_number in (2, 15) else None, "frames": frames}
        if isinstance(error, sqlite3.Error):
            code = getattr(error, "sqlite_errorcode", None)
            if type(code) is int and 0 <= code <= 65535:
                value["sqlite_errorcode"] = code
        target = self.path.with_name("last-exit.json")
        temporary = target.with_name("exit-" + uuid.uuid4().hex + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return value

    async def run(self, stopping: asyncio.Event, *, interval=2):
        while not stopping.is_set():
            # This coroutine must be scheduled by the bot loop itself. A separate
            # heartbeat thread would conceal an event-loop hang from the guardian.
            self.write()
            try:
                await asyncio.wait_for(stopping.wait(), interval)
            except TimeoutError:
                pass
