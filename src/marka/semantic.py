"""Optional local multilingual retrieval. SQLite remains the source of truth.

Only fixed, hash-pinned model assets are downloaded by an explicit CLI command.
Inference never sends text over a network or executes remote model Python code.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sqlite3
import struct
import threading
import urllib.request

from .retrieval import visible_events

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
ASSETS = {
    "model.onnx": ("onnx/model_quint8_avx2.onnx", 118453870, "98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f"),
    "tokenizer.json": ("tokenizer.json", 9081518, "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8"),
}
DIMENSION = 384
PIPELINE = "mean128-chunk500-v1"
ORT_VERSION = "1.30.0"
RUNTIME_PROFILE = "ort-mmap-no-prepack-v1"
RUNTIME_BYTES = 118713512
_MODEL_KEY = REVISION + ":" + PIPELINE
_ENCODERS = {}
_ENCODER_LOCK = threading.Lock()


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def _normalized_vector(value) -> list[float]:
    try:
        vector = [float(item) for item in value]
        if len(vector) != DIMENSION or not all(math.isfinite(item) for item in vector):
            raise ValueError()
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError()
        return [item / norm for item in vector]
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid embedding vector shape or values") from None


def _trim_unused_heap() -> None:
    """Return freed model-parsing buffers to Linux/glibc, when supported."""
    if os.name != "posix":
        return
    try:
        import ctypes
        trim = ctypes.CDLL(None).malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        trim(0)
    except (AttributeError, OSError):
        pass


def _runtime_manifest(directory: Path) -> dict | None:
    """Validate bounded local derivation metadata, without rereading 119 MB per query."""
    manifest, model = directory / "manifest.json", directory / "model.ort"
    try:
        if (manifest.is_symlink() or model.is_symlink() or not model.is_file()
                or manifest.stat().st_size > 16384 or model.stat().st_size != RUNTIME_BYTES):
            return None
        data = json.loads(manifest.read_text("utf-8"))
        runtime = data.get("runtime", {})
        digest = runtime.get("sha256", "")
        if (data.get("model") != MODEL or data.get("revision") != REVISION
                or runtime.get("profile") != RUNTIME_PROFILE
                or runtime.get("ort_version") != ORT_VERSION
                or runtime.get("file") != "model.ort"
                or runtime.get("bytes") != RUNTIME_BYTES
                or runtime.get("source_sha256") != ASSETS["model.onnx"][2]
                or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            return None
        return runtime
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _derive_runtime(directory: Path) -> dict:
    """Locally serialize the verified model as ORT, allowing mmap without copies.

    ORT serialization is not byte-deterministic across processes. The manifest
    records this local derivative's hash and binds it to the pinned input/runtime;
    it is an integrity record, not a signature against a compromised model folder.
    """
    import onnxruntime as ort
    if ort.__version__ != ORT_VERSION:
        raise ValueError(f"Semantic runtime requires onnxruntime=={ORT_VERSION}")
    ort.disable_telemetry_events()
    existing = _runtime_manifest(directory)
    target, temporary = directory / "model.ort", directory / "model.ort.convert"
    if target.is_symlink() or temporary.is_symlink():
        raise ValueError("Derived model assets must not be symlinks")
    if existing and _file_hash(target) == existing["sha256"]:
        return existing
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.add_session_config_entry("session.disable_prepacking", "1")
    options.add_session_config_entry("session.save_model_format", "ORT")
    options.optimized_model_filepath = str(temporary)
    try:
        session = ort.InferenceSession(str(directory / "model.onnx"), sess_options=options,
                                       providers=["CPUExecutionProvider"])
        del session
        _trim_unused_heap()
        if temporary.stat().st_size != RUNTIME_BYTES:
            raise ValueError("Unexpected derived model size; supported runtime profile changed")
        digest = _file_hash(temporary)
        temporary.chmod(0o600)
        temporary.replace(target)
        return {"file": "model.ort", "bytes": RUNTIME_BYTES, "sha256": digest,
                "source_sha256": ASSETS["model.onnx"][2], "ort_version": ORT_VERSION,
                "profile": RUNTIME_PROFILE}
    finally:
        temporary.unlink(missing_ok=True)


def install_model(directory: Path) -> dict:
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Model directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, (remote, size, digest) in ASSETS.items():
        target = directory / name
        if target.is_symlink():
            raise ValueError("Model assets must not be symlinks")
        if target.is_file() and target.stat().st_size == size and _file_hash(target) == digest:
            continue
        temporary = directory / (name + ".download")
        if temporary.is_symlink():
            raise ValueError("Model download must not be a symlink")
        try:
            hasher, received = hashlib.sha256(), 0
            with urllib.request.urlopen(f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{remote}", timeout=120) as response, temporary.open("wb") as output:
                while payload := response.read(1024 * 1024):
                    received += len(payload)
                    if received > size:
                        raise ValueError("Model download exceeded pinned size")
                    hasher.update(payload)
                    output.write(payload)
            if received != size or hasher.hexdigest() != digest:
                raise ValueError("Model asset checksum mismatch")
            temporary.chmod(0o600)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    runtime = _derive_runtime(directory)
    manifest = {"model": MODEL, "revision": REVISION, "license": "Apache-2.0", "dimensions": DIMENSION,
                "source": f"https://huggingface.co/{MODEL}/tree/{REVISION}", "assets": ASSETS,
                "runtime": runtime}
    manifest_path = directory / "manifest.json"
    manifest_temporary = directory / "manifest.json.write"
    if manifest_path.is_symlink() or manifest_temporary.is_symlink():
        raise ValueError("Model manifest must not be a symlink")
    try:
        manifest_temporary.write_text(json.dumps(manifest, indent=2), "utf-8")
        manifest_temporary.chmod(0o600)
        manifest_temporary.replace(manifest_path)
    finally:
        manifest_temporary.unlink(missing_ok=True)
    return manifest


class LocalEncoder:
    def __init__(self, directory: Path):
        _trim_unused_heap()
        # Avoid hidden BLAS/tokenizer thread pools on a one-CPU small VM. An
        # explicitly configured environment remains the operator's choice.
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        ort.disable_telemetry_events()
        if ort.__version__ != ORT_VERSION:
            raise ValueError(f"Semantic runtime requires onnxruntime=={ORT_VERSION}")
        self.np = np
        options = ort.SessionOptions()
        # The default transformer graph optimization/prepacking duplicates large
        # initializers during loading and exceeded a real 512 MiB container.
        # Favor bounded memory over peak throughput on the small CPU deployment.
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.add_session_config_entry("session.disable_prepacking", "1")
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        options.add_session_config_entry("session.use_memory_mapped_ort_model", "1")
        options.add_session_config_entry("session.use_ort_model_bytes_for_initializers", "1")
        self.session = ort.InferenceSession(str(directory / "model.ort"), sess_options=options, providers=["CPUExecutionProvider"])
        self.inputs = {item.name for item in self.session.get_inputs()}
        _trim_unused_heap()
        # Load the tokenizer after temporary ONNX parsing allocations have gone.
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding()
        self.lock = threading.Lock()
        _trim_unused_heap()

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > 8:
            raise ValueError("Embedding batch limit is eight")
        with self.lock:
            encodings = self.tokenizer.encode_batch([text[:8000] for text in texts])
            np = self.np
            feeds = {
                "input_ids": np.array([entry.ids for entry in encodings], dtype=np.int64),
                "attention_mask": np.array([entry.attention_mask for entry in encodings], dtype=np.int64),
                "token_type_ids": np.array([entry.type_ids for entry in encodings], dtype=np.int64),
            }
            output = self.session.run(None, {key: value for key, value in feeds.items() if key in self.inputs})[0]
            if len(output.shape) == 3:
                mask = feeds["attention_mask"][:, :, None].astype(np.float32)
                output = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
            norms = np.maximum(np.linalg.norm(output, axis=1, keepdims=True), 1e-12)
            result = (output / norms).astype(np.float32)
            if result.shape != (len(texts), DIMENSION) or not np.isfinite(result).all():
                raise ValueError("Unexpected local embedding shape or values")
            return result.tolist()


class SemanticIndex:
    def __init__(self, store, model_dir: Path, *, encoder=None):
        self.store, self.model_dir = store, Path(model_dir)
        self.encoder = encoder
        self.index_path = store.path.with_suffix(".semantic.sqlite3")
        self._initialized = False

    def _initialize(self):
        if self._initialized:
            return
        fresh = not self.index_path.exists()
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS vectors (
                    kind TEXT NOT NULL, source_id INTEGER NOT NULL, part INTEGER NOT NULL,
                    source_hash TEXT NOT NULL, offset INTEGER NOT NULL, length INTEGER NOT NULL,
                    vector BLOB NOT NULL, model TEXT NOT NULL,
                    PRIMARY KEY(kind,source_id,part)
                );
                CREATE TABLE IF NOT EXISTS indexed (
                    kind TEXT NOT NULL, source_id INTEGER NOT NULL, source_hash TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(kind,source_id)
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(indexed)")}
            if "model" not in columns:
                db.execute("ALTER TABLE indexed ADD COLUMN model TEXT NOT NULL DEFAULT ''")
            outdated = db.execute("SELECT 1 FROM indexed WHERE model<>? LIMIT 1", (_MODEL_KEY,)).fetchone() is not None
            if outdated:
                db.execute("DELETE FROM vectors WHERE model<>?", (_MODEL_KEY,))
                db.execute("DELETE FROM indexed WHERE model<>?", (_MODEL_KEY,))
        self._prepare_pending(reset=fresh or outdated)
        self._initialized = True

    def _prepare_pending(self, *, reset=False):
        """A durable derivative work queue makes idle indexing independent of N.

        A generation counter prevents losing an edit arriving while encoding.
        Vector commits precede conditional acknowledgements, so a crash causes
        at most a harmless replay of the same source, never a skipped change.
        """
        with self.store._connect() as source:
            source.executescript("""
                CREATE TABLE IF NOT EXISTS semantic_pending (
                    kind TEXT NOT NULL,source_id INTEGER NOT NULL,generation INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(kind,source_id)
                );
            """)
            for table, kind in (("events", "event"), ("memories", "memory")):
                for action, ref in (("INSERT", "new"), ("UPDATE OF content" + (",status" if kind == "memory" else ""), "new"), ("DELETE", "old")):
                    name = action.split()[0].lower()
                    source.execute(f"""CREATE TRIGGER IF NOT EXISTS semantic_{kind}_{name}
                        AFTER {action} ON {table} BEGIN
                        INSERT INTO semantic_pending(kind,source_id,generation) VALUES('{kind}',{ref}.id,1)
                        ON CONFLICT(kind,source_id) DO UPDATE SET generation=generation+1;
                        END""")
            source.execute("BEGIN IMMEDIATE")
            marker = source.execute("SELECT value FROM meta WHERE key='_semantic_pipeline'").fetchone()
            if reset or marker is None or json.loads(marker[0]) != _MODEL_KEY:
                source.execute("INSERT INTO semantic_pending(kind,source_id) SELECT 'memory',id FROM memories WHERE status='accepted' "
                               "ON CONFLICT(kind,source_id) DO UPDATE SET generation=generation+1")
                source.execute("INSERT INTO semantic_pending(kind,source_id) SELECT 'event',id FROM events WHERE role IN ('user','assistant','tool','system') "
                               "ON CONFLICT(kind,source_id) DO UPDATE SET generation=generation+1")
                source.execute("INSERT INTO meta(key,value) VALUES('_semantic_pipeline',?) "
                               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(_MODEL_KEY),))

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.index_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def available(self) -> bool:
        if self.encoder is not None:
            return True
        if self.model_dir.is_symlink():
            return False
        return (_runtime_manifest(self.model_dir) is not None
                and all(not (self.model_dir / name).is_symlink() and (self.model_dir / name).is_file()
                        and (self.model_dir / name).stat().st_size == entry[1] for name, entry in ASSETS.items()))

    def _encoder(self):
        if self.encoder is not None:
            return self.encoder
        if not self.available():
            raise ValueError("Local semantic model is not installed")
        key = (str(self.model_dir.resolve()), _MODEL_KEY)
        with _ENCODER_LOCK:
            if key not in _ENCODERS:
                for name, (_, _, digest) in ASSETS.items():
                    if _file_hash(self.model_dir / name) != digest:
                        raise ValueError("Installed model checksum mismatch; reinstall pinned model")
                runtime = _runtime_manifest(self.model_dir)
                if runtime is None or _file_hash(self.model_dir / "model.ort") != runtime["sha256"]:
                    raise ValueError("Derived model checksum mismatch; reinstall pinned model")
                _ENCODERS[key] = LocalEncoder(self.model_dir)
            return _ENCODERS[key]

    def stats(self):
        if not self.index_path.exists():
            return {"available": self.available(), "model": MODEL, "revision": REVISION,
                    "pipeline": PIPELINE, "sources": 0, "chunks": 0}
        self._initialize()
        with self._db() as db:
            return {"available": self.available(), "model": MODEL, "revision": REVISION,
                    "pipeline": PIPELINE,
                    "sources": db.execute("SELECT count(*) FROM indexed").fetchone()[0],
                    "chunks": db.execute("SELECT count(*) FROM vectors").fetchone()[0]}

    @staticmethod
    def chunks(text: str):
        # Short overlapping passages fit the model's 128-token context reasonably.
        # Original text stays in Store and remains available through exact paging.
        start = 0
        while start < len(text):
            end = min(start + 500, len(text))
            if end < len(text):
                boundary = max(text.rfind(". ", start + 250, end), text.rfind("\n", start + 250, end))
                if boundary > start:
                    end = boundary + 1
            yield start, text[start:end]
            if end == len(text):
                break
            start = max(start + 1, end - 80)

    def update(self, max_sources=64, *, include_events=True):
        if not self.available():
            return {"indexed": 0, "available": False}
        self._initialize()
        maximum = max(1, min(int(max_sources), 10000))
        processed = checked = 0
        with self.store._connect() as source, self._db() as db:
            pending = source.execute("SELECT * FROM semantic_pending WHERE (? OR kind='memory') "
                                     "ORDER BY kind DESC,source_id DESC LIMIT ?", (include_events,maximum)).fetchall()
            for task in pending:
                kind, identifier = task["kind"], task["source_id"]
                if kind == "memory":
                    row = source.execute("SELECT id,content FROM memories WHERE id=? AND status='accepted'", (identifier,)).fetchone()
                else:
                    row = source.execute("SELECT e.id,e.content FROM events e WHERE e.id=? AND " + visible_events(), (identifier,)).fetchone()
                checked += 1
                digest = hashlib.sha256(row["content"].encode()).hexdigest() if row else None
                old = db.execute("SELECT source_hash,model FROM indexed WHERE kind=? AND source_id=?", (kind,identifier)).fetchone()
                if row is None:
                    db.execute("DELETE FROM vectors WHERE kind=? AND source_id=?", (kind,identifier))
                    db.execute("DELETE FROM indexed WHERE kind=? AND source_id=?", (kind,identifier))
                elif not old or old[0] != digest or old[1] != _MODEL_KEY:
                    parts = list(self.chunks(row["content"]))
                    db.execute("DELETE FROM vectors WHERE kind=? AND source_id=?", (kind,identifier))
                    for offset in range(0, len(parts), 4):
                        batch = parts[offset:offset+4]
                        vectors = self._encoder().encode([text for _,text in batch])
                        if not isinstance(vectors, (list,tuple)) or len(vectors) != len(batch):
                            raise ValueError("Embedding result count does not match input batch")
                        for index, ((start,text),vector) in enumerate(zip(batch,vectors)):
                            vector = _normalized_vector(vector)
                            db.execute("INSERT INTO vectors VALUES(?,?,?,?,?,?,?,?)",
                                       (kind,identifier,offset+index,digest,start,len(text),struct.pack(f'<{DIMENSION}f',*vector),_MODEL_KEY))
                    db.execute("INSERT INTO indexed(kind,source_id,source_hash,model) VALUES(?,?,?,?) "
                               "ON CONFLICT(kind,source_id) DO UPDATE SET source_hash=excluded.source_hash,model=excluded.model",
                               (kind,identifier,digest,_MODEL_KEY))
                    processed += 1
                db.commit()
                source.execute("DELETE FROM semantic_pending WHERE kind=? AND source_id=? AND generation=?",
                               (kind,identifier,task["generation"]))
                source.commit()
            remaining = source.execute("SELECT count(*) FROM semantic_pending WHERE (? OR kind='memory')", (include_events,)).fetchone()[0]
        return {"indexed": processed, "checked": checked, "remaining": remaining, "available": True}

    def search(self, query: str, *, kind="memory", limit=8):
        if not query.strip() or not self.available():
            return []
        if kind not in {"memory", "event"}:
            raise ValueError("Unknown vector source kind")
        limit = max(0, min(int(limit), 20))
        if not limit or not self.index_path.exists():
            return []
        self._initialize()
        vectors = self._encoder().encode([query[:4000]])
        if not isinstance(vectors, (list, tuple)) or len(vectors) != 1:
            raise ValueError("Embedding result count does not match query")
        vector = _normalized_vector(vectors[0])
        # Scan bounded batches. Optional numpy accelerates the actual deployment;
        # the fallback keeps deterministic fake-encoder tests dependency-free.
        try:
            import numpy as np
        except ImportError:
            np = None
        winners, canonical_hashes = {}, {}
        with self._db() as db, self.store._connect() as source:
            cursor = db.execute("SELECT * FROM vectors WHERE kind=? AND model=?", (kind, _MODEL_KEY))
            while rows := cursor.fetchmany(256):
                if np is not None:
                    matrix = np.frombuffer(b''.join(row['vector'] for row in rows), dtype='<f4').reshape(-1, DIMENSION)
                    scores = matrix @ np.asarray(vector, dtype=np.float32)
                else:
                    scores = [sum(a*b for a, b in zip(vector, struct.unpack(f'<{DIMENSION}f', row['vector']))) for row in rows]
                candidates = [(float(score), row) for score, row in zip(scores, rows) if math.isfinite(float(score)) and float(score) >= 0.20]
                unknown = sorted({row["source_id"] for _, row in candidates if row["source_id"] not in canonical_hashes})
                if unknown:
                    placeholders = ",".join("?" for _ in unknown)
                    if kind == "memory":
                        canonical = source.execute("SELECT id,content FROM memories WHERE status='accepted' AND id IN (" + placeholders + ")", unknown).fetchall()
                    else:
                        canonical = source.execute("SELECT e.id,e.content FROM events e WHERE e.id IN (" + placeholders + ") AND " + visible_events(), unknown).fetchall()
                    canonical_hashes.update({identifier: None for identifier in unknown})
                    canonical_hashes.update({row["id"]: hashlib.sha256(row["content"].encode()).hexdigest() for row in canonical})
                for score, row in candidates:
                    identifier = row["source_id"]
                    if canonical_hashes.get(identifier) != row["source_hash"]:
                        continue
                    if identifier not in winners or score > winners[identifier][0]:
                        winners[identifier] = (score, dict(row))
                keep = sorted(winners, key=lambda key: (-winners[key][0], -key))[:limit * 20]
                winners = {key: winners[key] for key in keep}
        found, used = [], set()
        for score, row in sorted(winners.values(), key=lambda item: (-item[0], -item[1]["source_id"])):
            identifier = row["source_id"]
            if identifier in used:
                continue
            item = self.store.get_memory(identifier, offset=row["offset"], limit=max(800, row["length"])) if kind == "memory" else self.store.get_event(identifier, offset=row["offset"], limit=max(800, row["length"]))
            if item is None or (kind == "memory" and item.get("status") != "accepted"):
                continue
            if item.get("content_hash") != row["source_hash"]:
                continue
            item.update(semantic_score=round(score, 4), retrieval="local_multilingual_embedding", matched_offset=row["offset"])
            found.append(item)
            used.add(identifier)
            if len(found) >= limit:
                break
        return found


def hybrid(lexical: list[dict], semantic: list[dict], limit=8):
    """Fuse independent retrieval evidence and keep its actual source passage.

    A partial bag-of-words match is not a full second vote for a semantic hit.
    When coverage is available, lexical support starts above half the query and
    reaches full strength only when every query term matched (including normalized
    forms/aliases). Squaring this bounded support limits weak corroboration.
    Scores are ranking signals, not probabilities or a change in source authority.
    """
    limit = max(0, min(int(limit), 100))
    if not limit:
        return []
    groups = {}
    scored = any("semantic_score" in row for row in semantic)
    for method, rows in (("lexical", lexical), ("semantic", semantic)):
        seen = set()
        rank = 0
        for row in rows:
            source_kind = "event" if "session" in row and "role" in row else "memory"
            identifier = (source_kind, row["id"])
            if identifier in seen:
                continue
            seen.add(identifier)
            rank += 1
            weight = 1.0
            if method == "lexical" and semantic and scored:
                match = row.get("match") or {}
                coverage = match.get("coverage")
                try:
                    if coverage is None:
                        # Compatibility with pre-upgrade results. A complete exact
                        # match scores 8; related episodes without match evidence
                        # contribute no extra vote.
                        coverage = float(row.get("score", 0)) / 8
                    coverage = float(coverage)
                    if not math.isfinite(coverage):
                        coverage = 0.0
                except (TypeError, ValueError, OverflowError):
                    coverage = 0.0
                support = max(0.0, min(1.0, 2 * coverage - 1))
                weight = support * support
            contribution = weight / (30 + rank)
            group = groups.setdefault(identifier, {"score": 0.0, "views": [], "hashes": set(),
                                                   "states": set(), "roles": set(), "inactive": False})
            group["score"] += contribution
            group["views"].append((contribution, row))
            if row.get("content_hash"):
                group["hashes"].add(row["content_hash"])
            if source_kind == "memory" and row.get("status"):
                group["states"].add(row["status"])
            if source_kind == "event":
                group["roles"].add(row["role"])
            group["inactive"] |= row.get("inactive") is True or row.get("status") in {"forgotten", "superseded"}
    result = []
    for group in sorted(groups.values(), key=lambda item: item["score"], reverse=True):
        # Never combine evidence from two versions or conceal withdrawal/status
        # disagreement during concurrent reads. A subsequent search can refresh it.
        if group["inactive"] or any(len(group[key]) > 1 for key in ("hashes", "states", "roles")):
            continue
        _, selected = max(group["views"], key=lambda item: item[0])
        result.append(dict(selected, hybrid_score=round(group["score"], 6)))
        if len(result) == limit:
            break
    return result
