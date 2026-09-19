"""A small liveness receipt; the external guardian performs independent checks."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


def delivery_effect(item, *, document: bytes | None = None) -> str:
    """Bind the original durable source AND payload, never a reusable SQLite row ID."""
    payload = {"source": item["source"], "chat_id": item["chat_id"], "text": item["text"],
               "document": item.get("document", ""),
               "document_sha256": hashlib.sha256(document).hexdigest() if document is not None else None}
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
        value = {"version": 1, "pid": os.getpid(), "boot_id": self.boot_id,
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

    async def run(self, stopping: asyncio.Event, *, interval=2):
        while not stopping.is_set():
            # This coroutine must be scheduled by the bot loop itself. A separate
            # heartbeat thread would conceal an event-loop hang from the guardian.
            self.write()
            try:
                await asyncio.wait_for(stopping.wait(), interval)
            except TimeoutError:
                pass
