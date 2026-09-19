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
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

from .redact import redact, redact_value
from . import retrieval


_KINDS = {"fact", "lesson", "skill", "preference"}
_STATUSES = {"candidate", "accepted", "superseded", "forgotten"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _clean(value: Any) -> Any:
    return redact_value(value)


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
            retrieval.initialize(db)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS event_origins (
                    source TEXT NOT NULL, external_id TEXT NOT NULL,
                    event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
                    original_role TEXT NOT NULL, original_timestamp TEXT NOT NULL,
                    content_hash TEXT NOT NULL, origin_meta TEXT NOT NULL,
                    imported_at TEXT NOT NULL, PRIMARY KEY(source,external_id)
                );
                CREATE INDEX IF NOT EXISTS event_origin_id ON event_origins(event_id);
                CREATE TRIGGER IF NOT EXISTS event_origin_immutable
                    BEFORE UPDATE OF source,external_id,original_role,original_timestamp,
                        content_hash,origin_meta,imported_at ON event_origins
                    BEGIN SELECT RAISE(ABORT,'import origin is immutable'); END;
            """)

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
        maximum = 250000 if role == "tool" else 40000
        if len(content) > maximum:
            raise ValueError(f"event content exceeds {maximum} characters")
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

    def history(self, session: str = "main", limit: int = 12, *, before_id: int | None = None) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT e.* FROM events e WHERE session=? AND " + retrieval.visible_events() +
                " AND (? IS NULL OR e.id<?) ORDER BY e.id DESC LIMIT ?",
                (session, before_id, before_id, self._limit(limit)),
            ).fetchall()
        result = [dict(row) for row in reversed(rows)]
        for row in result:
            row["meta"] = json.loads(row["meta"])
        return result

    @staticmethod
    def _page(content: str, offset: int, limit: int) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 8000:
            raise ValueError("page offset must be nonnegative and limit must be 1–8000 characters")
        end = min(len(content), offset + limit)
        return {"content": content[offset:end], "offset": offset, "total_chars": len(content),
                "next_offset": end if end < len(content) else None,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()}

    def get_event(self, event_id: int, *, offset: int = 0, limit: int = 4000,
                  include_inactive: bool = False) -> dict | None:
        """Exact canonical text page. Inactive evidence is opt-in for owner audit."""
        self._page("", offset, limit)
        with self._connect() as db:
            row = db.execute("SELECT e.*, (" + retrieval.visible_events() +
                             ") AS visible FROM events e WHERE id=?", (event_id,)).fetchone()
            if row is None or (not row["visible"] and not include_inactive):
                return None
            item = dict(row)
            item["inactive"] = not bool(item.pop("visible"))
            item["meta"] = json.loads(item["meta"])
            item["trust"] = self._event_trust(item["meta"])
            item.update(self._page(item["content"], offset, limit))
            origin = db.execute("SELECT source,external_id,original_role,original_timestamp,content_hash,imported_at "
                                "FROM event_origins WHERE event_id=?", (event_id,)).fetchone()
            if origin:
                item["origin"] = dict(origin)
            return item

    def get_memory(self, memory_id: int, *, offset: int = 0, limit: int = 4000,
                   source_id: int | None = None, include_inactive: bool = False) -> dict | None:
        """Page a knowledge record, or one immutable evidence snapshot by ID.

        Snapshot content is loaded only when requested. Hashes refer to the
        complete canonical text, never to an abridged model-produced summary.
        """
        self._page("", offset, limit)
        with self._connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None or (row["status"] in {"forgotten", "superseded"} and not include_inactive):
                return None
            item = dict(row)
            item["key"] = item.pop("memory_key")
            evidence = db.execute("SELECT event_id,role,content_hash,captured_at,length(content) AS total_chars "
                                  "FROM memory_sources WHERE memory_id=? ORDER BY event_id", (memory_id,)).fetchall()
            item["sources"] = [source["event_id"] for source in evidence]
            item["source_snapshots"] = [dict(source) for source in evidence]
            item["record_type"] = "memory"
            if source_id is not None:
                source = db.execute("SELECT * FROM memory_sources WHERE memory_id=? AND event_id=?",
                                    (memory_id, source_id)).fetchone()
                if source is None:
                    return None
                item.update({"record_type": "source_snapshot", "event_id": source["event_id"],
                             "role": source["role"], "captured_at": source["captured_at"],
                             "content": source["content"]})
            item.update(self._page(item["content"], offset, limit))
            return item

    @staticmethod
    def _import_timestamp(value: Any) -> tuple[str, str]:
        raw = str(value)
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValueError("import timestamp must be finite")
            parsed = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("import timestamps require an explicit timezone")
        else:
            raise ValueError("import record requires created_at or timestamp")
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds"), raw

    def import_events(self, records, source: str) -> dict:
        """Atomically import up to 1000 historical records without reusing IDs.

        Originals are low-trust data. Duplicate origins are durable even after
        explicit retention; conflicting reuse is rejected instead of rewriting
        a source that a later knowledge record may rely upon.
        """
        if not isinstance(source, str) or not source.strip() or len(source) > 512:
            raise ValueError("import source must be a nonempty string of at most 512 characters")
        source = redact(source.strip())
        prepared = []
        for record in records:
            if len(prepared) >= 1000:
                raise ValueError("import batch limit is 1000 records")
            if not isinstance(record, dict):
                raise ValueError("import records must be objects")
            external = record.get("external_id", record.get("id"))
            if isinstance(external, bool) or not isinstance(external, (str, int)) or not str(external).strip() or len(str(external)) > 512:
                raise ValueError("import record requires a bounded external_id")
            role, content = record.get("role"), record.get("content")
            if not isinstance(role, str) or not role.strip() or len(role) > 64:
                raise ValueError("import role must contain 1–64 characters")
            if not isinstance(content, str) or len(content) > 40000:
                raise ValueError("import content must be a string of at most 40000 characters")
            when, original_timestamp = self._import_timestamp(record.get("created_at", record.get("timestamp")))
            session = record.get("session") or "import:" + source
            if not isinstance(session, str) or len(session) > 1024:
                raise ValueError("import session must be a string of at most 1024 characters")
            content, role, external, session = (redact(str(value)) for value in (content, role, external, session))
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            origin_meta = json.dumps(_clean(record.get("meta") or {}), ensure_ascii=False, sort_keys=True)
            if len(origin_meta) > 16000:
                raise ValueError("import metadata exceeds 16000 characters")
            prepared.append((external,role,content,when,original_timestamp,session,digest,origin_meta))
        imported = skipped = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT value FROM meta WHERE key='_event_high_watermark'").fetchone()
            identifier = max(int(json.loads(previous[0])) if previous else 0,
                             db.execute("SELECT coalesce(max(id),0) FROM events").fetchone()[0],
                             db.execute("SELECT coalesce(max(event_id),0) FROM memory_sources").fetchone()[0])
            for external,role,content,when,original_timestamp,session,digest,origin_meta in prepared:
                existing = db.execute("SELECT original_role,original_timestamp,content_hash FROM event_origins "
                                      "WHERE source=? AND external_id=?", (source,external)).fetchone()
                if existing is not None:
                    if tuple(existing) != (role,original_timestamp,digest):
                        raise ValueError("conflicting content for an existing import origin")
                    skipped += 1
                    continue
                identifier += 1
                metadata = {"imported": True, "trust": "historical_unverified", "source": source,
                            "external_id": external, "origin_meta": json.loads(origin_meta)}
                db.execute("INSERT INTO events(id,role,content,session,created_at,meta) VALUES(?,?,?,?,?,?)",
                           (identifier,role,content,session,when,json.dumps(metadata,ensure_ascii=False)))
                db.execute("INSERT INTO event_origins VALUES(?,?,?,?,?,?,?,?)",
                           (source,external,identifier,role,original_timestamp,digest,origin_meta,_now()))
                imported += 1
            db.execute("INSERT INTO meta(key,value) VALUES('_event_high_watermark',?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(identifier),))
        return {"imported": imported, "skipped": skipped}

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
        result["content_hash"] = hashlib.sha256(result["content"].encode("utf-8")).hexdigest()
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
                hits = retrieval.matched_chunks(db, query, "memory", statuses=statuses, limit=bounded)
                result = []
                for hit in hits:
                    row = db.execute("SELECT * FROM memories WHERE id=?", (hit["source_id"],)).fetchone()
                    item = self._memory(db, row)
                    item["match"] = hit
                    item["score"] = hit["score"]
                    result.append(item)
                return result
            return [self._memory(db, row) for row in rows]

    def recall_events(self, query: str, limit: int = 5) -> list[dict]:
        """Retrieve bounded L0 observations, never promote them into accepted facts.

        Related tool/system outcomes share the request's job/session. Superseded
        or forgotten source events are excluded even from this lower-trust path.
        """
        bounded = min(self._limit(limit), 12)
        if not bounded:
            return []
        excluded = retrieval.visible_events()
        with self._connect() as db:
            hit_by_id = {}
            if query.strip():
                hits = retrieval.matched_chunks(db, query, "event", limit=bounded)
                hit_by_id = {hit["source_id"]: hit for hit in hits}
                matches = [db.execute("SELECT * FROM events WHERE id=?", (hit["source_id"],)).fetchone() for hit in hits]
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
                item = self._episode(row, hit_by_id.get(row["id"]))
                result.append(item)
            return result

    @staticmethod
    def _event_trust(meta: dict) -> str:
        if meta.get("trust") == "unverified_transcription":
            return "unverified_transcription"
        return "historical_unverified" if meta.get("imported") else "observed_episode_not_accepted_knowledge"

    @staticmethod
    def _episode(row: sqlite3.Row, hit: dict | None = None) -> dict:
        item = dict(row)
        item["meta"] = json.loads(item["meta"])
        content = item["content"]
        start = hit["start_char"] if hit else 0
        # Give the matching passage, not an unrelated prefix of a long source.
        start = min(start, max(0, len(content) - 2000))
        item.update(Store._page(content, start, 2000))
        item["truncated"] = len(content) > 2000
        item["trust"] = Store._event_trust(item["meta"])
        if hit:
            item["match"] = hit
            item["score"] = hit["score"]
        return item

    def list_memories(self, status: str = "candidate", limit: int = 10, *, before_id: int | None = None) -> list[dict]:
        if status not in _STATUSES:
            raise ValueError("unknown memory status")
        with self._connect() as db:
            rows = db.execute("SELECT * FROM memories WHERE status=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?",
                              (status, before_id, before_id, self._limit(limit))).fetchall()
            return [self._memory(db, row) for row in rows]

    def memory_page(self, status: str = "candidate", limit: int = 10, *, before_id: int | None = None) -> dict:
        bounded = self._limit(limit)
        rows = self.list_memories(status, bounded, before_id=before_id)
        more = bool(rows and self.list_memories(status, 1, before_id=rows[-1]["id"]))
        return {"items": rows, "next_cursor": rows[-1]["id"] if more else None}

    def related_events(self, event_id: int, limit: int = 8) -> list[dict]:
        """Read-only links: same task/session, then literal entity co-mentions.

        A shared label is only a navigation hint; it never asserts that two
        people, projects or facts are the same real-world entity.
        """
        bounded = min(self._limit(limit), 20)
        if not bounded:
            return []
        with self._connect() as db:
            source = db.execute("SELECT e.* FROM events e WHERE e.id=? AND " + retrieval.visible_events(), (event_id,)).fetchone()
            if source is None:
                return []
            retrieval.sync(db)
            metadata = json.loads(source["meta"])
            sessions = {source["session"]}
            if metadata.get("job"):
                sessions.add("work:" + str(metadata["job"]))
            placeholders = ",".join("?" for _ in sessions)
            result = []
            seen = {event_id}
            # Avoid treating the entire long-lived main/import archive as one
            # task: only nearest neighbors are useful for those sessions.
            rows = db.execute("SELECT e.* FROM events e WHERE e.session IN (" + placeholders +
                              ") AND e.id<>? AND " + retrieval.visible_events() +
                              " ORDER BY abs(e.id-?),e.id LIMIT ?", (*sorted(sessions),event_id,event_id,bounded)).fetchall()
            for row in rows:
                item = self._episode(row)
                item["relationship"] = "same_task" if row["session"].startswith("work:") else "session_neighbor"
                item["related_to"] = event_id
                result.append(item)
                seen.add(row["id"])
            if len(result) < bounded:
                rows = db.execute("""SELECT e.*,group_concat(DISTINCT target.entity) AS shared_entities
                    FROM retrieval_mentions target JOIN retrieval_mentions other ON target.entity=other.entity
                    JOIN events e ON e.id=other.source_id
                    WHERE target.source_kind='event' AND target.source_id=? AND other.source_kind='event'
                    AND e.id<>? AND """ + retrieval.visible_events() +
                    " GROUP BY e.id ORDER BY count(DISTINCT target.entity) DESC,e.id DESC LIMIT ?",
                    (event_id,event_id,bounded * 2)).fetchall()
                for row in rows:
                    if row["id"] in seen:
                        continue
                    item = self._episode(row)
                    item["relationship"] = "literal_entity_co_mention"
                    item["related_to"] = event_id
                    item["shared_entities"] = item["shared_entities"].split(",")[:10]
                    result.append(item)
                    if len(result) >= bounded:
                        break
            return result

    def entity_links(self, query: str = "", limit: int = 20) -> list[dict]:
        """Bounded mention projection with exact evidence IDs and source hashes."""
        bounded = min(self._limit(limit), 50)
        if not bounded:
            return []
        with self._connect() as db:
            retrieval.sync(db)
            query = retrieval.normalize(query).strip()
            rows = db.execute("""SELECT r.* FROM retrieval_mentions r
                LEFT JOIN events e ON r.source_kind='event' AND e.id=r.source_id
                LEFT JOIN memories m ON r.source_kind='memory' AND m.id=r.source_id
                WHERE (?='' OR instr(r.entity,?)>0)
                AND ((r.source_kind='event' AND e.id IS NOT NULL AND """ + retrieval.visible_events() +
                ") OR (r.source_kind='memory' AND m.status='accepted')) "
                "ORDER BY r.source_id DESC,r.entity LIMIT 1000", (query,query)).fetchall()
            grouped = {}
            for row in rows:
                key = row["entity"]
                if key not in grouped:
                    if len(grouped) >= bounded:
                        continue
                    grouped[key] = {"entity": key, "label": row["label"], "kind": row["kind"],
                                    "trust": "literal_mention_projection_not_asserted_fact", "sources": []}
                if len(grouped[key]["sources"]) < 10:
                    grouped[key]["sources"].append({"source_kind": row["source_kind"], "id": row["source_id"],
                        "start_char": row["start_char"], "end_char": row["end_char"], "content_hash": row["content_hash"]})
            return list(grouped.values())

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

    def prune(self, days: int = 0) -> int:
        """Apply an explicit positive-day retention policy; zero keeps all L0."""
        if type(days) is not int or days < 0:
            raise ValueError("retention days cannot be negative")
        if days == 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="microseconds")
        with self._connect() as db:
            result = db.execute(
                """DELETE FROM events WHERE created_at<? AND id NOT IN (
                    SELECT ms.event_id FROM memory_sources ms JOIN memories m ON m.id=ms.memory_id
                    WHERE m.status IN ('candidate','accepted')
                )""", (cutoff,),
            )
            return result.rowcount
