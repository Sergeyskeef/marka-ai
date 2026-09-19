"""Immutable, evidence-linked recipes for the isolated code runner, never host tools."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from .redact import redact
from .sandbox import _safe_name, _validate_command

MAX_FILES = 16
MAX_BYTES = 512 * 1024
LIMITATION = ("Validated on the recorded input and command only. Exit code 0 does not "
              "prove general correctness. Reuse requires the isolated runner and a new outcome check.")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise ValueError("Skill name must be a lowercase ASCII slug, at most 64 characters")
    return name


def _path(root: Path, relative: str) -> Path:
    _safe_name(relative)
    if any(part.casefold() in {"auth.json", "settings.json", "credentials.json", "id_rsa", "id_ed25519"}
           or part.lower().endswith((".pem", ".key", ".p12", ".pfx", ".session"))
           for part in relative.split("/")):
        raise ValueError("Credential paths cannot become skill inputs")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Skill storage root is unavailable or is a symlink")
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError("Skill paths cannot contain symlinks")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("Skill path escapes its storage root")
    return current


def _manifest(value) -> dict:
    if not isinstance(value, dict) or not 1 <= len(value) <= MAX_FILES:
        raise ValueError("A skill requires 1–16 recorded input files")
    if any(not isinstance(name, str) for name in value):
        raise ValueError("Skill input paths must be strings")
    total, names, result = 0, set(), {}
    for name, item in sorted(value.items()):
        _safe_name(name)
        folded = name.casefold()
        if any(folded == other or folded.startswith(other + "/") or other.startswith(folded + "/") for other in names):
            raise ValueError("Skill input paths collide")
        names.add(folded)
        if (not isinstance(item, dict) or type(item.get("bytes")) is not int or not 0 <= item["bytes"] <= MAX_BYTES
                or not isinstance(item.get("sha256"), str) or not re.fullmatch("[0-9a-f]{64}", item["sha256"])):
            raise ValueError("Invalid recorded input digest or byte count")
        total += item["bytes"]
        result[name] = {"sha256": item["sha256"], "bytes": item["bytes"]}
    if total > MAX_BYTES:
        raise ValueError("Skill inputs exceed 512 KiB total")
    return result


def _read_verified(root: Path, manifest: dict) -> dict[str, bytes]:
    files = {}
    for name, metadata in manifest.items():
        path = _path(root, name)
        if not path.is_file() or path.stat().st_size != metadata["bytes"]:
            raise ValueError("Skill input is missing or changed since its verified run")
        with path.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) != metadata["bytes"] or _hash(content) != metadata["sha256"]:
            raise ValueError("Skill input digest does not match its verified run")
        # Exact bytes must be preserved: never silently redact runnable code.
        text = content.decode("utf-8", errors="replace")
        if redact(text) != text:
            raise ValueError("Potential credential content cannot become a skill input")
        files[name] = content
    return files


class SkillLibrary:
    def __init__(self, settings, store, queue):
        self.settings, self.store, self.queue = settings, store, queue
        self.root = settings.data_dir / "skills"
        if self.root.is_symlink():
            raise ValueError("Skill library cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS skill_versions (
                    name TEXT NOT NULL, version INTEGER NOT NULL, description TEXT NOT NULL,
                    content_hash TEXT NOT NULL, manifest TEXT NOT NULL, created REAL NOT NULL,
                    PRIMARY KEY(name,version), UNIQUE(name,content_hash)
                );
                CREATE TABLE IF NOT EXISTS skill_evidence (
                    name TEXT NOT NULL, version INTEGER NOT NULL, event_id INTEGER NOT NULL,
                    job_id TEXT NOT NULL, source_snapshot TEXT NOT NULL, source_hash TEXT NOT NULL,
                    arguments TEXT NOT NULL, captured REAL NOT NULL,
                    PRIMARY KEY(name,version,event_id),
                    FOREIGN KEY(name,version) REFERENCES skill_versions(name,version)
                );
            """)

    @staticmethod
    def _negative_feedback(db, job_id: str) -> bool:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='learning_feedback'").fetchone() is None:
            return False
        row = db.execute("SELECT valence FROM learning_feedback WHERE job_id=? ORDER BY id DESC LIMIT 1", (job_id,)).fetchone()
        return row is not None and row["valence"] < 0

    @staticmethod
    def _negative_use_feedback(db, name: str, version: int) -> bool:
        """Use immutable runtime receipts, including runs before this upgrade.

        A later positive review of another task cannot override a rejected use.
        The ledger survives checkpoint compaction and needs no source rewrite.
        """
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='learning_feedback'").fetchone() is None:
            return False
        # Keep the small feedback set outermost; task_steps has a job_id index.
        rows = db.execute("SELECT s.job_id,s.outcome,s.event_id FROM learning_feedback f "
                          "CROSS JOIN task_steps s ON s.job_id=f.job_id AND s.name='skill.run' "
                          "WHERE f.valence<0 AND f.id="
                          "(SELECT max(id) FROM learning_feedback WHERE job_id=f.job_id)")
        for row in rows:
            try:
                observed = json.loads(row["outcome"])
                if isinstance(observed, dict) and observed.get("truncated") is True:
                    # Recover only the exact runtime-hashed source, never a
                    # model trace, imported event or a shortened JSON preview.
                    event = db.execute("SELECT role,session,meta,content FROM events WHERE id=?", (row["event_id"],)).fetchone()
                    if event is None or event["role"] != "tool" or event["session"] != "work:" + row["job_id"]:
                        continue
                    meta, full = json.loads(event["meta"]), json.loads(event["content"])
                    if (not isinstance(meta, dict) or meta.get("job") != row["job_id"]
                            or meta.get("tool") != "skill.run" or meta.get("imported")):
                        continue
                    from .queue import _snapshot_payload
                    if json.loads(_snapshot_payload(full, 48000)) != observed:
                        continue
                    observed = full
                result = observed.get("result") if isinstance(observed, dict) else None
                if (isinstance(observed, dict) and observed.get("ok") is True and isinstance(result, dict)
                        and result.get("skill") == name and type(result.get("version")) is int
                        and result["version"] == version and type(result.get("source_event")) is int
                        and db.execute("SELECT 1 FROM skill_evidence WHERE name=? AND version=? AND event_id=?",
                                       (name, version, result["source_event"])).fetchone()):
                    return True
            except (ValueError, TypeError):
                continue
        return False

    def _source(self, event_id: int, job_id: str) -> tuple[dict, dict, str]:
        if type(event_id) is not int or event_id < 1 or not isinstance(job_id, str) or not self.queue.get(job_id):
            raise ValueError("A real task and tool observation are required")
        event = self.store.get_event(event_id)
        if (not event or event["role"] != "tool" or event["meta"].get("tool") != "code.run"
                or event["meta"].get("job") != job_id or event["meta"].get("imported")):
            raise ValueError("Skill evidence must be an active code.run observation from this task")
        with self.store._connect() as db:
            row = db.execute("SELECT content FROM events WHERE id=?", (event_id,)).fetchone()
            if self._negative_feedback(db, job_id):
                raise ValueError("Owner feedback rejects this task result; it cannot supply a reusable skill")
        if row is None:
            raise ValueError("Skill evidence is no longer available")
        try:
            observation = json.loads(row["content"])
        except (ValueError, TypeError):
            raise ValueError("Skill evidence must contain a complete structured observation") from None
        result = observation.get("result") if isinstance(observation, dict) else None
        if (not isinstance(observation, dict) or observation.get("ok") is not True or not isinstance(result, dict)
                or type(result.get("exit_code")) is not int or result["exit_code"] != 0
                or result.get("timed_out") is not False or result.get("error") or observation.get("error")):
            raise ValueError("Skill evidence needs an actual successful process, without timeout or error")
        # evidence_trace can also reconstruct legacy checkpoint pairs. Reusable
        # code requires the stronger durable-call receipt before using that API's
        # hash-verified restoration of a compacted observation.
        with self.queue.connection() as db:
            durable = db.execute("SELECT 1 FROM task_steps WHERE job_id=? AND event_id=? AND name='code.run'",
                                 (job_id, event_id)).fetchone()
        if durable is None:
            raise ValueError("Skill requires a durable recorded tool call, not a model trace")
        previous, arguments = None, None
        for item in self.queue.evidence_trace(job_id):
            if item.get("kind") == "observation" and item.get("event_id") == event_id:
                if not previous or previous.get("name") != "code.run":
                    raise ValueError("Skill evidence is not linked to a code.run call")
                try:
                    arguments = json.loads(previous["arguments"])
                    recorded = json.loads(item["content"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError("Skill call ledger is incomplete") from None
                if recorded != observation:
                    raise ValueError("Skill observation does not match its immutable task ledger")
                break
            previous = item if item.get("kind") == "tool" else None
        if not isinstance(arguments, dict):
            raise ValueError("Skill requires a durable recorded tool call, not a model trace")
        argv, timeout = arguments.get("argv"), arguments.get("timeout", 30)
        _validate_command(argv, timeout)
        if result.get("argv") != argv:
            raise ValueError("Skill command does not match the runtime-recorded command")
        if any(redact(argument) != argument for argument in argv):
            raise ValueError("Credential-like command arguments cannot become a skill")
        return {"argv": argv, "timeout": timeout, "inputs": _manifest(result.get("input_manifest"))}, arguments, row["content"]

    def _package(self, content_hash: str, manifest: dict) -> dict[str, bytes]:
        if not re.fullmatch("[0-9a-f]{64}", content_hash):
            raise ValueError("Invalid skill archive identifier")
        directory = _path(self.root, content_hash)
        metadata = _path(directory, "manifest.json")
        if not metadata.is_file() or metadata.stat().st_size > 32000:
            raise ValueError("Skill archive metadata is missing or oversized")
        try:
            archived = json.loads(metadata.read_text("utf-8"))
        except (ValueError, UnicodeError):
            raise ValueError("Skill archive metadata is invalid") from None
        if archived != manifest or _hash(_json(archived).encode("utf-8")) != content_hash:
            raise ValueError("Skill archive metadata has changed")
        _validate_command(manifest.get("argv"), manifest.get("timeout"))
        return _read_verified(_path(directory, "inputs"), _manifest(manifest.get("inputs")))

    def _archive(self, digest: str, manifest: dict, files: dict[str, bytes]) -> None:
        target = _path(self.root, digest)
        if target.exists():
            self._package(digest, manifest)
            return
        temporary = Path(tempfile.mkdtemp(prefix="capture-", dir=self.root))
        try:
            (temporary / "inputs").mkdir(mode=0o700)
            for name, content in files.items():
                path = _path(temporary / "inputs", name)
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                path.chmod(0o400)
            (temporary / "manifest.json").write_text(_json(manifest), encoding="utf-8")
            (temporary / "manifest.json").chmod(0o400)
            temporary.rename(target)
        finally:
            if temporary.exists():
                for path in temporary.rglob("*"):
                    if path.is_file() and not path.is_symlink():
                        path.chmod(0o600)
                shutil.rmtree(temporary)

    def save(self, name: str, description: str, event_id: int, job_id: str) -> dict:
        name = _name(name)
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1000:
            raise ValueError("Skill description must contain 1–1000 characters")
        manifest, arguments, snapshot = self._source(event_id, job_id)
        files = _read_verified(self.settings.workspace, manifest["inputs"])
        digest = _hash(_json(manifest).encode("utf-8"))
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._archive(digest, manifest, files)
            row = db.execute("SELECT version FROM skill_versions WHERE name=? AND content_hash=?", (name, digest)).fetchone()
            duplicate = row is not None
            version = row["version"] if row else db.execute("SELECT coalesce(max(version),0)+1 FROM skill_versions WHERE name=?", (name,)).fetchone()[0]
            if not duplicate:
                db.execute("INSERT INTO skill_versions VALUES(?,?,?,?,?,?)",
                           (name, version, redact(description.strip()), digest, _json(manifest), time.time()))
            db.execute("INSERT OR IGNORE INTO skill_evidence VALUES(?,?,?,?,?,?,?,?)",
                       (name, version, event_id, job_id, snapshot, _hash(snapshot.encode("utf-8")), _json(arguments), time.time()))
        return {"name": name, "version": version, "content_hash": digest, "deduplicated": duplicate,
                "event_id": event_id, "job_id": job_id, "input_count": len(files),
                "input_bytes": sum(map(len, files.values())), "limitations": LIMITATION}

    def _latest(self, name: str) -> tuple[dict, dict, dict]:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM skill_versions WHERE name=? ORDER BY version DESC LIMIT 1", (_name(name),)).fetchone()
            evidence = db.execute("SELECT * FROM skill_evidence WHERE name=? AND version=? ORDER BY event_id DESC",
                                  (name, row["version"])).fetchall() if row else []
            if (any(self._negative_feedback(db, proof["job_id"]) for proof in evidence)
                    or (row and self._negative_use_feedback(db, name, row["version"]))):
                raise ValueError("Owner feedback suspends this skill; a zero process exit did not establish task correctness")
        if row is None:
            raise ValueError("Skill does not exist")
        for proof in evidence:
            source = self.store.get_event(proof["event_id"])
            if (source and source["content_hash"] == proof["source_hash"] and source["role"] == "tool"
                    and source["meta"].get("job") == proof["job_id"] and source["meta"].get("tool") == "code.run"
                    and not source["meta"].get("imported")):
                return dict(row), json.loads(row["manifest"]), dict(proof)
        raise ValueError("Skill has no active canonical evidence; forgotten or missing sources cannot be reused")

    @staticmethod
    def _receipt(row: dict, manifest: dict, proof: dict) -> dict:
        return {key: row[key] for key in ("name", "version", "description", "content_hash")} | {
            "argv": manifest["argv"], "timeout": manifest["timeout"], "input_manifest": manifest["inputs"],
            "event_id": proof["event_id"], "job_id": proof["job_id"], "source_hash": proof["source_hash"],
            "validation": "observed_process_exit_zero", "limitations": LIMITATION}

    def inspect(self, name: str) -> dict:
        row, manifest, proof = self._latest(name)
        files = self._package(row["content_hash"], manifest)
        previews, remaining = {}, 12000
        for path, content in files.items():
            if remaining <= 0:
                break
            try:
                text = content.decode("utf-8")
            except UnicodeError:
                continue
            excerpt = text[:min(3000, remaining)]
            previews[path] = {"content": excerpt, "truncated": len(excerpt) < len(text)}
            remaining -= len(excerpt)
        return self._receipt(row, manifest, proof) | {"previews": previews, "preview_trust": "untrusted_code_data"}

    def prepare(self, name: str) -> dict:
        row, manifest, proof = self._latest(name)
        files = self._package(row["content_hash"], manifest)
        return self._receipt(row, manifest, proof) | {"files": {path: base64.b64encode(content).decode("ascii") for path, content in files.items()}}

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if not isinstance(query, str) or len(query) > 1000 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Skill search needs a short query and limit 1–20")
        terms = set(re.findall(r"\w+", query.casefold()))
        with self.store._connect() as db:
            rows = db.execute("SELECT s.name,s.description,s.created FROM skill_versions s WHERE version="
                              "(SELECT max(version) FROM skill_versions WHERE name=s.name) ORDER BY created DESC LIMIT 1000").fetchall()
        ranked = []
        for row in rows:
            text = (row["name"] + " " + row["description"]).casefold()
            score = sum(term in text for term in terms)
            if terms and not score:
                continue
            ranked.append((score, row["created"], row["name"]))
        found = []
        for _, _, name in sorted(ranked, reverse=True):
            try:
                version, manifest, proof = self._latest(name)
                self._package(version["content_hash"], manifest)
            except (ValueError, OSError):
                continue
            found.append(self._receipt(version, manifest, proof))
            if len(found) == limit:
                break
        return found
