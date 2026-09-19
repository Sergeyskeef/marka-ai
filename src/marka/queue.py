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

from .redact import redact, redact_value


def _clean(value):
    return redact_value(value)


def _payload(value, limit=180000):
    result = json.dumps(_clean(value), ensure_ascii=False, allow_nan=False)
    if len(result.encode("utf-8")) > limit:
        raise ValueError("Task data exceeds persistence budget")
    return result


def _snapshot_payload(value, limit):
    text = json.dumps(_clean(value), ensure_ascii=False, allow_nan=False)
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    # A large source-code action must not break persistence after execution.
    # The original event remains canonical; this is explicitly a bounded view.
    return json.dumps({"truncated": True, "sha256": hashlib.sha256(raw).hexdigest(),
                       "preview": raw[:limit // 3].decode("utf-8", errors="ignore")}, ensure_ascii=False)


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
                CREATE TABLE IF NOT EXISTS task_steps (
                    job_id TEXT NOT NULL, number INTEGER NOT NULL, name TEXT NOT NULL,
                    arguments TEXT NOT NULL, outcome TEXT NOT NULL, event_id INTEGER,
                    created REAL NOT NULL, PRIMARY KEY(job_id,number)
                );
                CREATE TABLE IF NOT EXISTS task_artifacts (
                    job_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
                    bytes INTEGER NOT NULL, step INTEGER NOT NULL, created REAL NOT NULL,
                    PRIMARY KEY(job_id,path)
                );
                CREATE TABLE IF NOT EXISTS budget_extensions (
                    source TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                    extra_steps INTEGER NOT NULL, extra_model_calls INTEGER NOT NULL,
                    extra_seconds INTEGER NOT NULL, created REAL NOT NULL
                );
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
            additions = {
                "lease": "TEXT NOT NULL DEFAULT ''", "first_started": "REAL",
                "budget_configured": "INTEGER NOT NULL DEFAULT 0",
                "max_steps": "INTEGER NOT NULL DEFAULT 0", "max_model_calls": "INTEGER NOT NULL DEFAULT 0",
                "max_seconds": "INTEGER NOT NULL DEFAULT 0", "deadline": "REAL NOT NULL DEFAULT 0",
                "steps_used": "INTEGER NOT NULL DEFAULT 0", "model_calls": "INTEGER NOT NULL DEFAULT 0",
                "continuations": "INTEGER NOT NULL DEFAULT 0", "plan": "TEXT NOT NULL DEFAULT '[]'",
                "progress_summary": "TEXT NOT NULL DEFAULT ''", "verification": "TEXT NOT NULL DEFAULT '{}'",
            }
            for name, definition in additions.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
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
            now, lease = time.time(), uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='running',updated=?,lease=?,first_started=coalesce(first_started,?),"
                       "deadline=CASE WHEN budget_configured=1 AND deadline=0 THEN ?+max_seconds ELSE deadline END WHERE id=?",
                       (now, lease, now, now, row["id"]))
            return self._decode(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    @staticmethod
    def _decode(row):
        return dict(row) | {key: json.loads(row[key]) for key in ("trace", "plan", "verification")}

    @staticmethod
    def _running(db, identifier, lease=None):
        row = db.execute("SELECT * FROM jobs WHERE id=? AND state='running'", (identifier,)).fetchone()
        return row if row is not None and (lease is None or row["lease"] == lease) else None

    def get(self, identifier: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            return self._decode(row) if row else None

    def list(self, limit=10) -> list[dict]:
        with self.connection() as db:
            return [dict(x) for x in db.execute("SELECT id,prompt,state,kind,due,error FROM jobs ORDER BY created DESC LIMIT ?", (limit,))]

    def get_by_source(self, source: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE source=?", (source,)).fetchone()
            return self._decode(row) if row else None

    def checkpoint(self, identifier: str, trace: list, *, inflight=False, lease=None) -> bool:
        # Redact string leaves, not encoded JSON: a secret regex can otherwise
        # consume closing quotes/brackets and make restart checkpoints unreadable.
        payload = _payload(trace)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._running(db, identifier, lease) is None:
                return False
            db.execute("UPDATE jobs SET trace=?,inflight=?,updated=? WHERE id=?", (payload, int(inflight), time.time(), identifier))
            return True

    def finish(self, identifier: str, state: str, result="", error="", *, lease=None, verification=None) -> bool:
        """Atomically finish, schedule the next run, and queue the owner's reply.

        The caller must not enqueue another final reply. Resumed jobs get a new
        completion sequence, while duplicate/late finish calls have no effect.
        """
        if state not in {"completed", "failed", "blocked", "cancelled"}:
            raise ValueError("Invalid final job state")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._running(db, identifier, lease)
            if row is None:
                return False
            db.execute("UPDATE jobs SET state=?,result=?,error=?,inflight=0,lease='',updated=?,completion_seq=completion_seq+1,verification=? WHERE id=?",
                       (state, redact(result), redact(error), time.time(),
                        _payload(verification, 256000) if verification is not None else row["verification"], identifier))
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
            return True

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
                db.execute("UPDATE jobs SET state='cancelled',lease='',updated=? WHERE id=?", (time.time(), row[0]))
            return [r[0] for r in rows]

    def resume(self, identifier: str) -> bool:
        with self.connection() as db:
            cursor = db.execute("UPDATE jobs SET state='queued',due=?,updated=?,lease='',inflight=0,error='' WHERE id=? AND state IN ('blocked','failed','cancelled')", (time.time(), time.time(), identifier))
            return bool(cursor.rowcount)

    def recover(self):
        with self.connection() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN inflight=1 THEN 'blocked' ELSE 'queued' END, lease='',error=CASE WHEN inflight=1 THEN 'Interrupted during tool execution; inspect before /resume' ELSE '' END WHERE state='running'")
            db.execute("UPDATE deliveries SET state='uncertain',error='Process stopped during delivery' WHERE state='sending'")

    @staticmethod
    def _budget(row, now=None):
        now = time.time() if now is None else now
        configured = bool(row["budget_configured"])
        return {
            "configured": configured,
            "limits": {"steps": row["max_steps"], "model_calls": row["max_model_calls"], "seconds": row["max_seconds"]},
            "used": {"steps": row["steps_used"], "model_calls": row["model_calls"]},
            "remaining": {
                "steps": max(0, row["max_steps"] - row["steps_used"]) if configured else None,
                "model_calls": max(0, row["max_model_calls"] - row["model_calls"]) if configured else None,
                "seconds": max(0, row["deadline"] - now) if configured and row["deadline"] else (row["max_seconds"] if configured else None),
            },
            "deadline": row["deadline"] or None,
            "first_started": row["first_started"], "continuations": row["continuations"],
        }

    def configure_task(self, identifier: str, *, max_steps=48, max_model_calls=64, max_seconds=900) -> dict:
        """Set a task's budget once. Replays never replenish existing budgets.

        Queued time before the first claim is free. Afterwards the absolute
        deadline includes pauses, restarts and queue waits. Only extend_budget
        may grant more work after this initial configuration.
        """
        for value, maximum in ((max_steps, 1000), (max_model_calls, 2000), (max_seconds, 86400)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Invalid task budget")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError("Task not found")
            if not row["budget_configured"]:
                deadline = row["first_started"] + max_seconds if row["first_started"] is not None else 0
                db.execute("UPDATE jobs SET budget_configured=1,max_steps=?,max_model_calls=?,max_seconds=?,deadline=?,updated=? WHERE id=?",
                           (max_steps, max_model_calls, max_seconds, deadline, time.time(), identifier))
                row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            return self._budget(row)

    def extend_budget(self, identifier: str, *, extra_steps=0, extra_model_calls=0, extra_seconds=0, source=None) -> dict:
        """Owner-only integration point. It does not resume a task or clear usage."""
        for value, maximum in ((extra_steps, 1000), (extra_model_calls, 2000), (extra_seconds, 86400)):
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError("Invalid budget extension")
        if not any((extra_steps, extra_model_calls, extra_seconds)):
            raise ValueError("Budget extension must add work")
        if source is not None and (not isinstance(source, str) or not 1 <= len(source) <= 300):
            raise ValueError("Invalid budget extension source")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if row is None or not row["budget_configured"]:
                raise ValueError("Configure a known task before extending its budget")
            if source is not None:
                previous = db.execute("SELECT job_id FROM budget_extensions WHERE source=?", (source,)).fetchone()
                if previous is not None:
                    if previous["job_id"] != identifier:
                        raise ValueError("Budget extension source belongs to a different task")
                    return self._budget(row)
            deadline = row["deadline"]
            if deadline and extra_seconds:
                deadline = max(time.time(), deadline) + extra_seconds
            db.execute("UPDATE jobs SET max_steps=max_steps+?,max_model_calls=max_model_calls+?,max_seconds=max_seconds+?,deadline=?,updated=? WHERE id=?",
                       (extra_steps, extra_model_calls, extra_seconds, deadline, time.time(), identifier))
            if source is not None:
                db.execute("INSERT INTO budget_extensions VALUES(?,?,?,?,?,?)",
                           (source, identifier, extra_steps, extra_model_calls, extra_seconds, time.time()))
            return self._budget(db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone())

    def reserve_call(self, identifier: str, lease: str, *, step=True) -> dict:
        """Charge before calling the model, including calls interrupted by a crash."""
        if type(step) is not bool:
            raise ValueError("step must be a boolean")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._running(db, identifier, lease)
            if row is None:
                return {"allowed": False, "reason": "stale_lease"}
            budget = self._budget(row)
            if budget["configured"]:
                reason = ("time_limit" if budget["remaining"]["seconds"] <= 0 else
                          "model_call_limit" if budget["remaining"]["model_calls"] <= 0 else
                          "step_limit" if step and budget["remaining"]["steps"] <= 0 else None)
                if reason:
                    return {"allowed": False, "reason": reason, "budget": budget}
            db.execute("UPDATE jobs SET model_calls=model_calls+1,steps_used=steps_used+?,updated=? WHERE id=?",
                       (int(step), time.time(), identifier))
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            return {"allowed": True, "reason": "", "call_number": row["model_calls"],
                    "step_number": row["steps_used"], "budget": self._budget(row)}

    def requeue(self, identifier: str, lease: str, trace: list, summary="", *, delay=0) -> bool:
        """Yield a bounded work slice without sending a final reply or resetting it."""
        if type(delay) not in (int, float) or not math.isfinite(delay) or not 0 <= delay <= 3600:
            raise ValueError("Invalid continuation delay")
        if not isinstance(summary, str) or len(summary) > 2000:
            raise ValueError("Progress summary exceeds 2000 characters")
        payload = _payload(trace)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._running(db, identifier, lease)
            if row is None or row["inflight"]:
                return False
            budget = self._budget(row)
            if budget["configured"] and any(value <= 0 for value in budget["remaining"].values()):
                return False
            # An unconfigured legacy task cannot spin indefinitely through the
            # new continuation API without consuming decisions.
            if row["continuations"] >= 1000:
                return False
            db.execute("UPDATE jobs SET state='queued',lease='',trace=?,progress_summary=?,due=?,updated=?,continuations=continuations+1 WHERE id=?",
                       (payload, redact(summary), time.time() + delay, time.time(), identifier))
            return True

    def save_plan(self, identifier: str, plan: list, *, lease: str, summary="") -> bool:
        if not isinstance(plan, list) or len(plan) > 12:
            raise ValueError("A task plan must have at most 12 flat steps")
        if not isinstance(summary, str) or len(summary) > 2000:
            raise ValueError("Progress summary exceeds 2000 characters")
        normalized = []
        for item in plan:
            item = {"title": item} if isinstance(item, str) else item
            if not isinstance(item, dict) or set(item) - {"title", "status", "evidence"}:
                raise ValueError("Plan steps require title, optional status/evidence")
            title, status, evidence = item.get("title"), item.get("status", "pending"), item.get("evidence", "")
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 500 or status not in {"pending", "running", "completed", "blocked"}:
                raise ValueError("Invalid plan title or status")
            if not isinstance(evidence, str) or len(evidence) > 1000:
                raise ValueError("Plan evidence must be a short reference")
            normalized.append({"title": title, "status": status, "evidence": evidence})
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._running(db, identifier, lease) is None:
                return False
            db.execute("UPDATE jobs SET plan=?,progress_summary=?,updated=? WHERE id=?",
                       (_payload(normalized, 24000), redact(summary), time.time(), identifier))
            return True

    def record_step(self, identifier: str, *, lease: str, number: int, name: str,
                    outcome: dict, arguments: dict | None = None, event_id: int | None = None) -> bool:
        if type(number) is not int or not 1 <= number <= 100000 or not isinstance(name, str) or not 1 <= len(name) <= 100:
            raise ValueError("Invalid task step")
        if not isinstance(outcome, dict) or (arguments is not None and not isinstance(arguments, dict)):
            raise ValueError("Step observations and arguments must be objects")
        if event_id is not None and (type(event_id) is not int or event_id < 1):
            raise ValueError("Invalid observation source")
        args, observed = _snapshot_payload(arguments or {}, 16000), _snapshot_payload(outcome, 48000)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._running(db, identifier, lease) is None:
                return False
            # An observation is immutable; retries cannot rewrite earlier proof.
            cursor = db.execute("INSERT OR IGNORE INTO task_steps VALUES(?,?,?,?,?,?,?)",
                                (identifier, number, name, args, observed, event_id, time.time()))
            return bool(cursor.rowcount)

    def record_artifact(self, identifier: str, artifact: dict, *, lease: str, step=0) -> bool:
        from .sandbox import _safe_name
        if not isinstance(artifact, dict):
            raise ValueError("Artifact receipt must be an object")
        path = _safe_name(artifact.get("path"))
        digest, size = artifact.get("sha256"), artifact.get("bytes")
        if (not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or type(size) is not int or not 0 <= size <= 20 * 1024 * 1024
                or type(step) is not int or not 0 <= step <= 100000):
            raise ValueError("Invalid artifact receipt")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._running(db, identifier, lease) is None:
                return False
            db.execute("INSERT INTO task_artifacts VALUES(?,?,?,?,?,?) ON CONFLICT(job_id,path) DO UPDATE SET "
                       "sha256=excluded.sha256,bytes=excluded.bytes,step=excluded.step,created=excluded.created",
                       (identifier, path, digest, size, step, time.time()))
            return True

    def progress(self, identifier: str) -> dict | None:
        with self.connection() as db:
            # Read all parts from one WAL snapshot, even while a worker commits.
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if row is None:
                return None
            steps = [dict(item) for item in db.execute("SELECT number,name,outcome,event_id,created FROM task_steps WHERE job_id=? ORDER BY number DESC LIMIT 20", (identifier,))]
            for item in steps:
                item["outcome"] = json.loads(item["outcome"])
            artifacts = [dict(item) for item in db.execute("SELECT path,sha256,bytes,step FROM task_artifacts WHERE job_id=? ORDER BY created DESC LIMIT 100", (identifier,))]
            return {"id": identifier, "state": row["state"], "summary": row["progress_summary"],
                    "plan": json.loads(row["plan"]), "steps": list(reversed(steps)), "artifacts": artifacts,
                    "budget": self._budget(row), "verification": json.loads(row["verification"]),
                    "ambiguous_tool": bool(row["inflight"]), "result": row["result"], "error": row["error"]}

    def evidence_trace(self, identifier: str) -> list[dict]:
        """Merge retained legacy pairs with immutable steps in one WAL snapshot.

        A canonical event can repair a shortened checkpoint only when its role,
        session, job and tool agree. Content from another task is never loaded
        into the returned trace. Surviving checkpoints remain useful after event
        retention removes their canonical rows.
        """
        with self.connection() as db:
            db.execute("BEGIN")
            job = db.execute("SELECT trace FROM jobs WHERE id=?", (identifier,)).fetchone()
            if job is None:
                return []
            rows = db.execute("SELECT name,arguments,outcome,event_id FROM task_steps WHERE job_id=? ORDER BY number LIMIT 2001", (identifier,)).fetchall()
            if len(rows) > 2000:
                raise ValueError("Task evidence exceeds verification budget")
            events_available = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone() is not None

            def canonical_pair(name, arguments, content, event_id, *, durable=False):
                source = event_id if type(event_id) is int and event_id > 0 else None
                if source is not None and events_available:
                    event = db.execute("SELECT role,session,meta,content FROM events WHERE id=?", (source,)).fetchone()
                    if event is not None:
                        try:
                            meta = json.loads(event["meta"])
                        except (ValueError, TypeError):
                            meta = None
                        if (event["role"] == "tool" and event["session"] == "work:" + identifier
                                and isinstance(meta, dict) and meta.get("job") == identifier and meta.get("tool") == name):
                            try:
                                full = json.loads(event["content"])
                            except (ValueError, TypeError):
                                full = None
                            if isinstance(full, dict) and type(full.get("ok")) is bool:
                                if not durable:
                                    content = event["content"]
                                else:
                                    try:
                                        saved = json.loads(content)
                                        raw = json.dumps(_clean(full), ensure_ascii=False, allow_nan=False).encode("utf-8")
                                    except (ValueError, TypeError):
                                        saved = None
                                    if (isinstance(saved, dict) and set(saved) == {"truncated", "sha256", "preview"}
                                            and saved["truncated"] is True):
                                        if hashlib.sha256(raw).hexdigest() == saved["sha256"]:
                                            content = raw.decode("utf-8")
                                        else:
                                            source = None
                            if not durable and isinstance(meta.get("arguments"), dict):
                                arguments = json.dumps(meta["arguments"], ensure_ascii=False)
                        else:
                            # Keep the job's saved observation, but never lend it
                            # a source ID belonging to somebody else's evidence.
                            source = None
                return ({"kind": "tool", "name": name, "arguments": arguments},
                        {"kind": "observation", "content": content, "event_id": source})

            try:
                legacy = json.loads(job["trace"])
            except (ValueError, TypeError):
                legacy = []
            durable_ids = {row["event_id"] for row in rows if type(row["event_id"]) is int and row["event_id"] > 0}
            pairs, seen, pending = [], set(), None
            for item in legacy if isinstance(legacy, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("kind") == "tool" and isinstance(item.get("name"), str):
                    pending = item
                elif item.get("kind") == "observation" and pending:
                    source = item.get("event_id")
                    valid_id = type(source) is int and source > 0
                    if not valid_id or (source not in durable_ids and source not in seen):
                        pairs.append(canonical_pair(pending["name"], pending.get("arguments", "{}"), item.get("content", ""), source))
                        if valid_id:
                            seen.add(source)
                    pending = None
            for row in rows:
                source = row["event_id"]
                if type(source) is int and source > 0 and source in seen:
                    continue
                pairs.append(canonical_pair(row["name"], row["arguments"], row["outcome"], source, durable=True))
                if type(source) is int and source > 0:
                    seen.add(source)
            if len(pairs) > 2000:
                raise ValueError("Task evidence exceeds verification budget")
            # Store event IDs are monotonic, even after retention. Without IDs,
            # the retained legacy order followed by durable step order is the
            # only chronology available; do not invent a timestamp for it.
            if all(type(pair[1]["event_id"]) is int for pair in pairs):
                pairs.sort(key=lambda pair: pair[1]["event_id"])
            return [item for pair in pairs for item in pair]

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
