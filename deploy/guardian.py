#!/usr/bin/env python3
"""Independent, root-owned release controller. Python 3.10 stdlib only.

Never import the mutable runtime here. Configuration, snapshots and this file
must remain outside bot mounts. A model can submit source bytes, never commands.
This is a recovery boundary, not a proof that arbitrary Python is beneficial.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid

MAX_REQUEST = 6 * 1024 * 1024
MAX_MODULE = 60 * 1024
RESERVE = 1024 * 1024 * 1024
MAX_DATABASE = 2 * 1024 * 1024 * 1024
MAX_EVENT_BYTES = 2 * 1024 * 1024
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
MODULE = re.compile(r"src/marka/[A-Za-z_][A-Za-z0-9_]*\.py\Z")
TERMINAL = {"accepted", "recovered", "rejected", "manual_intervention"}


class Rejected(Exception):
    """Only fixed, nonsensitive messages are propagated to status."""


def root_protected(info, *, private=False):
    return os.name == "nt" or (info.st_uid == 0 and not info.st_mode & (0o077 if private else 0o022))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(sources):
    return digest(canonical({p: digest(v.encode("utf-8")) for p, v in sources.items()}))


def fsync_dir(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic(path, raw, mode=0o600):
    path = Path(path)
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(mode)
        fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_copy(source, destination):
    """Copy a large protected checkpoint without reading it all into RAM."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink():
        raise Rejected("checkpoint symlink refused")
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or not root_protected(info):
        os.close(descriptor)
        raise Rejected("checkpoint is not protected")
    temporary = destination.parent / (".restore-" + uuid.uuid4().hex)
    try:
        with os.fdopen(descriptor, "rb") as src, open(temporary, "xb") as dst:
            shutil.copyfileobj(src, dst, 128 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
        fsync_dir(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def read_regular(path, limit, *, trusted=False):
    """Capture a bounded immutable buffer, refusing links and concurrent writes."""
    path = Path(path)
    if path.is_symlink():
        raise Rejected("symlink refused")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise Rejected("invalid file size or type")
        if trusted and not root_protected(before):
            raise Rejected("guardian file is not root protected")
        raw = b""
        while len(raw) <= limit:
            block = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not block:
                break
            raw += block
        after = os.fstat(fd)
        if len(raw) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise Rejected("file changed during capture")
        return raw
    finally:
        os.close(fd)


def json_object(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Rejected("duplicate JSON key")
            out[key] = value
        return out
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected("invalid JSON") from None
    if not isinstance(result, dict):
        raise Rejected("JSON object required")
    return result


def sources_from(root):
    root = Path(root)
    result = {}
    for path in sorted((root / "src" / "marka").glob("*.py")):
        name = path.relative_to(root).as_posix()
        result[name] = read_regular(path, MAX_REQUEST, trusted=True).decode("utf-8")
    if not result:
        raise Rejected("trusted source inventory missing")
    return result


def validate_request(request, trusted, owner_source):
    required = {"version", "request_id", "experiment_id", "job_id", "source", "objective",
                "baseline", "candidate", "baseline_manifest", "candidate_manifest"}
    if set(request) - required - {"report", "report_sha256"} or not required <= set(request):
        raise Rejected("unknown or missing request fields")
    if type(request["version"]) is not int or request["version"] != 1:
        raise Rejected("unsupported request version")
    for key in ("request_id", "experiment_id", "job_id"):
        if not isinstance(request[key], str) or not IDENT.fullmatch(request[key]):
            raise Rejected("invalid request identity")
    if not isinstance(request["objective"], str) or not 1 <= len(request["objective"].strip()) <= 4000:
        raise Rejected("invalid objective")
    if not isinstance(request["source"], str) or not re.fullmatch(r"telegram:[0-9]{1,20}", request["source"]):
        raise Rejected("owner source required")
    if not 0 <= int(request["source"].split(":")[1]) <= 2**63 - 1:
        raise Rejected("owner source outside supported range")
    if not owner_source(request["source"]):
        raise Rejected("original owner input absent from bridge journal")
    for name in ("baseline", "candidate"):
        values = request[name]
        if not isinstance(values, dict) or not values or len(values) > 250:
            raise Rejected("invalid source inventory")
        if any(not isinstance(p, str) or not MODULE.fullmatch(p) or not isinstance(v, str)
               for p, v in values.items()):
            raise Rejected("only runtime Python modules are allowed")
        try:
            actual = manifest(values)
        except UnicodeError:
            raise Rejected("invalid source encoding") from None
        if actual != request[name + "_manifest"]:
            raise Rejected("source manifest mismatch")
    if request["baseline"] != trusted or request["baseline_manifest"] != manifest(trusted):
        raise Rejected("stale baseline")
    if set(request["candidate"]) != set(trusted):
        raise Rejected("module additions and removals require operator review")
    changed = [p for p in trusted if trusted[p] != request["candidate"][p]]
    if not 1 <= len(changed) <= 3:
        raise Rejected("candidate must change one to three modules")
    for path in changed:
        raw = request["candidate"][path].encode("utf-8")
        if len(raw) > MAX_MODULE or "\x00" in request["candidate"][path]:
            raise Rejected("changed module exceeds size limit")
        try:
            ast.parse(raw, filename=path)
        except (SyntaxError, ValueError, RecursionError):
            raise Rejected("candidate does not parse") from None
    if "report" in request or "report_sha256" in request:
        if not isinstance(request.get("report"), dict) or digest(canonical(request["report"])) != request.get("report_sha256"):
            raise Rejected("experiment report hash mismatch")
    return changed


def check_db_paths(path):
    path = Path(path)
    for suffix in ("", "-wal", "-shm", "-journal"):
        child = Path(str(path) + suffix)
        if child.is_symlink() or (child.exists() and not child.is_file()):
            raise Rejected("unsafe database path")
        if child.exists() and child.stat().st_size > MAX_DATABASE:
            raise Rejected("database file exceeds inspection bound")


@contextmanager
def database(path, *, readonly=True):
    check_db_paths(path)
    connection = sqlite3.connect(Path(path).as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                                 uri=True, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA hard_heap_limit=134217728")
        connection.execute("PRAGMA cache_size=-8192")
        deadline = time.monotonic() + 10
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        yield connection
    finally:
        connection.close()


def db_fingerprint(path, ceiling=None):
    with database(path) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise Rejected("canonical database integrity failure")
        owner = db.execute("SELECT substr(value,1,128),length(value) FROM meta WHERE key='owner_id'").fetchone()
        if owner is None or owner[1] > 128:
            raise Rejected("canonical owner missing")
        maximum = db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        upper = maximum if ceiling is None else ceiling
        h = hashlib.sha256()
        count = 0
        oversized = db.execute("SELECT 1 FROM events WHERE id<=? AND (length(CAST(content AS BLOB))>? OR length(CAST(meta AS BLOB))>? OR length(CAST(session AS BLOB))>? OR length(CAST(role AS BLOB))>1024 OR length(CAST(created_at AS BLOB))>1024) LIMIT 1",
                               (upper, MAX_EVENT_BYTES, MAX_EVENT_BYTES, MAX_EVENT_BYTES)).fetchone()
        if oversized:
            raise Rejected("canonical event exceeds inspection bound")
        deadline = time.monotonic() + 10
        for row in db.execute("SELECT id,role,content,session,created_at,meta FROM events WHERE id<=? ORDER BY id", (upper,)):
            if time.monotonic() > deadline:
                raise Rejected("canonical event inspection deadline exceeded")
            h.update(canonical(list(row)) + b"\n")
            count += 1
        return {"owner": str(owner[0]), "max_id": upper, "count": count, "sha256": h.hexdigest()}


def db_schema(path):
    with database(path) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        result = {"tables": {}, "objects": {}}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            result["tables"][table] = [list(r) for r in db.execute("PRAGMA table_info(" + quoted + ")")]
        for row in db.execute("SELECT name,type,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"):
            result["objects"][row[0]] = list(row)[1:]
        return result


def schema_compatible(path, expected):
    current = db_schema(path)
    # Old code includes INSERT INTO cursors VALUES(...), so even nullable added
    # columns break compatibility. Constraints and triggers matter as well.
    for table, columns in expected["tables"].items():
        if current["tables"].get(table) != columns:
            return False
    for name, definition in expected["objects"].items():
        if current["objects"].get(name) != definition:
            return False
    for name, definition in current["objects"].items():
        if name not in expected["objects"] and definition[0] in {"trigger", "index"} and definition[1] in expected["tables"]:
            return False
    return True


def idle(path, now):
    with database(path) as db:
        work = db.execute("SELECT 1 FROM jobs WHERE state='running' OR (state='queued' AND due<=?) LIMIT 1", (now,)).fetchone()
        sending = db.execute("SELECT 1 FROM deliveries WHERE state='sending' LIMIT 1").fetchone()
        return work is None and sending is None


def checkpoint(source, target):
    check_db_paths(source)
    target = Path(target)
    temporary = target.with_suffix(".partial")
    temporary.unlink(missing_ok=True)
    deadline = time.monotonic() + 45
    def progress(*_):
        if time.monotonic() > deadline:
            raise Rejected("checkpoint deadline exceeded")
    with database(source) as src, closing(sqlite3.connect(temporary)) as dst:
        src.backup(dst, pages=128, sleep=0.02, progress=progress)
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise Rejected("checkpoint verification failed")
    with temporary.open("r+b") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    target.chmod(0o600)
    fsync_dir(target.parent)
    return db_fingerprint(target)


def block_uncertain(path, *, restored=False):
    with database(path, readonly=False) as db:
        with db:
            predicate = "state IN ('running','queued')" if restored else "state='running' OR inflight<>0"
            db.execute("UPDATE jobs SET state='blocked',inflight=0,error='Guardian recovery: review before resuming',updated=? WHERE " + predicate, (time.time(),))
            db.execute("UPDATE deliveries SET state='uncertain',error='Guardian recovery: remote outcome requires review' WHERE state IN ('pending','sending')" if restored else
                       "UPDATE deliveries SET state='uncertain',error='Guardian recovery: remote outcome requires review' WHERE state='sending'")


# This fixture is guardian-owned. Candidate tests are never copied into an image.
FIXTURE = '''from pathlib import Path
from marka.store import Store
from marka.queue import Queue
p=Path('/state/fixture.sqlite3')
s=Store(p); q=Queue(p)
s.set_meta('owner_id',424242)
e=s.event('user','guardian fixture immutable input',session='guardian-fixture',meta={'fixture':True})
q.enqueue('guardian future task',424242,source='guardian:future',due=4102444800)
q.deliver('guardian:delivery',424242,'guardian fixture output')
print('guardian fixture complete')
'''


class Docker:
    """All commands come from this fixed adapter and root-owned configuration."""
    def __init__(self, config):
        self.config = config

    def command(self, args, *, timeout=60, check=True):
        process = subprocess.Popen(["docker", *args], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pieces = [bytearray(), bytearray()]
        over = threading.Event()
        bound = 4 * 1024 * 1024
        def reader(stream, result):
            try:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    room = bound - len(result)
                    result.extend(chunk[:max(0, room)])
                    if len(chunk) > room:
                        over.set()
                        break
            finally:
                stream.close()
        readers = [threading.Thread(target=reader, args=(stream, pieces[i]), daemon=True)
                   for i, stream in enumerate((process.stdout, process.stderr))]
        for thread in readers:
            thread.start()
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if over.is_set():
                    raise Rejected("Docker output exceeded bound")
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired("docker", timeout)
                if args and args[0] in {"run", "build"} and getattr(self, "interrupted", lambda: False)():
                    raise Rejected("owner recovery command interrupted validation")
                time.sleep(0.03)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for thread in readers:
                thread.join(timeout=2)
        if over.is_set():
            raise Rejected("Docker output exceeded bound")
        result = subprocess.CompletedProcess(["docker", *args], process.returncode,
                                             bytes(pieces[0]), bytes(pieces[1]))
        if check and result.returncode:
            raise Rejected("Docker operation failed")
        return result

    def repair_runner(self):
        runner = self.config.get("runner_container")
        if not runner:
            return
        socket = Path(runner["socket_path"])
        if socket.exists():
            return
        row = json.loads(self.command(["inspect", runner["name"]]).stdout)[0]
        if row["Image"] != runner["image"]:
            raise Rejected("runner image changed externally")
        self.command(["restart", "--time", "10", runner["name"]], timeout=30)

    def inspect(self):
        result = self.command(["inspect", self.config["container"]["name"]], check=False)
        if result.returncode:
            return None
        row = json.loads(result.stdout)[0]
        return {"image": row["Image"], "running": row["State"]["Running"],
                "oom": row["State"].get("OOMKilled", False),
                "restarts": row.get("RestartCount", 0), "exit": row["State"]["ExitCode"]}

    def stop(self):
        row = self.inspect()
        if row and row["running"]:
            self.command(["stop", "--time", "30", self.config["container"]["name"]], timeout=45)

    def launch(self, image):
        if not IMAGE.fullmatch(image):
            raise Rejected("unpinned image refused")
        cfg = self.config["container"]
        self.repair_runner()
        self.command(["rm", "-f", cfg["name"]], check=False)
        args = ["run", "-d", "--name", cfg["name"], "--restart=no", "--read-only", "--user=10001:10001",
                "--network", cfg.get("network", "none"), "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                "--pids-limit", str(cfg.get("pids", 128)), "--memory", cfg.get("memory", "1g"),
                "--cpus", str(cfg.get("cpus", "1.0")), "--tmpfs", cfg.get("tmpfs", "/tmp:size=128m,mode=1777"),
                "--log-driver=json-file", "--log-opt=max-size=10m", "--log-opt=max-file=3"]
        for mount in cfg["mounts"]:
            text = "type={type},source={source},target={target}".format(**mount)
            if mount.get("readonly"):
                text += ",readonly"
            args += ["--mount", text]
        for name, value in cfg.get("environment", {}).items():
            args += ["--env", name + "=" + str(value)]
        args += [image, "run"]
        self.command(args)

    def build(self, stage, image):
        if not IMAGE.fullmatch(image):
            raise Rejected("unpinned build image refused")
        original = json.loads(self.command(["image", "inspect", image]).stdout)[0]
        if original.get("Id") != image or not isinstance(original.get("RootFS", {}).get("Layers"), list):
            raise Rejected("pinned build image metadata mismatch")
        # BuildKit interprets FROM sha256:<image-id> as a registry image named
        # "sha256", not as a local content ID. Create our own temporary tag,
        # verify its exact ID, and bind the result back to the original layers.
        base_tag = "marka-guardian-base:" + image[7:39] + "-" + digest(str(Path(stage).resolve()).encode())[:16]
        tag = "marka-guardian-candidate:" + Path(stage).name
        self.command(["tag", image, base_tag])
        try:
            pinned = json.loads(self.command(["image", "inspect", base_tag]).stdout)[0]
            if pinned.get("Id") != image or pinned.get("RootFS") != original["RootFS"]:
                raise Rejected("temporary base tag differs from pinned image")
            dockerfile = ("FROM " + base_tag + "\nCOPY src/marka/ /app/src/marka/\n"
                          "COPY src/marka/ /opt/venv/lib/python3.11/site-packages/marka/\n")
            atomic(Path(stage) / "Dockerfile", dockerfile.encode())
            self.command(["build", "--network=none", "--pull=false", "--tag", tag, str(stage)], timeout=600)
            result = json.loads(self.command(["image", "inspect", tag]).stdout)[0]
            candidate = result.get("Id", "")
            layers = result.get("RootFS", {}).get("Layers", [])
            baseline_layers = original["RootFS"]["Layers"]
            if not IMAGE.fullmatch(candidate) or layers[:len(baseline_layers)] != baseline_layers:
                raise Rejected("candidate image does not preserve pinned base layers")
            return candidate
        finally:
            self.command(["image", "rm", base_tag], check=False)

    def validate(self, image, stage):
        stage = Path(stage)
        fixture_dir = stage / "fixture-state"
        fixture_dir.mkdir(exist_ok=True)
        fixture_dir.chmod(0o700)
        if os.name != "nt":
            os.chown(fixture_dir, 10001, 10001)
        script = stage / "fixture.py"
        atomic(script, FIXTURE.encode(), 0o444)
        name = "marka-guardian-check-" + stage.name
        common = ["run", "--name", name, "--network=none", "--log-driver=none", "--read-only", "--user=10001:10001",
                  "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--pids-limit=128",
                  "--memory=1g", "--cpus=1", "--tmpfs=/tmp:size=128m,mode=1777", "--entrypoint=python"]
        evidence = {}
        try:
            result = self.command(common + [image, "-m", "unittest", "discover", "-s", "/app/tests", "-v"],
                                  timeout=self.config.get("test_timeout", 600), check=False)
            observed = json.loads(self.command(["inspect", name]).stdout)[0]["State"]
            text = (result.stdout + result.stderr).decode("utf-8", "replace")
            match = re.search(r"Ran (\d+) tests? in", text)
            count = int(match.group(1)) if match else 0
            evidence["tests"] = count
            evidence["tests_output_sha256"] = digest(result.stdout + result.stderr)
            if result.returncode or observed["Running"] or observed["ExitCode"] != 0 or observed.get("OOMKilled") or count < self.config.get("minimum_tests", 390):
                raise Rejected("independent regression checks failed")
            self.command(["rm", name])
            result = self.command(common + ["--mount", f"type=bind,source={fixture_dir},target=/state",
                                           "--mount", f"type=bind,source={script},target=/guardian-fixture.py,readonly",
                                           image, "/guardian-fixture.py"], timeout=45, check=False)
            observed = json.loads(self.command(["inspect", name]).stdout)[0]["State"]
            if result.returncode or observed["Running"] or observed["ExitCode"] != 0 or observed.get("OOMKilled"):
                raise Rejected("independent fixture process failed")
            fixture = fixture_dir / "fixture.sqlite3"
            fingerprint = db_fingerprint(fixture)
            with database(fixture) as db:
                event = db.execute("SELECT role,content,session FROM events").fetchall()
                jobs = db.execute("SELECT prompt,chat_id,source,state,due FROM jobs").fetchall()
                deliveries = db.execute("SELECT source,chat_id,text,state FROM deliveries").fetchall()
                valid = ([tuple(r) for r in event] == [("user", "guardian fixture immutable input", "guardian-fixture")]
                         and [tuple(r) for r in jobs] == [("guardian future task", 424242, "guardian:future", "queued", 4102444800.0)]
                         and [tuple(r) for r in deliveries] == [("guardian:delivery", 424242, "guardian fixture output", "pending")]
                         and fingerprint["owner"] == "424242")
            if not valid:
                raise Rejected("independent fixture database mismatch")
            evidence["fixture"] = fingerprint
            return evidence
        finally:
            self.command(["rm", "-f", name], check=False)

    def remove_image(self, image):
        if IMAGE.fullmatch(image):
            self.command(["image", "rm", image], check=False)


class Guardian:
    def __init__(self, config, docker=None, *, now=time.time, free=None):
        self.cfg = config
        self.now = now
        self.free = free or (lambda path: shutil.disk_usage(path).free)
        self.root = Path(config["root_dir"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise Rejected("guardian directory cannot be a symlink")
        if not root_protected(self.root.stat(), private=True):
            raise Rejected("guardian directory must be root private")
        self.state_file = self.root / "controller.json"
        self.db = Path(config["state_path"]) / "marka.sqlite3"
        self.docker = docker or Docker(config)
        if isinstance(self.docker, Docker):
            self.docker.interrupted = self.pending_control
        self.status = Path(config["status_path"])
        self.status.parent.mkdir(parents=True, exist_ok=True)
        if self.state_file.exists():
            self.state = json_object(read_regular(self.state_file, 20 * 1024 * 1024, trusted=True))
        else:
            initial = sources_from(config["trusted_source_dir"])
            fallback = sources_from(config.get("fallback_source_dir", config["trusted_source_dir"]))
            self.state = {"version": 1, "phase": "accepted", "current_image": config["current_image"],
                          "current_sources": initial, "fallback_sources": fallback, "fallback_image": config["fallback_image"],
                          "previous_image": "", "previous_sources": {}, "active": None, "seen": {},
                          "rejected_manifests": [], "last_control": 0, "recovery_attempts": 0,
                          "started": now(), "expected_boot_started": 0, "updated": now(), "reason": "initialized"}
            self.save()

    def initialize_checkpoint(self):
        """Call under the guardian lock before its first observation loop."""
        if self.state.get("checkpoint"):
            # A reserve consumed by an earlier disk-full recovery must not
            # prevent the independent watchdog from restarting afterwards.
            try:
                self.ensure_recovery_reserve()
            except Rejected as exc:
                if str(exc) != "insufficient space to protect emergency reserve":
                    raise
            return
        self.disk_check()
        target = self.root / "bootstrap.sqlite3"
        self.state["fingerprint"] = checkpoint(self.db, target)
        self.state["schema"] = db_schema(target)
        if self.state["fingerprint"]["owner"] != str(self.cfg["owner_id"]):
            raise Rejected("bootstrap owner mismatch")
        self.state["checkpoint"] = str(target)
        self.save()
        self.ensure_recovery_reserve()

    def ensure_recovery_reserve(self):
        """Preallocate emergency space outside every mutable container mount."""
        checkpoint_bytes = Path(self.state["checkpoint"]).stat().st_size
        wanted = int(self.cfg.get("recovery_reserve_bytes", min(512 * 1024**2, max(128 * 1024**2, checkpoint_bytes * 2 + 32 * 1024**2))))
        if wanted == 0:  # Explicit operator option, used by small synthetic tests.
            return
        if not 128 * 1024**2 <= wanted <= 512 * 1024**2:
            raise Rejected("recovery reserve must be 128 to 512 MiB")
        target = self.root / "recovery-reserve.bin"
        if target.exists() or target.is_symlink():
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode) or not root_protected(info, private=True):
                raise Rejected("recovery reserve is not protected")
            if info.st_size >= wanted:
                return
            target.unlink()
        reserve = max(RESERVE, int(self.cfg.get("disk_reserve_bytes", RESERVE)))
        if self.free(self.root) < reserve + wanted + checkpoint_bytes:
            raise Rejected("insufficient space to protect emergency reserve")
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if hasattr(os, "posix_fallocate"):
                os.posix_fallocate(fd, 0, wanted)
            else:
                block = b"\0" * (1024 * 1024)
                for _ in range(wanted // len(block)):
                    os.write(fd, block)
                if wanted % len(block):
                    os.write(fd, block[:wanted % len(block)])
            os.fsync(fd)
        finally:
            os.close(fd)
        fsync_dir(self.root)

    def release_recovery_reserve(self, checkpoint_bytes):
        if self.free(Path(self.cfg["state_path"])) >= checkpoint_bytes + 32 * 1024**2:
            return False
        target = self.root / "recovery-reserve.bin"
        if not target.exists() and not target.is_symlink():
            return False
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or not root_protected(info, private=True):
            raise Rejected("unsafe emergency reserve")
        if self.root.stat().st_dev != Path(self.cfg["state_path"]).stat().st_dev:
            raise Rejected("emergency reserve is on a different filesystem")
        target.unlink()
        fsync_dir(self.root)
        return True

    def save(self):
        backup = (self.state.get("active") or {}).get("checkpoint") or self.state.get("checkpoint")
        if backup:
            self.release_recovery_reserve(Path(backup).stat().st_size)
        self.state["updated"] = self.now()
        atomic(self.state_file, canonical(self.state))
        active = self.state.get("active") or {}
        public = {key: self.state.get(key) for key in ("version", "phase", "current_image", "fallback_image", "reason", "updated")}
        public["request_id"] = active.get("request_id", "") or self.state.get("last_result", {}).get("request_id", "")
        public["last_result"] = self.state.get("last_result", {})
        atomic(self.status, canonical(public), 0o644)

    def phase(self, phase, reason):
        self.state["phase"] = phase
        self.state["reason"] = reason
        self.save()

    def owner_source(self, source):
        with database(self.cfg["bridge_journal"]) as db:
            row = db.execute("SELECT owner_id,control FROM updates WHERE update_id=?", (int(source.split(":")[1]),)).fetchone()
            return bool(row and row[0] == self.cfg["owner_id"] and row[1] == "")

    def controls(self):
        with database(self.cfg["bridge_journal"]) as db:
            return [(r[0], r[1]) for r in db.execute("SELECT update_id,control FROM updates WHERE update_id>? AND owner_id=? AND control IN ('rescue','rollback') ORDER BY update_id LIMIT 20",
                                                    (self.state["last_control"], self.cfg["owner_id"]))]

    def pending_control(self):
        # Called while a bounded Docker child runs, so /rescue can interrupt
        # validation instead of waiting for its whole test timeout.
        now = time.monotonic()
        if now < getattr(self, "_next_control_check", 0):
            return False
        self._next_control_check = now + 1
        try:
            return bool(self.controls())
        except (OSError, sqlite3.Error, Rejected):
            return False

    def disk_check(self):
        reserve = max(RESERVE, int(self.cfg.get("disk_reserve_bytes", RESERVE)))
        # Room for the next consistent backup and a small source-only overlay.
        need = reserve + (self.db.stat().st_size if self.db.exists() else 0) * 2 + MAX_REQUEST * 4
        for path in (self.root, Path(self.cfg["state_path"])):
            if self.free(path) < need:
                raise Rejected("disk reserve would be violated")

    def cleanup_stages(self):
        """Retain the active proposal and the one currently referenced backup."""
        keep = {str(Path(self.state["checkpoint"]).parent)} if self.state.get("checkpoint") else set()
        active = self.state.get("active") or {}
        if active.get("stage"):
            keep.add(active["stage"])
        for child in self.root.glob("candidate-*"):
            if str(child) in keep:
                continue
            if child.is_symlink() or not child.is_dir() or child.parent.resolve() != self.root.resolve():
                raise Rejected("unsafe guardian stage")
            # Only exact stage names created by this controller are eligible.
            if IDENT.fullmatch(child.name.removeprefix("candidate-")):
                shutil.rmtree(child)
        fsync_dir(self.root)

    def capture(self, path):
        raw = read_regular(path, MAX_REQUEST)
        request = json_object(raw)
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not IDENT.fullmatch(request_id) or Path(path).name != request_id + ".json":
            raise Rejected("request filename identity mismatch")
        if request_id in self.state["seen"]:
            return False
        self.disk_check()
        stage = self.root / ("candidate-" + request_id)
        stage.mkdir(mode=0o700, exist_ok=False)
        atomic(stage / "request.json", raw)
        self.state["active"] = {"request_id": request_id, "stage": str(stage), "captured_hash": digest(raw),
                                "requested": self.now(), "rollback_image": self.state["current_image"],
                                "rollback_sources": self.state["current_sources"]}
        self.phase("validating", "request captured")
        # The root-owned capture is now durable. Release the bot's bounded
        # outgoing queue, without following or deleting any symlink target.
        try:
            if digest(read_regular(path, MAX_REQUEST)) == digest(raw):
                Path(path).unlink()
                fsync_dir(Path(path).parent)
        except (OSError, Rejected):
            pass
        return True

    def request(self):
        active = self.state["active"]
        raw = read_regular(Path(active["stage"]) / "request.json", MAX_REQUEST, trusted=True)
        if digest(raw) != active["captured_hash"]:
            raise Rejected("captured request changed")
        return json_object(raw)

    def reject(self, reason):
        active = self.state.get("active")
        if active:
            self.state["seen"][active["request_id"]] = "rejected"
            candidate = active.get("candidate_manifest")
            if candidate:
                self.state["rejected_manifests"] = (self.state["rejected_manifests"] + [candidate])[-500:]
            image = active.get("candidate_image")
            if image and image not in {self.state["current_image"], self.state["fallback_image"], self.state.get("previous_image")}:
                self.docker.remove_image(image)
            self.state["last_result"] = {"request_id": active["request_id"], "phase": "rejected", "reason": reason}
        self.phase("rejected", reason)
        self.state["active"] = None
        self.save()
        self.cleanup_stages()

    def check_installed(self, allowed):
        observed = self.docker.inspect()
        if observed and observed["image"] not in allowed:
            raise Rejected("installed image differs from protected release record")
        return observed

    def begin_recovery(self, reason):
        backup = (self.state.get("active") or {}).get("checkpoint") or self.state.get("checkpoint")
        if backup:
            # Free emergency blocks before trying to persist this transition:
            # a completely full filesystem cannot fsync a new state document.
            self.release_recovery_reserve(Path(backup).stat().st_size)
        if self.state.get("recovery_attempts", 0) >= 2:
            self.phase("manual_intervention", "bounded recovery attempts exhausted")
            return
        active = self.state.get("active")
        if not active:
            image = self.state.get("previous_image") or self.state["fallback_image"]
            sources = self.state.get("previous_sources") or self.state["fallback_sources"]
            if image == self.state["current_image"]:
                image, sources = self.state["fallback_image"], self.state["fallback_sources"]
            self.state["active"] = {"request_id": "", "rollback_image": image, "rollback_sources": sources,
                                    "checkpoint": self.state.get("checkpoint", ""), "fingerprint": self.state.get("fingerprint"),
                                    "schema": self.state.get("schema")}
        self.state["recovery_attempts"] = self.state.get("recovery_attempts", 0) + 1
        self.phase("rolling_back", reason)

    def healthy(self, image, *, grace=False):
        observed = self.docker.inspect()
        if not observed or observed["image"] != image or not observed["running"] or observed["oom"] or observed["restarts"]:
            return False, "container exited or changed"
        try:
            fingerprint = self.state.get("fingerprint")
            active = self.state.get("active") or {}
            fingerprint = active.get("fingerprint") or fingerprint
            current = db_fingerprint(self.db, fingerprint["max_id"] if fingerprint else None)
            if fingerprint and current != fingerprint:
                return False, "canonical history changed"
            expected_schema = active.get("schema") or self.state.get("schema")
            if expected_schema and not schema_compatible(self.db, expected_schema):
                return False, "canonical schema is incompatible"
            if current["owner"] != str(self.cfg["owner_id"]):
                return False, "canonical owner changed"
            if grace:
                return True, "startup grace"
            heartbeat = json_object(read_regular(Path(self.cfg["state_path"]) / "heartbeat.json", 8192))
            if heartbeat.get("version") != 1 or heartbeat.get("phase") != "running":
                return False, "heartbeat unavailable"
            tick = heartbeat.get("tick")
            if not isinstance(tick, (int, float)) or not 0 <= self.now() - tick <= self.cfg.get("heartbeat_timeout", 30):
                return False, "event loop heartbeat stale"
            activated = active.get("activated", self.state.get("expected_boot_started", 0))
            started = heartbeat.get("started")
            if not isinstance(started, (int, float)) or not activated - 2 <= started <= self.now():
                return False, "heartbeat belongs to earlier process"
            with database(self.db) as db:
                past = db.execute("SELECT 1 FROM jobs WHERE state='running' AND deadline>0 AND deadline<? LIMIT 1",
                                  (self.now() - self.cfg.get("heartbeat_timeout", 30),)).fetchone()
                if past:
                    return False, "running task exceeded durable deadline"
            return True, "healthy"
        except (OSError, ValueError, TypeError, MemoryError, sqlite3.Error, Rejected):
            return False, "canonical database or heartbeat unavailable"

    def restore(self):
        active = self.state["active"]
        self.check_installed({self.state["current_image"], active["rollback_image"],
                              active.get("candidate_image", "")})
        self.docker.stop()
        backup = active.get("checkpoint") or self.state.get("checkpoint")
        expected = active.get("fingerprint") or self.state.get("fingerprint")
        if backup:
            self.release_recovery_reserve(Path(backup).stat().st_size)
        restored = False
        try:
            if active.get("force_restore"):
                raise Rejected("owner requested checkpoint restoration")
            actual = db_fingerprint(self.db, expected["max_id"] if expected else None)
            if expected and actual != expected:
                raise Rejected("canonical history differs")
            expected_schema = active.get("schema") or self.state.get("schema")
            if expected_schema and not schema_compatible(self.db, expected_schema):
                raise Rejected("canonical schema is incompatible")
            block_uncertain(self.db, restored=False)
            if expected and db_fingerprint(self.db, expected["max_id"]) != expected:
                raise Rejected("canonical history changed during recovery")
        except (OSError, ValueError, TypeError, MemoryError, sqlite3.Error, Rejected):
            if not backup or not Path(backup).is_file():
                raise Rejected("verified recovery checkpoint unavailable") from None
            if expected and db_fingerprint(backup) != expected:
                raise Rejected("recovery checkpoint mismatch")
            quarantine = self.root / ("quarantine-" + uuid.uuid4().hex)
            quarantine.mkdir(mode=0o700)
            for suffix in ("", "-wal", "-shm", "-journal"):
                item = Path(str(self.db) + suffix)
                if item.exists() or item.is_symlink():
                    os.replace(item, quarantine / (self.db.name + suffix))
            atomic_copy(backup, self.db)
            if os.name != "nt":
                os.chown(self.db, 10001, 10001)
            restored = True
        if restored:
            block_uncertain(self.db, restored=True)
        self.docker.launch(active["rollback_image"])
        self.state["current_image"] = active["rollback_image"]
        self.state["current_sources"] = active["rollback_sources"]
        self.state["started"] = self.now()
        self.state["expected_boot_started"] = self.now()
        self.state["previous_image"] = ""
        self.state["previous_sources"] = {}
        request_id = active.get("request_id", "")
        if request_id:
            self.state["seen"][request_id] = "recovered"
            if active.get("candidate_manifest"):
                self.state["rejected_manifests"] = (self.state["rejected_manifests"] + [active["candidate_manifest"]])[-500:]
        self.state["last_result"] = {"request_id": request_id, "phase": "recovered", "restored_database": restored,
                                     "reason": self.state["reason"]}
        self.state["active"] = None
        self.phase("recovered", "known-good image restored")
        image = active.get("candidate_image")
        if image and image not in {self.state["current_image"], self.state["fallback_image"]}:
            self.docker.remove_image(image)
        self.cleanup_stages()

    def tick(self):
        """One bounded transition. Restarting this process resumes saved phases."""
        controls = self.controls()
        if controls:
            self.state["last_control"] = controls[-1][0]
            self.state["recovery_attempts"] = 0
            self.begin_recovery("owner recovery command")
            if self.state.get("active"):
                self.state["active"]["force_restore"] = any(command == "rescue" for _, command in controls)
                self.save()
        phase = self.state["phase"]
        if phase == "manual_intervention":
            return
        active = self.state.get("active")
        if phase == "rolling_back":
            try:
                self.restore()
            except (OSError, ValueError, sqlite3.Error, Rejected, subprocess.TimeoutExpired):
                self.phase("manual_intervention", "recovery needs operator inspection")
            return
        if active and phase == "validating":
            try:
                request = self.request()
                validate_request(request, self.state["current_sources"], self.owner_source)
                active["candidate_manifest"] = request["candidate_manifest"]
                if request["candidate_manifest"] in self.state["rejected_manifests"]:
                    raise Rejected("candidate was already rejected")
                self.disk_check()
                for path, content in request["candidate"].items():
                    target = Path(active["stage"]) / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    atomic(target, content.encode(), 0o644)
                # Rebase each complete source overlay on the fixed initial image
                # to avoid an ever-growing dependency chain between candidates.
                active["candidate_image"] = self.docker.build(active["stage"], self.cfg["current_image"])
                self.save()
                active["evidence"] = self.docker.validate(active["candidate_image"], active["stage"])
                self.disk_check()
                self.phase("waiting_idle", "independent acceptance passed")
            except (OSError, ValueError, sqlite3.Error, Rejected, subprocess.TimeoutExpired) as exc:
                self.reject(str(exc) if isinstance(exc, Rejected) else "candidate validation failed")
            return
        if active and phase == "waiting_idle":
            if self.now() - active["requested"] > self.cfg.get("idle_timeout", 7200):
                self.reject("idle boundary deadline exceeded")
                return
            observed = self.docker.inspect()
            if not observed or observed["image"] != self.state["current_image"]:
                self.reject("installed container changed externally")
                return
            okay, reason = self.healthy(self.state["current_image"], grace=self.now() - self.state.get("started", 0) < self.cfg.get("startup_grace", 60))
            if not okay:
                self.begin_recovery(reason)
                return
            if idle(self.db, self.now()):
                self.disk_check()
                self.phase("checkpoint", "idle boundary reached")
            return
        if active and phase == "checkpoint":
            self.check_installed({active["rollback_image"]})
            self.docker.stop()
            if not idle(self.db, self.now()):
                self.docker.launch(active["rollback_image"])
                self.phase("waiting_idle", "work arrived before stop")
                return
            active["checkpoint"] = str(Path(active["stage"]) / "before.sqlite3")
            active["fingerprint"] = checkpoint(self.db, active["checkpoint"])
            active["schema"] = db_schema(active["checkpoint"])
            self.state["checkpoint"] = active["checkpoint"]
            self.state["fingerprint"] = active["fingerprint"]
            self.state["schema"] = active["schema"]
            self.phase("activating", "verified checkpoint saved")
            self.cleanup_stages()
            return
        if active and phase == "activating":
            observed = self.docker.inspect()
            if observed and observed["image"] not in {active["rollback_image"], active["candidate_image"]}:
                self.phase("manual_intervention", "unexpected container image during activation")
                return
            # An activation interrupted after launch is deliberately restarted;
            # bridge receipts make ambiguous external effects non-retriable.
            if observed and observed["image"] == active["candidate_image"]:
                self.begin_recovery("guardian restarted during activation")
                return
            active["activated"] = self.now()
            self.save()
            self.docker.launch(active["candidate_image"])
            self.phase("probation", "candidate activated")
            return
        if active and phase == "probation":
            age = self.now() - active["activated"]
            okay, reason = self.healthy(active["candidate_image"], grace=age < self.cfg.get("startup_grace", 60))
            if not okay:
                self.begin_recovery(reason)
            elif age >= self.cfg.get("probation_seconds", 120):
                request = self.request()
                old_previous = self.state.get("previous_image")
                self.state["previous_image"] = active["rollback_image"]
                self.state["previous_sources"] = active["rollback_sources"]
                self.state["current_image"] = active["candidate_image"]
                self.state["current_sources"] = request["candidate"]
                self.state["started"] = active["activated"]
                self.state["expected_boot_started"] = active["activated"]
                self.state["seen"][active["request_id"]] = "accepted"
                self.state["last_result"] = {"request_id": active["request_id"], "phase": "accepted",
                                             "manifest": active["candidate_manifest"], "evidence": active["evidence"]}
                self.state["active"] = None
                self.state["recovery_attempts"] = 0
                self.phase("accepted", "candidate passed probation")
                if old_previous and old_previous not in {self.state["current_image"], self.state["previous_image"], self.state["fallback_image"], self.cfg["current_image"]}:
                    self.docker.remove_image(old_previous)
            return
        # The stable watchdog remains active after a successful release.
        if self.now() - self.state.get("started", 0) >= self.cfg.get("startup_grace", 60):
            okay, reason = self.healthy(self.state["current_image"])
            if not okay:
                self.begin_recovery(reason)
                return
        for path in (p for p in sorted(Path(self.cfg["inbox"]).glob("*.json")) if p.stem not in self.state["seen"]):
            if not IDENT.fullmatch(path.stem) or path.stem in self.state["seen"]:
                continue
            try:
                if self.capture(path):
                    return
            except (OSError, ValueError, Rejected):
                self.state["seen"][path.stem] = "rejected"
                self.state["last_result"] = {"request_id": path.stem, "phase": "rejected", "reason": "request capture refused"}
                self.save()
                try:
                    path.unlink()
                    fsync_dir(path.parent)
                except OSError:
                    pass


def load_config(path):
    config = json_object(read_regular(path, 128 * 1024, trusted=True))
    if config.get("version") != 1:
        raise Rejected("unsupported guardian configuration")
    for key in ("current_image", "fallback_image"):
        if not isinstance(config.get(key), str) or not IMAGE.fullmatch(config[key]):
            raise Rejected("exact pinned image IDs required")
    for key in ("trusted_source_dir", "state_path", "bridge_journal", "root_dir", "inbox", "status_path"):
        if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
            raise Rejected("absolute configured path required")
    if type(config.get("owner_id")) is not int or config["owner_id"] <= 0:
        raise Rejected("configured owner required")
    container = config.get("container", {})
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container.get("name", "")) or not container.get("mounts"):
        raise Rejected("fixed container specification required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container.get("network", "none")):
        raise Rejected("fixed network required")
    for mount in container["mounts"]:
        if mount.get("type") not in {"bind", "volume"} or any(not isinstance(mount.get(key), str) or "," in mount[key] or "\n" in mount[key] for key in ("source", "target")):
            raise Rejected("invalid fixed mount")
        if not mount["target"].startswith("/") or (mount["type"] == "bind" and not Path(mount["source"]).is_absolute()):
            raise Rejected("absolute fixed mount required")
    if "runner_container" in config:
        runner = config["runner_container"]
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", runner.get("name", ""))
                or not IMAGE.fullmatch(runner.get("image", ""))
                or not Path(runner.get("socket_path", "")).is_absolute()):
            raise Rejected("fixed runner identity and socket required")
    return config


@contextmanager
def lock(path):
    if os.name == "nt":
        raise Rejected("host guardian requires Linux flock")
    import fcntl
    with open(path, "a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if os.name != "nt" and os.geteuid() != 0:
        raise Rejected("guardian must be run by root")
    config = load_config(args.config)
    root = Path(config["root_dir"])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or not root_protected(root.stat(), private=True):
        raise Rejected("guardian directory must be root private")
    with lock(root / "guardian.lock"):
        guardian = Guardian(config)
        guardian.initialize_checkpoint()
        while True:
            try:
                guardian.tick()
            except (OSError, ValueError, sqlite3.Error, Rejected, subprocess.TimeoutExpired):
                if guardian.state["phase"] in {"checkpoint", "activating", "probation"}:
                    guardian.begin_recovery("interrupted upgrade operation")
                else:
                    guardian.state["reason"] = "independent service temporarily unavailable"
                    guardian.save()
            if args.once:
                break
            time.sleep(3)


if __name__ == "__main__":
    main()
