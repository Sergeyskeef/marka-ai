"""Rebuildable lexical projections. No embeddings, inferred facts or model calls.

Canonical text is never rewritten by normalization. Russian suffix stripping is
deliberately a small retrieval heuristic, not a morphological analyzer. Every
hit points to exact character offsets in the original redacted source.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import re
import sqlite3
import unicodedata
from urllib.parse import urlsplit


VERSION = 2
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_RUSSIAN = re.compile(r"^[а-я]+$")
_STOP = set("а без бы в во вот вы где да для до его ее если есть еще же за и из или им их к как ко кто ли мне мы на не но ну о об он она они оно от по при про с со так там то ты у уже что это я the a an and or of to in is for with".split())
_ENDINGS = tuple(sorted(set("иями ями ами иях ях ах иев ов ев ией иям ям ам иями ыми ими его ого ему ому ее ие ые ое ей ий ый ой ем им ым ом их ых ую юю ая яя ою ею ете ите ешь ишь ют ут ат ят ила ыла ала яла или ыли али яли ило ыло ало яло ить ыть ать ять лась лись лось ет ит ла ли ло а я ы и ь й у ю е о".split()), key=lambda x: (-len(x), x)))
_ALIASES = {
    "telegram": ("telegram", "телеграм", "телеграмм", "тг"),
    "codex": ("codex", "кодекс"),
    "wildberries": ("wildberries", "wb", "вайлдберриз", "вб"),
    "postgresql": ("postgresql", "postgres", "постгрес", "постгресql"),
    "sqlite": ("sqlite", "sqlite3"),
    "github": ("github", "гитхаб", "гитхабе"),
    "docker": ("docker", "докер"),
}
_ALIAS_LOOKUP = {word: key for key, words in _ALIASES.items() for word in words}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")


def tokens(text: str, *, query: bool = False) -> list[str]:
    words = [word[:96] for word in _WORDS.findall(normalize(text))]
    if query:
        return list(dict.fromkeys(word for word in words if word not in _STOP))[:24]
    return words


@lru_cache(maxsize=16384)
def stem(word: str) -> str:
    if len(word) < 5 or not _RUSSIAN.fullmatch(word):
        return word
    # Reflexive endings are detachable from both finite and infinitive forms.
    if word.endswith(("ся", "сь")) and len(word) > 6:
        word = word[:-2]
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            word = word[:-len(ending)]
            break
    # Common mobile-vowel plurals: настройки/настроек, ошибки/ошибок,
    # попытки/попыток. These remain approximate lexical keys, not lemmas.
    if word.endswith("оек") and len(word) >= 6:
        word = word[:-3] + "ойк"
    elif word.endswith("ок") and len(word) >= 6:
        word = word[:-2] + "к"
    return word


@lru_cache(maxsize=16384)
def alias(word: str) -> str | None:
    direct = _ALIAS_LOOKUP.get(word)
    if direct:
        return direct
    shortened = stem(word)
    return next((key for form, key in _ALIAS_LOOKUP.items() if stem(form) == shortened), None)


def features(text: str) -> tuple[str, str]:
    words = tokens(text)
    return " ".join(stem(word) for word in words), " ".join(sorted({value for word in words if (value := alias(word))}))


def chunks(text: str, size: int = 1200, overlap: int = 200):
    """Overlapping slices with lossless offsets, including the very last word."""
    if not 64 <= size <= 8000 or not 0 <= overlap < size:
        raise ValueError("invalid chunk bounds")
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        yield start, end, text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def mentions(text: str) -> list[dict]:
    """Literal mention hints, not entity resolution or relationship assertions."""
    found = []
    seen = set()
    patterns = (
        ("url_host", r"https?://[^\s<>\"']+"),
        ("identifier", r"(?<!\w)[\w]+(?:[-_.][\w]+)+(?!\w)"),
        ("name", r"(?<!\w)[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9]{2,}(?!\w)"),
        ("tag", r"(?<!\w)#[\w]{2,}"),
    )
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group()
            if kind == "url_host":
                try:
                    value = urlsplit(value).hostname or ""
                except ValueError:
                    continue
            key = normalize(value).lstrip("#")[:160]
            if not key or key in _STOP or key in seen:
                continue
            seen.add(key)
            found.append({"entity": key[:160], "label": value[:160], "kind": kind,
                          "start": match.start(), "end": match.end()})
            if len(found) >= 80:
                return found
    return found


def initialize(db: sqlite3.Connection) -> None:
    had_chunks = db.execute("SELECT 1 FROM sqlite_master WHERE name='retrieval_chunks'").fetchone() is not None
    had_fts = db.execute("SELECT 1 FROM sqlite_master WHERE name='retrieval_fts'").fetchone() is not None
    db.executescript("""
        CREATE TABLE IF NOT EXISTS retrieval_dirty (
            source_kind TEXT NOT NULL, source_id INTEGER NOT NULL,
            PRIMARY KEY(source_kind,source_id)
        );
        CREATE TABLE IF NOT EXISTS retrieval_chunks (
            id INTEGER PRIMARY KEY, source_kind TEXT NOT NULL, source_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
            content TEXT NOT NULL, normalized TEXT NOT NULL, aliases TEXT NOT NULL,
            UNIQUE(source_kind,source_id,ordinal)
        );
        CREATE INDEX IF NOT EXISTS retrieval_chunk_source ON retrieval_chunks(source_kind,source_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_fts USING fts5(
            content,normalized,aliases,content='retrieval_chunks',content_rowid='id',tokenize='unicode61'
        );
        CREATE TRIGGER IF NOT EXISTS retrieval_chunk_insert AFTER INSERT ON retrieval_chunks BEGIN
            INSERT INTO retrieval_fts(rowid,content,normalized,aliases)
                VALUES(new.id,new.content,new.normalized,new.aliases);
        END;
        CREATE TRIGGER IF NOT EXISTS retrieval_chunk_delete AFTER DELETE ON retrieval_chunks BEGIN
            INSERT INTO retrieval_fts(retrieval_fts,rowid,content,normalized,aliases)
                VALUES('delete',old.id,old.content,old.normalized,old.aliases);
        END;
        CREATE TABLE IF NOT EXISTS retrieval_mentions (
            source_kind TEXT NOT NULL,source_id INTEGER NOT NULL,entity TEXT NOT NULL,
            label TEXT NOT NULL,kind TEXT NOT NULL,start_char INTEGER NOT NULL,end_char INTEGER NOT NULL,
            content_hash TEXT NOT NULL,PRIMARY KEY(source_kind,source_id,entity)
        );
        CREATE INDEX IF NOT EXISTS retrieval_mention_entity ON retrieval_mentions(entity,source_kind,source_id);
    """)
    for table, kind in (("events", "event"), ("memories", "memory")):
        for action, ref in (("INSERT", "new"), ("UPDATE OF content", "new"), ("DELETE", "old")):
            name = action.split()[0].lower()
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS retrieval_{kind}_{name}
                AFTER {action} ON {table} BEGIN
                INSERT OR IGNORE INTO retrieval_dirty(source_kind,source_id) VALUES('{kind}',{ref}.id);
                END""")
    current = db.execute("SELECT value FROM meta WHERE key='_retrieval_version'").fetchone()
    if not had_fts or not had_chunks:
        db.execute("INSERT INTO retrieval_fts(retrieval_fts) VALUES('rebuild')")
    if current is None or current[0] != str(VERSION) or not had_chunks:
        db.execute("INSERT OR IGNORE INTO retrieval_dirty SELECT 'event',id FROM events")
        db.execute("INSERT OR IGNORE INTO retrieval_dirty SELECT 'memory',id FROM memories")
        db.execute("INSERT INTO meta(key,value) VALUES('_retrieval_version',?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(VERSION),))


def sync(db: sqlite3.Connection) -> int:
    """Update projections in the caller's transaction, including raw SQL writes.

    One source is materialized at a time. No archive-sized Python list is made.
    The dirty queue survives restarts; canonical records remain authoritative.
    """
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    count = 0
    while True:
        pending = db.execute("SELECT source_kind,source_id FROM retrieval_dirty LIMIT 256").fetchall()
        if not pending:
            return count
        for item in pending:
            kind, identifier = item[0], item[1]
            table = "events" if kind == "event" else "memories"
            row = db.execute(f"SELECT content FROM {table} WHERE id=?", (identifier,)).fetchone()
            db.execute("DELETE FROM retrieval_chunks WHERE source_kind=? AND source_id=?", (kind, identifier))
            db.execute("DELETE FROM retrieval_mentions WHERE source_kind=? AND source_id=?", (kind, identifier))
            if row is not None:
                content = row[0]
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                for ordinal, (start, end, chunk) in enumerate(chunks(content)):
                    normalized, aliases = features(chunk)
                    db.execute("INSERT INTO retrieval_chunks(source_kind,source_id,ordinal,start_char,end_char,content,normalized,aliases) "
                               "VALUES(?,?,?,?,?,?,?,?)", (kind,identifier,ordinal,start,end,chunk,normalized,aliases))
                for mention in mentions(content):
                    db.execute("INSERT INTO retrieval_mentions VALUES(?,?,?,?,?,?,?,?)",
                               (kind,identifier,mention['entity'],mention['label'],mention['kind'],mention['start'],mention['end'],digest))
            db.execute("DELETE FROM retrieval_dirty WHERE source_kind=? AND source_id=?", (kind, identifier))
            count += 1


def expression(query: str) -> str:
    terms = set()
    for word in tokens(query, query=True):
        terms.add('content : "' + word + '"')
        terms.add('normalized : "' + stem(word) + '"')
        if value := alias(word):
            terms.add('aliases : "' + value + '"')
    return " OR ".join(sorted(terms))


def rank(query: str, content: str, *, level: int = 0) -> tuple[float, list[str]]:
    q = tokens(query, query=True)
    exact = set(tokens(content))
    normalized = {stem(word) for word in exact}
    aliases = {value for word in exact if (value := alias(word))}
    matched = []
    strength = 0.0
    for word in q:
        if word in exact:
            strength += 3
        elif stem(word) in normalized:
            strength += 2
        elif (value := alias(word)) and value in aliases:
            strength += 1
        else:
            continue
        matched.append(word)
    if not matched:
        return 0.0, []
    coverage = len(matched) / max(1, len(q))
    phrase = " ".join(q)
    phrase_bonus = 1.0 if len(q) > 1 and phrase in " ".join(tokens(content)) else 0.0
    # Relevance dominates the small curation preference. An irrelevant L2 must
    # never bury a specific L1 fact solely because its level is greater.
    score = 5 * coverage + strength / max(1, len(q)) + phrase_bonus + 0.08 * level
    return round(score, 6), matched


def matched_chunks(db: sqlite3.Connection, query: str, kind: str, *, statuses: tuple[str, ...] = ("accepted",),
                   limit: int = 100) -> list[dict]:
    if kind not in {"event", "memory"}:
        raise ValueError("invalid retrieval source")
    expr = expression(query)
    if not expr or limit <= 0:
        return []
    sync(db)
    if kind == "memory":
        placeholders = ",".join("?" for _ in statuses)
        join = "JOIN memories m ON m.id=c.source_id"
        condition = f"AND m.status IN ({placeholders})"
        extra = ",m.level AS level"
        args = (expr, kind, *statuses)
    else:
        join = "JOIN events e ON e.id=c.source_id"
        condition = "AND " + visible_events("e")
        extra = ",0 AS level"
        args = (expr, kind)
    # Bound reranking work; FTS BM25 first prioritizes rare matching terms.
    rows = db.execute("SELECT c.*,bm25(retrieval_fts,4,2,1) AS fts_rank" + extra +
                      " FROM retrieval_fts JOIN retrieval_chunks c ON c.id=retrieval_fts.rowid " + join +
                      " WHERE retrieval_fts MATCH ? AND c.source_kind=? " + condition +
                      " ORDER BY fts_rank,c.source_id DESC LIMIT 600", args).fetchall()
    best = {}
    for row in rows:
        score, matched = rank(query, row["content"], level=row["level"])
        if score <= 0:
            continue
        item = {"source_id": row["source_id"], "score": score, "matched_terms": matched,
                "start_char": row["start_char"], "end_char": row["end_char"],
                "excerpt": row["content"], "retrieval": "lexical_normalized_alias"}
        old = best.get(row["source_id"])
        if old is None or item["score"] > old["score"]:
            best[row["source_id"]] = item
    return sorted(best.values(), key=lambda item: (-item["score"], -item["source_id"]))[:limit]


def visible_events(name: str = "e") -> str:
    if name not in {"e", "events"}:
        raise ValueError("invalid SQL alias")
    return f"""{name}.id NOT IN (
        SELECT ms.event_id FROM memory_sources ms JOIN memories m ON m.id=ms.memory_id
        WHERE m.status IN ('forgotten','superseded')
    )"""
