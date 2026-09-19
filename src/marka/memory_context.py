"""Additive, evidence-linked labels and freshness for canonical memory.

Annotations never change memory content, sources, acceptance, or visibility.
Model annotations are proposals, including dates that claim verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re


LABELS = frozenset({"fact", "lesson", "skill", "preference", "decision", "hypothesis", "dated_observation"})
_DATES = ("last_verified", "review_after", "valid_from", "valid_until")
_PREFIX = "memory-context:v1:"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")


def _utc(now=None):
    value = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now requires a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 32 or not _DATE.fullmatch(value):
        raise ValueError("dates require UTC ISO 8601: YYYY-MM-DDTHH:MM:SS[.ffffff]Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid UTC date") from error
    if parsed.year < 1970:
        raise ValueError("dates must be in years 1970 through 9999")
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parsed(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fields(label, dates):
    if not isinstance(label, str) or label not in LABELS:
        raise ValueError("invalid semantic memory label")
    result = {"label": label, **{key: _timestamp(dates.get(key)) for key in _DATES}}
    if result["valid_from"] and result["valid_until"] and result["valid_until"] <= result["valid_from"]:
        raise ValueError("valid_until must be after valid_from")
    if result["last_verified"] and result["review_after"] and result["review_after"] < result["last_verified"]:
        raise ValueError("review_after must not precede last_verified")
    return result


class MemoryContext:
    def __init__(self, store):
        self.store = store

    def annotate(self, memory_id, *, label, last_verified=None, review_after=None,
                 valid_from=None, valid_until=None, source_ids=None, actor="model",
                 owner_event_id=None, now=None):
        """Replace the actor's annotation; a proposal cannot replace owner metadata.

        Only trusted owner command handling may pass actor='owner'. An owner
        annotation requires its persisted /annotate command receipt source.
        This is separate from accepting the underlying memory.
        """
        if type(memory_id) is not int or memory_id <= 0:
            raise ValueError("memory_id must be a positive integer")
        if not isinstance(actor, str) or actor not in {"model", "owner"}:
            raise ValueError("annotation actor must be model or owner")
        if actor == "model" and owner_event_id is not None:
            raise ValueError("model proposals cannot use owner confirmation")
        captured = _utc(now)
        fields = _fields(label, {"last_verified": last_verified, "review_after": review_after,
                                 "valid_from": valid_from, "valid_until": valid_until})
        if fields["last_verified"] and _parsed(fields["last_verified"]) > captured:
            raise ValueError("last_verified cannot be in the future")
        if source_ids is not None and (not isinstance(source_ids, (list, tuple)) or
                                      len(source_ids) > 16 or not source_ids or
                                      any(type(identifier) is not int or identifier <= 0 for identifier in source_ids)):
            raise ValueError("source_ids requires 1 through 16 positive integer event IDs")
        key = _PREFIX + str(memory_id)
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            memory = db.execute("SELECT status FROM memories WHERE id=?", (memory_id,)).fetchone()
            if memory is None:
                raise ValueError("memory does not exist")
            if memory["status"] not in {"accepted", "candidate"}:
                raise ValueError("inactive memory cannot be annotated")
            snapshots = {row["event_id"]: dict(row) for row in db.execute(
                "SELECT event_id,role,content_hash FROM memory_sources WHERE memory_id=?", (memory_id,))}
            identifiers = list(dict.fromkeys(source_ids if source_ids is not None else snapshots))
            if not identifiers or len(identifiers) > 16:
                raise ValueError("annotation requires 1 through 16 evidence sources")
            sources = []
            for identifier in identifiers:
                if identifier in snapshots:
                    sources.append(snapshots[identifier])
                    continue
                event = db.execute("SELECT role,content FROM events WHERE id=?", (identifier,)).fetchone()
                if event is None:
                    raise ValueError(f"source event {identifier} does not exist")
                sources.append({"event_id": identifier, "role": event["role"],
                                "content_hash": hashlib.sha256(event["content"].encode("utf-8")).hexdigest()})
            owner_source = None
            if actor == "owner":
                owner_source = self._owner_command(db, owner_event_id, memory_id)
                if label == "decision" and not any(row["role"] == "user" for row in snapshots.values()):
                    raise ValueError("an owner decision needs user evidence in the memory sources")
            annotation = {**fields, "actor": actor,
                          "annotation_status": "owner_confirmed" if actor == "owner" else "proposed",
                          "annotated_at": captured.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                          "sources": sources, "owner_command": owner_source}
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            saved = json.loads(row[0]) if row else {"version": 1, "confirmed": None, "proposed": None}
            self._validate_saved(saved)
            saved["confirmed" if actor == "owner" else "proposed"] = annotation
            if actor == "owner":
                saved["proposed"] = None
            db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(saved, ensure_ascii=False)))
        return self.enrich(self.store.get_memory(memory_id, include_inactive=True), now=captured)["memory_context"]

    @staticmethod
    def _owner_command(db, event_id, memory_id):
        if type(event_id) is not int or event_id <= 0:
            raise ValueError("owner annotation requires an owner command event")
        event = db.execute("SELECT role,content,meta FROM events WHERE id=?", (event_id,)).fetchone()
        if event is None or event["role"] != "user":
            raise ValueError("owner command source must have user role")
        metadata = json.loads(event["meta"])
        update = metadata.get("telegram_update")
        command = str(metadata.get("command", "")).split("@")[0].lower()
        words = event["content"].split(maxsplit=2)
        link = db.execute("SELECT value FROM meta WHERE key=?", (f"command-source:{update}",)).fetchone()
        if (metadata.get("imported") or metadata.get("trust") == "unverified_transcription" or
                type(update) is not int or update <= 0 or command != "/annotate" or
                len(words) < 3 or words[0].split("@")[0].lower() != "/annotate" or
                words[1] != str(memory_id) or not link or json.loads(link[0]).get("source_id") != event_id):
            raise ValueError("owner annotation needs a current persisted /annotate command for this memory")
        return {"event_id": event_id, "role": "user", "telegram_update": update,
                "content_hash": hashlib.sha256(event["content"].encode("utf-8")).hexdigest()}

    @staticmethod
    def _validate_saved(saved):
        if not isinstance(saved, dict) or saved.get("version") != 1:
            raise ValueError("invalid memory annotation metadata")
        for slot, status in (("confirmed", "owner_confirmed"), ("proposed", "proposed")):
            item = saved.get(slot)
            if item is None:
                continue
            if not isinstance(item, dict) or item.get("annotation_status") != status:
                raise ValueError("invalid memory annotation state")
            _fields(item.get("label"), item)
            if item.get("actor") != ("owner" if slot == "confirmed" else "model"):
                raise ValueError("invalid memory annotation actor")

    def enrich(self, record, *, now=None):
        """Return a copy with context flags; never omit stale or inactive evidence."""
        if record is None:
            return None
        result = dict(record)
        # Event IDs can collide with memory IDs. Do not annotate episode records.
        if "kind" not in record or "status" not in record or type(record.get("id")) is not int:
            return result
        captured = _utc(now)
        context = {"label": record["kind"], "annotation_status": "unannotated",
                   **{key: None for key in _DATES}, "temporal_status": "unspecified",
                   "needs_recheck": False, "verification_state": "unverified", "reasons": []}
        try:
            saved = self.store.get_meta(_PREFIX + str(record["id"]))
            if saved is None:
                result["memory_context"] = context
                return result
            self._validate_saved(saved)
        except (ValueError, TypeError, KeyError):
            context.update(annotation_status="invalid", temporal_status="needs_recheck",
                           needs_recheck=True, reasons=["invalid_annotation_metadata"])
            result["memory_context"] = context
            return result
        annotation = saved.get("confirmed") or saved.get("proposed")
        if annotation is None:
            result["memory_context"] = context
            return result
        context.update({key: annotation.get(key) for key in ("label", "annotation_status", *_DATES,
                                                             "annotated_at", "sources", "owner_command")})
        if saved.get("confirmed") and saved.get("proposed"):
            context["proposed_annotation"] = saved["proposed"]
        reasons = context["reasons"]
        if annotation.get("valid_from") and captured < _parsed(annotation["valid_from"]):
            reasons.append("not_yet_valid")
        if annotation.get("valid_until") and captured >= _parsed(annotation["valid_until"]):
            reasons.append("validity_expired")
        if annotation.get("review_after") and captured >= _parsed(annotation["review_after"]):
            reasons.append("review_due")
        if annotation.get("last_verified") and captured < _parsed(annotation["last_verified"]):
            reasons.append("verification_in_future")
        if reasons:
            context.update(temporal_status="needs_recheck", needs_recheck=True)
        elif any(annotation.get(key) for key in ("valid_from", "valid_until", "review_after")):
            context["temporal_status"] = "within_declared_window"
        if (annotation["annotation_status"] == "owner_confirmed" and annotation.get("last_verified")
                and record["status"] == "accepted" and not reasons and annotation["label"] != "hypothesis"):
            context["verification_state"] = "owner_reported_verification"
        if annotation["annotation_status"] == "proposed":
            context["verification_state"] = "model_proposal_not_verification"
        result["memory_context"] = context
        return result

    def enrich_many(self, records, *, now=None):
        captured = _utc(now)
        return [self.enrich(record, now=captured) for record in records]
