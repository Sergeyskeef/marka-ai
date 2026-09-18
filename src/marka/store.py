"""Canonical, local memory with explicit provenance and owner-controlled learning.

Levels describe curation: L0 episodes, L1 facts, L2 reusable lessons. The L3
identity belongs to the versioned identity file and cannot be edited here.
SQLite is authoritative; its FTS index is only a derived retrieval aid.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

from .redact import redact


_KINDS = {"fact", "lesson", "skill", "preference"}
_STATUSES = {"candidate", "accepted", "superseded", "forgotten"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


class Store:
    """A connection per operation supports concurrent workers and SQLite backups."""

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            had_event_index = db.execute("SELECT 1 FROM sqlite_master WHERE name='events_fts'").fetchone() is not None
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL,
                    content TEXT NOT NULL, session TEXT NOT NULL,
                    created_at TEXT NOT NULL, meta TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS events_session ON events(session, id);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, content TEXT NOT NULL,
                    kind TEXT NOT NULL, level INTEGER NOT NULL CHECK(level BETWEEN 0 AND 2),
                    status TEXT NOT NULL, memory_key TEXT, actor TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL, created_at TEXT NOT NULL,
                    accepted_at TEXT, superseded_by INTEGER,
                    FOREIGN KEY(superseded_by) REFERENCES memories(id)
                );
                CREATE INDEX IF NOT EXISTS memories_status ON memories(status, level, id);
                CREATE UNIQUE INDEX IF NOT EXISTS memories_current_key
                    ON memories(memory_key) WHERE status='accepted' AND memory_key IS NOT NULL;
                CREATE TABLE IF NOT EXISTS memory_sources (
                    memory_id INTEGER NOT NULL REFERENCES memories(id),
                    event_id INTEGER NOT NULL, role TEXT NOT NULL,
                    content TEXT NOT NULL, content_hash TEXT NOT NULL,
                    captured_at TEXT NOT NULL, PRIMARY KEY(memory_id, event_id)
                );
                CREATE INDEX IF NOT EXISTS memory_source_events ON memory_sources(event_id);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS provider_budget (
                    day TEXT PRIMARY KEY, used INTEGER NOT NULL CHECK(used >= 0)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content, content='memories', content_rowid='id', tokenize='unicode61'
                );
                CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content)
                        VALUES ('delete', old.id, old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE OF content ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content)
                        VALUES ('delete', old.id, old.content);
                    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
                END;
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    content, content='events', content_rowid='id', tokenize='unicode61'
                );
                CREATE TRIGGER IF NOT EXISTS events_fts_insert AFTER INSERT ON events BEGIN
                    INSERT INTO events_fts(rowid, content) VALUES(new.id, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS events_fts_delete AFTER DELETE ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, content) VALUES('delete', old.id, old.content);
                END;
                CREATE TRIGGER IF NOT EXISTS events_fts_update AFTER UPDATE OF content ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, content) VALUES('delete', old.id, old.content);
                    INSERT INTO events_fts(rowid, content) VALUES(new.id, new.content);
                END;
            """)
            if not had_event_index:
                db.execute("INSERT INTO events_fts(events_fts) VALUES('rebuild')")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _limit(limit: int) -> int:
        return max(0, min(int(limit), 100))

    def event(self, role: str, content: str, *, session: str = "main",
              meta: dict | None = None) -> int:
        if not role or not session or not isinstance(content, str):
            raise ValueError("role, session and string content are required")
        if len(content) > 40000:
            raise ValueError("event content exceeds 40000 characters")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Preserve monotonic IDs even when upgrading a pre-AUTOINCREMENT
            # prototype database and after retention removes its latest event.
            previous = db.execute("SELECT value FROM meta WHERE key='_event_high_watermark'").fetchone()
            maximum = db.execute("SELECT coalesce(max(id),0) FROM events").fetchone()[0]
            snapshot_maximum = db.execute("SELECT coalesce(max(event_id),0) FROM memory_sources").fetchone()[0]
            identifier = max(int(json.loads(previous[0])) if previous else 0, maximum, snapshot_maximum) + 1
            result = db.execute(
                "INSERT INTO events(id,role,content,session,created_at,meta) VALUES(?,?,?,?,?,?)",
                (identifier, role, redact(content), session, _now(), json.dumps(_clean(meta or {}), ensure_ascii=False)),
            )
            db.execute("INSERT INTO meta(key,value) VALUES('_event_high_watermark',?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(identifier),))
            return int(result.lastrowid)

    def history(self, session: str = "main", limit: int = 12) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE session=? ORDER BY id DESC LIMIT ?",
                (session, self._limit(limit)),
            ).fetchall()
        result = [dict(row) for row in reversed(rows)]
        for row in result:
            row["meta"] = json.loads(row["meta"])
        return result

    def remember(self, content: str, *, kind: str = "fact", level: int = 1,
                 status: str = "candidate", sources: list[int], key: str | None = None,
                 actor: str = "model", evidence_kind: str = "interpretation") -> int:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("memory content is required")
        if len(content) > 6000:
            raise ValueError("memory content exceeds 6000 characters")
        if kind not in _KINDS or type(level) is not int or level not in (0, 1, 2):
            raise ValueError("invalid memory kind or level; L3 identity is immutable")
        if status not in {"candidate", "accepted"}:
            raise ValueError("new memory must be candidate or accepted")
        if status == "accepted" and actor != "owner":
            raise ValueError("only the owner can accept a memory")
        if not sources or any(type(source) is not int for source in sources):
            raise ValueError("at least one valid source event is required")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValueError("memory key must be a nonempty string")
        if not evidence_kind or not actor:
            raise ValueError("actor and evidence kind are required")
        sources = list(dict.fromkeys(sources))
        captured = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            evidence = []
            for source in sources:
                row = db.execute("SELECT * FROM events WHERE id=?", (source,)).fetchone()
                if row is None:
                    raise ValueError(f"source event {source} does not exist")
                evidence.append(row)
            # Insert as candidate first so the old keyed assertion can be superseded
            # atomically before the unique active-key constraint is checked.
            result = db.execute(
                """INSERT INTO memories(content,kind,level,status,memory_key,actor,
                   evidence_kind,created_at) VALUES(?,?,?,'candidate',?,?,?,?)""",
                (redact(content.strip()), kind, level, key, actor, evidence_kind, captured),
            )
            memory_id = int(result.lastrowid)
            for source in evidence:
                digest = hashlib.sha256(source["content"].encode("utf-8")).hexdigest()
                db.execute(
                    "INSERT INTO memory_sources VALUES(?,?,?,?,?,?)",
                    (memory_id, source["id"], source["role"], source["content"], digest, captured),
                )
            if status == "accepted":
                self._accept(db, memory_id)
            return memory_id

    @staticmethod
    def _memory(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
        result = dict(row)
        result["key"] = result.pop("memory_key")
        snapshots = [dict(source) for source in db.execute(
            "SELECT event_id,role,content,content_hash,captured_at FROM memory_sources "
            "WHERE memory_id=? ORDER BY event_id", (row["id"],),
        )]
        result["sources"] = [source["event_id"] for source in snapshots]
        result["source_snapshots"] = snapshots
        return result

    def search(self, query: str, limit: int = 8, include_candidates: bool = False) -> list[dict]:
        statuses = ("accepted", "candidate") if include_candidates else ("accepted",)
        placeholders = ",".join("?" for _ in statuses)
        bounded = self._limit(limit)
        with self._connect() as db:
            if not query.strip():
                rows = db.execute(
                    f"SELECT * FROM memories WHERE status IN ({placeholders}) "
                    "ORDER BY level DESC, id DESC LIMIT ?", (*statuses, bounded),
                ).fetchall()
            else:
                tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)[:16]
                if not tokens:
                    return []
                # Each term is quoted. User input never becomes an FTS operator.
                expression = " OR ".join('"' + token[:64] + '"' for token in tokens)
                rows = db.execute(
                    "SELECT m.* FROM memories_fts JOIN memories m ON m.id=memories_fts.rowid "
                    f"WHERE memories_fts MATCH ? AND m.status IN ({placeholders}) "
                    "ORDER BY m.level DESC, bm25(memories_fts), m.id DESC LIMIT ?",
                    (expression, *statuses, bounded),
                ).fetchall()
            return [self._memory(db, row) for row in rows]

    def recall_events(self, query: str, limit: int = 5) -> list[dict]:
        """Retrieve bounded L0 observations, never promote them into accepted facts.

        Related tool/system outcomes share the request's job/session. Superseded
        or forgotten source events are excluded even from this lower-trust path.
        """
        bounded = min(self._limit(limit), 12)
        if not bounded:
            return []
        excluded = """e.id NOT IN (
            SELECT ms.event_id FROM memory_sources ms JOIN memories m ON m.id=ms.memory_id
            WHERE m.status IN ('forgotten','superseded')
        )"""
        with self._connect() as db:
            if query.strip():
                tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)[:16]
                if not tokens:
                    return []
                expression = " OR ".join('"' + token[:64] + '"' for token in tokens)
                matches = db.execute(
                    "SELECT e.* FROM events_fts JOIN events e ON e.id=events_fts.rowid "
                    f"WHERE events_fts MATCH ? AND {excluded} "
                    "ORDER BY bm25(events_fts),e.id DESC LIMIT ?", (expression, bounded),
                ).fetchall()
            else:
                matches = db.execute(f"SELECT e.* FROM events e WHERE {excluded} ORDER BY e.id DESC LIMIT ?",
                                     (bounded,)).fetchall()
            rows: list[sqlite3.Row] = []
            seen: set[int] = set()
            for match in matches:
                if match["id"] not in seen:
                    rows.append(match)
                    seen.add(match["id"])
                if len(rows) >= bounded:
                    break
                metadata = json.loads(match["meta"])
                job = metadata.get("job")
                work_session = "work:" + str(job) if job else match["session"]
                if not work_session.startswith("work:"):
                    continue
                related = db.execute(
                    f"SELECT e.* FROM events e WHERE e.session=? AND e.role IN ('tool','system') AND {excluded} "
                    "ORDER BY e.id DESC LIMIT ?", (work_session, bounded),
                ).fetchall()
                # One related result per match reserves room for other matches.
                for row in related:
                    if row["id"] not in seen:
                        rows.append(row)
                        seen.add(row["id"])
                        break
                if len(rows) >= bounded:
                    break
            result = []
            for row in rows[:bounded]:
                item = dict(row)
                item["meta"] = json.loads(item["meta"])
                item["truncated"] = len(item["content"]) > 2000
                item["content"] = item["content"][:2000]
                item["trust"] = "observed_episode_not_accepted_knowledge"
                result.append(item)
            return result

    def list_memories(self, status: str = "candidate", limit: int = 10) -> list[dict]:
        if status not in _STATUSES:
            raise ValueError("unknown memory status")
        with self._connect() as db:
            rows = db.execute("SELECT * FROM memories WHERE status=? ORDER BY id DESC LIMIT ?",
                              (status, self._limit(limit))).fetchall()
            return [self._memory(db, row) for row in rows]

    @staticmethod
    def _accept(db: sqlite3.Connection, memory_id: int) -> None:
        row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(memory_id)
        if row["status"] == "accepted":
            return
        if row["status"] != "candidate":
            raise ValueError("only an active candidate can be accepted")
        if row["memory_key"] is not None:
            db.execute("UPDATE memories SET status='superseded',superseded_by=? "
                       "WHERE memory_key=? AND status='accepted' AND id<>?",
                       (memory_id, row["memory_key"], memory_id))
        db.execute("UPDATE memories SET status='accepted',actor='owner',accepted_at=? WHERE id=?",
                   (_now(), memory_id))

    def accept(self, memory_id: int) -> dict:
        """Explicit owner action. This method must not be exposed as a model tool."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._accept(db, memory_id)
            row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            return self._memory(db, row)

    def forget(self, memory_id: int) -> bool:
        """Tombstone a memory; keep audit evidence, exclude it from future retrieval."""
        with self._connect() as db:
            result = db.execute("UPDATE memories SET status='forgotten' "
                                "WHERE id=? AND status<>'forgotten'", (memory_id,))
            return result.rowcount > 0

    def stats(self) -> dict:
        with self._connect() as db:
            counts = {status: 0 for status in sorted(_STATUSES)}
            counts.update({row["status"]: row["n"] for row in db.execute(
                "SELECT status,count(*) AS n FROM memories GROUP BY status")})
            events = db.execute("SELECT count(*) FROM events").fetchone()[0]
        return {"events": events, "memories": sum(counts.values()),
                "by_status": counts, "budget_used": self.budget_used()}

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_meta(self, key: str, value: Any) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(value, ensure_ascii=False)))

    @staticmethod
    def _day(date: str | None) -> str:
        day = date or datetime.now(timezone.utc).date().isoformat()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("budget date must use YYYY-MM-DD")
        datetime.strptime(day, "%Y-%m-%d")
        return day

    def claim_budget(self, limit: int, date: str | None = None) -> bool:
        day = self._day(date)
        if limit <= 0:
            return False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO provider_budget(day,used) VALUES(?,0)", (day,))
            result = db.execute("UPDATE provider_budget SET used=used+1 WHERE day=? AND used<?",
                                (day, limit))
            return result.rowcount == 1

    def budget_used(self, date: str | None = None) -> int:
        day = self._day(date)
        with self._connect() as db:
            row = db.execute("SELECT used FROM provider_budget WHERE day=?", (day,)).fetchone()
            return int(row[0]) if row else 0

    def backup(self, path: Path) -> Path:
        destination = Path(path).expanduser().resolve()
        if destination == self.path:
            raise ValueError("backup destination must differ from the live database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        return destination

    def prune(self, days: int = 90) -> int:
        if days < 0:
            raise ValueError("retention days cannot be negative")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="microseconds")
        with self._connect() as db:
            result = db.execute(
                """DELETE FROM events WHERE created_at<? AND id NOT IN (
                    SELECT ms.event_id FROM memory_sources ms JOIN memories m ON m.id=ms.memory_id
                    WHERE m.status IN ('candidate','accepted')
                )""", (cutoff,),
            )
            return result.rowcount
