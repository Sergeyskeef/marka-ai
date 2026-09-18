"""Private JSONL history ingestion. Historical text never becomes accepted fact."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .redact import redact


def import_archive(store, path: Path, source: str, *, batch_size=200):
    if path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("Archive exceeds 512 MiB; split into smaller JSONL files")
    if not isinstance(source, str) or not source.strip() or len(source) > 200:
        raise ValueError("Provide a short source identifier")
    total = {"imported": 0, "skipped": 0, "records": 0}
    batch = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                identifier = record.get("external_id", record.get("id"))
                role = record["role"]
                text = record.get("content", record.get("text"))
                if not isinstance(identifier, str) or not identifier or role not in {"user", "assistant", "tool", "system"} or not isinstance(text, str):
                    raise ValueError()
                if len(text) > 2_000_000:
                    raise ValueError()
                when = record.get("created_at")
                if isinstance(when, (int, float)) and type(when) is not bool:
                    when = datetime.fromtimestamp(when, timezone.utc).isoformat()
                elif when is None:
                    when = "1970-01-01T00:00:00+00:00"
                elif not isinstance(when, str):
                    raise ValueError()
                datetime.fromisoformat(when.replace("Z", "+00:00"))
                metadata = record.get("meta", {})
                if not isinstance(metadata, dict):
                    raise ValueError()
                # Preserve origin, not arbitrary archive keys that resemble live task fields.
                metadata = {key: str(metadata[key])[:1000] for key in ("conversation_id", "conversation_title", "original_role") if key in metadata}
                if role == "assistant":
                    metadata["historical_claims_unverified"] = "true"
                cleaned = redact(text)
                for offset in range(0, max(len(cleaned), 1), 30000):
                    batch.append({"external_id": identifier if len(cleaned) <= 30000 else f"{identifier}:part:{offset//30000}",
                                  "role": role, "content": cleaned[offset:offset+30000], "created_at": when,
                                  "session": "archive:" + str(metadata.get("conversation_id", source)),
                                  "meta": metadata | {"parent_external_id": identifier, "offset": offset}})
                total["records"] += 1
            except (ValueError, KeyError, TypeError, OverflowError, OSError, AttributeError):
                raise ValueError(f"Invalid archive record at line {line_number}; earlier committed batches remain resumable") from None
            if len(batch) >= batch_size:
                result = store.import_events(batch, source=source)
                for key in ("imported", "skipped"):
                    total[key] += result[key]
                batch = []
    if batch:
        result = store.import_events(batch, source=source)
        for key in ("imported", "skipped"):
            total[key] += result[key]
    return total
