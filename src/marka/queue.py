"""Durable work and delivery. Telegram delivery is explicitly at-most-once on ambiguity."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .redact import redact


class Queue:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, source TEXT UNIQUE, chat_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'chat',
                    state TEXT NOT NULL DEFAULT 'queued', due REAL NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL,
                    trace TEXT NOT NULL DEFAULT '[]', inflight INTEGER NOT NULL DEFAULT 0,
                    result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    interval_seconds INTEGER NOT NULL DEFAULT 0, runs_left INTEGER NOT NULL DEFAULT 1,
                    root_id TEXT NOT NULL, completion_seq INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state,due);
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT UNIQUE NOT NULL,
                    chat_id INTEGER NOT NULL, text TEXT NOT NULL, document TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'pending', due REAL NOT NULL, error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS cursors (name TEXT PRIMARY KEY,value INTEGER NOT NULL);
            """)
            # Upgrade the initial queue schema without losing pending work.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            if "root_id" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN root_id TEXT")
                db.execute("UPDATE jobs SET root_id=id WHERE root_id IS NULL")
                # Existing repeats name their parent in source. Walk from each
                # child to the root, including histories older than one level.
                for row in db.execute("SELECT id,source FROM jobs WHERE source LIKE 'repeat:%'").fetchall():
                    root = row["id"]
                    current = row["source"][7:]
                    visited = {root}
                    while current not in visited:
                        visited.add(current)
                        parent = db.execute("SELECT id,source FROM jobs WHERE id=?", (current,)).fetchone()
                        if parent is None:
                            break
                        root = parent["id"]
                        if not (parent["source"] or "").startswith("repeat:"):
                            break
                        current = parent["source"][7:]
                    db.execute("UPDATE jobs SET root_id=? WHERE id=?", (root, row["id"]))
            if "completion_seq" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN completion_seq INTEGER NOT NULL DEFAULT 0")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_root ON jobs(root_id,state)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=20000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def offset(self) -> int:
        with self.connection() as db:
            row = db.execute("SELECT value FROM cursors WHERE name='telegram'").fetchone()
            return row[0] if row else 0

    def advance(self, update_id: int):
        with self.connection() as db:
            db.execute("INSERT INTO cursors VALUES ('telegram',?) ON CONFLICT(name) DO UPDATE SET value=max(value,excluded.value)", (update_id + 1,))

    def enqueue(self, prompt: str, chat_id: int, *, kind="chat", source=None, due=None,
                interval_seconds=0, runs=1) -> str:
        if not prompt.strip() or len(prompt) > 24000:
            raise ValueError("Task must contain 1–24000 characters")
        if type(interval_seconds) is not int or (interval_seconds and interval_seconds < 300):
            raise ValueError("Minimum recurring interval is 300 seconds")
        if type(runs) is not int or not 1 <= runs <= 100:
            raise ValueError("A schedule must have 1–100 finite runs")
        if runs > 1 and interval_seconds == 0:
            raise ValueError("Multiple runs require a recurring interval")
        if due is not None and (not isinstance(due, (float, int)) or not math.isfinite(due)):
            raise ValueError("Task due time must be finite")
        if source is not None and not isinstance(source, str):
            raise ValueError("Task source must be a string")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._insert_job(db, prompt, chat_id, kind=kind, source=source, due=due,
                                    interval_seconds=interval_seconds, runs=runs)

    @staticmethod
    def _insert_job(db, prompt, chat_id, *, kind, source, due, interval_seconds, runs, root_id=None):
        if source is not None:
            existing = db.execute("SELECT id FROM jobs WHERE source=?", (source,)).fetchone()
            if existing is not None:
                return existing["id"]
        identifier = hashlib.sha256(source.encode()).hexdigest()[:12] if source is not None else uuid.uuid4().hex[:12]
        now = time.time()
        db.execute("INSERT INTO jobs(id,source,chat_id,prompt,kind,due,created,updated,interval_seconds,runs_left,root_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (identifier, source, chat_id, redact(prompt), kind, due if due is not None else now,
                    now, now, interval_seconds, runs, root_id or identifier))
        return identifier

    def claim(self) -> dict | None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE state='queued' AND due<=? ORDER BY due,created LIMIT 1", (time.time(),)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET state='running',updated=? WHERE id=?", (time.time(), row["id"]))
            return dict(row) | {"state": "running", "trace": json.loads(row["trace"])}

    def get(self, identifier: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            return dict(row) | {"trace": json.loads(row["trace"])} if row else None

    def list(self, limit=10) -> list[dict]:
        with self.connection() as db:
            return [dict(x) for x in db.execute("SELECT id,prompt,state,kind,due,error FROM jobs ORDER BY created DESC LIMIT ?", (limit,))]

    def checkpoint(self, identifier: str, trace: list, *, inflight=False):
        # Redact string leaves, not encoded JSON: a secret regex can otherwise
        # consume closing quotes/brackets and make restart checkpoints unreadable.
        def clean(value):
            if isinstance(value, str):
                return redact(value)
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        payload = json.dumps(clean(trace), ensure_ascii=False)
        if len(payload) > 180000:
            raise ValueError("Task context exceeds persistence budget")
        with self.connection() as db:
            db.execute("UPDATE jobs SET trace=?,inflight=?,updated=? WHERE id=? AND state='running'", (payload, int(inflight), time.time(), identifier))

    def finish(self, identifier: str, state: str, result="", error=""):
        """Atomically finish, schedule the next run, and queue the owner's reply.

        The caller must not enqueue another final reply. Resumed jobs get a new
        completion sequence, while duplicate/late finish calls have no effect.
        """
        if state not in {"completed", "failed", "blocked", "cancelled"}:
            raise ValueError("Invalid final job state")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE jobs SET state=?,result=?,error=?,inflight=0,updated=?,completion_seq=completion_seq+1 WHERE id=? AND state='running'",
                                 (state, redact(result), redact(error), time.time(), identifier))
            if changed.rowcount != 1:
                return
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if state != "cancelled" and row["chat_id"] > 0:
                if state == "completed":
                    text = result or f"Задача {identifier} завершена."
                else:
                    description = "приостановлена" if state == "blocked" else "не завершена"
                    details = "\n".join(value for value in (result, error) if value) or "Причина не указана"
                    text = (f"Задача {identifier} {description}.\n{details}\n"
                            f"Проверь результат и возможные выполненные действия перед продолжением: /resume {identifier}")
                db.execute("INSERT INTO deliveries(source,chat_id,text,due) VALUES(?,?,?,?)",
                           (f"job:{identifier}:final:{row['completion_seq']}", row["chat_id"], redact(text), time.time()))
            if state == "completed" and row["interval_seconds"] and row["runs_left"] > 1:
                self._insert_job(db, row["prompt"], row["chat_id"], kind="scheduled", source="repeat:" + identifier,
                                 due=max(time.time(), row["due"]) + row["interval_seconds"],
                                 interval_seconds=row["interval_seconds"], runs=row["runs_left"] - 1,
                                 root_id=row["root_id"])

    def cancel(self, identifier: str | None = None) -> list[str]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            sql = "SELECT id FROM jobs WHERE state IN ('queued','running','blocked')"
            if identifier:
                target = db.execute("SELECT root_id FROM jobs WHERE id=?", (identifier,)).fetchone()
                if target is None:
                    return []
                rows = db.execute(sql + " AND root_id=?", (target["root_id"],)).fetchall()
            else:
                rows = db.execute(sql).fetchall()
            for row in rows:
                db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=?", (time.time(), row[0]))
            return [r[0] for r in rows]

    def resume(self, identifier: str) -> bool:
        with self.connection() as db:
            cursor = db.execute("UPDATE jobs SET state='queued',due=?,inflight=0,error='' WHERE id=? AND state IN ('blocked','failed','cancelled')", (time.time(), identifier))
            return bool(cursor.rowcount)

    def recover(self):
        with self.connection() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN inflight=1 THEN 'blocked' ELSE 'queued' END, error=CASE WHEN inflight=1 THEN 'Interrupted during tool execution; inspect before /resume' ELSE '' END WHERE state='running'")
            db.execute("UPDATE deliveries SET state='uncertain',error='Process stopped during delivery' WHERE state='sending'")

    def deliver(self, source: str, chat_id: int, text: str, document=""):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO deliveries(source,chat_id,text,document,due) VALUES (?,?,?,?,?)", (source, chat_id, redact(text), document, time.time()))

    def next_delivery(self) -> dict | None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM deliveries WHERE state='pending' AND due<=? ORDER BY id LIMIT 1", (time.time(),)).fetchone()
            if row:
                db.execute("UPDATE deliveries SET state='sending' WHERE id=?", (row["id"],))
                return dict(row)
            return None

    def delivery_result(self, identifier: int, state: str, *, delay=0, error=""):
        if state not in {"pending", "sent", "failed", "uncertain"}:
            raise ValueError("Invalid delivery state")
        with self.connection() as db:
            # Late callbacks cannot revive a delivery made uncertain by recovery.
            db.execute("UPDATE deliveries SET state=?,due=?,error=? WHERE id=? AND state='sending'", (state, time.time() + delay, redact(error), identifier))

    def delivery_issues(self) -> list[dict]:
        with self.connection() as db:
            return [dict(x) for x in db.execute("SELECT id,source,state,error FROM deliveries WHERE state IN ('failed','uncertain') ORDER BY id DESC LIMIT 5")]
