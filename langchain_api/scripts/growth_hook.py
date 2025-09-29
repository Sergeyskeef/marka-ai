#!/usr/bin/env python3
import json, os, time, argparse
LEDGER=os.environ.get("MARK_GROWTH_LEDGER", "/srv/mark/langchain_api/core_docs/MARK_GROWTH_LEDGER.jsonl")

def record(event: str, who: str, notes: str, extra: dict | None = None):
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "who": who,
        "notes": notes
    }
    if extra:
        rec.update({"extra": extra})
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Append growth event to MARK_GROWTH_LEDGER.jsonl")
    p.add_argument("--event", required=True)
    p.add_argument("--who", default="assistant")
    p.add_argument("--notes", required=True)
    p.add_argument("--extra", help="JSON string with extra fields", default=None)
    args = p.parse_args()
    extra = None
    if args.extra:
        try:
            extra = json.loads(args.extra)
        except Exception:
            extra = None
    record(args.event, args.who, args.notes, extra)
    print("ok")
