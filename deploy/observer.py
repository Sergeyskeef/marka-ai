#!/usr/bin/env python3
"""Publish allowlisted diagnostics. No request, prompt or model enters commands.

Run by a root-owned oneshot systemd unit. The unprivileged protected bridge
receives ONLY the resulting read-only directory, never Docker or journal access.
Raw logs, messages, environment variables and credential files are not exported.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONTAINERS = ("marka-mark-1", "marka-bridge-1", "marka-sandbox-1")
PHASES = {"accepted", "recovered", "rejected", "manual_intervention", "idle",
          "checking", "probation", "validating", "building", "installing",
          "waiting_idle", "activating", "recovering", "bootstrapping", "other", "unavailable"}
CONFIG_NUMBERS = {"max_steps", "daily_calls", "provider_timeout", "retention_days",
                  "task_max_steps", "task_max_calls", "task_max_seconds"}
REASONS = {"error", "warning", "timeout", "traceback", "connection", "cancelled"}
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
MODULES = frozenset("__init__ __main__ acceptance app archive backup bridge bridge_client cli config engine evaluation evolution health learning media memory_context promotion provider queue redact retrieval sandbox scheduling semantic server_read skills store telegram tools voice voice_api web".split())
MAX_OUTPUT = 2 * 1024 * 1024
DOCKER = "/usr/bin/docker"
DOCKER_PREFIX = (DOCKER, "--host=unix:///var/run/docker.sock")
INSPECT_FORMAT = ('{"running":{{json .State.Running}},"paused":{{json .State.Paused}},'
                  '"restarting":{{json .State.Restarting}},"oom_killed":{{json .State.OOMKilled}},'
                  '"exit_code":{{json .State.ExitCode}},"restart_count":{{json .RestartCount}},'
                  '"image":{{json .Image}}}')
SOURCES = (("guardian_source", Path("/opt/marka-guardian/guardian.py")),
           ("observer_source", Path(__file__).absolute()))
SECTIONS = frozenset({"status", "config", "events", "guardian_source", "observer_source"})


def _protected(info):
    return info.st_uid == 0 and not info.st_mode & 0o022


def run(argv, *, timeout=8):
    """Bound bytes while reading, including a process that never finishes."""
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": "/nonexistent",
           "DOCKER_CONFIG": "/nonexistent"}
    for key in ("SystemRoot", "WINDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, bufsize=0,
                            start_new_session=os.name != "nt")
    mailbox = queue.Queue(maxsize=8)
    stopped = threading.Event()

    def reader(stream, index):
        try:
            while not stopped.is_set():
                block = stream.read(16384)
                while not stopped.is_set():
                    try:
                        mailbox.put((index, block), timeout=0.05)
                        break
                    except queue.Full:
                        pass
                if not block:
                    return
        finally:
            stream.close()

    readers = [threading.Thread(target=reader, args=(stream, index), daemon=True)
               for index, stream in enumerate((proc.stdout, proc.stderr))]
    for worker in readers:
        worker.start()
    chunks, total, finished = [[], []], 0, 0
    deadline = time.monotonic() + timeout
    completed = False
    try:
        while finished < 2:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Diagnostic command timeout")
            try:
                index, block = mailbox.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if not block:
                finished += 1
                continue
            total += len(block)
            if total > MAX_OUTPUT:
                raise ValueError("Diagnostic output limit")
            chunks[index].append(block)
        code = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        completed = True
        return subprocess.CompletedProcess(argv, code, b"".join(chunks[0]), b"".join(chunks[1]))
    finally:
        stopped.set()
        if not completed:
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except ProcessLookupError:
                pass
        proc.wait(timeout=2)
        for worker in readers:
            worker.join(timeout=1)


def protected_bytes(path, maximum=262144):
    path = Path(path)
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Protected input must be regular")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not _protected(info) or info.st_size > maximum:
            raise ValueError("Protected input ownership")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > maximum or (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Protected input limit")
    return raw


def protected_json(path, maximum=262144):
    return json.loads(protected_bytes(path, maximum))


def sanitized_config(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid configuration")
    result = {}
    for key in CONFIG_NUMBERS:
        if type(value.get(key)) is int and 0 <= value[key] <= 1000000:
            result[key] = value[key]
    model = value.get("model")
    if model is None or (isinstance(model, str) and re.fullmatch(r"gpt-[A-Za-z0-9_.-]{1,96}", model)):
        result["model"] = model
    effort = value.get("reasoning_effort")
    if effort is None or (isinstance(effort, str) and effort in EFFORTS):
        result["reasoning_effort"] = effort
    zone = value.get("timezone")
    if isinstance(zone, str) and len(zone) <= 100:
        try:
            if zone != "UTC":
                ZoneInfo(zone)
            result["timezone"] = zone
        except (ValueError, ZoneInfoNotFoundError):
            pass
    if type(value.get("semantic_search")) is bool:
        result["semantic_search"] = value["semantic_search"]
    return result


def log_summary(raw):
    """Extract only fixed error categories and package-frame identifiers."""
    counts = Counter()
    frames = Counter()
    for line in raw.decode("utf-8", "replace").splitlines():
        lower = line.lower()
        for reason in REASONS:
            if re.search(r"\b" + reason + r"\b", lower) or (reason in {"timeout", "connection", "cancelled"}
                                                           and reason + "error" in lower):
                counts[reason] += 1
        # No exception messages, arbitrary file paths, source lines or user data.
        frame = re.search(r'File "[^"\n]*[/\\]marka[/\\]([a-z_]{1,50})\.py", line ([0-9]{1,6})', line)
        if frame and frame[1] in MODULES and int(frame[2]) > 0:
            frames[(frame[1] + ".py", int(frame[2]))] += 1
    return {"categories": dict(sorted(counts.items())),
            "frames": [{"module": module, "line": line, "count": count}
                       for (module, line), count in frames.most_common(20)],
            "raw_logs_exposed": False, "window_seconds": 600, "tail_limit": 200}


def atomic(directory, section, data, now):
    if section not in SECTIONS:
        raise ValueError("Unknown snapshot section")
    raw = json.dumps({"version": 1, "section": section, "generated_at": now,
                      "data": data}, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    if len(raw) > 262144:
        raise ValueError("Snapshot limit")
    descriptor, name = tempfile.mkstemp(prefix="." + section + ".", suffix=".pending", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.chmod(temporary, 0o644)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / (section + ".json"))
        if os.name != "nt":
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _container(value, name):
    if not isinstance(value, dict) or name not in CONTAINERS:
        raise ValueError("Invalid container metadata")
    item = {"name": name, "available": value.get("available") is True}
    if not item["available"]:
        return item
    for key in ("running", "paused", "restarting", "oom_killed"):
        item[key] = value.get(key) is True
    for key, maximum in (("exit_code", 255), ("restart_count", 1000000000)):
        field = value.get(key)
        item[key] = field if type(field) is int and 0 <= field <= maximum else 0
    image = value.get("image")
    if isinstance(image, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        item["image"] = image
    return item


def _guardian(value):
    if not isinstance(value, dict):
        return {"service_active": False, "phase": "unavailable"}
    phase = value.get("phase")
    result = {"service_active": value.get("service_active") is True,
              "phase": phase if isinstance(phase, str) and phase in PHASES else "unavailable"}
    version = value.get("current_runtime_version")
    if isinstance(version, str) and re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", version):
        result["current_runtime_version"] = version
    if value.get("recovery_action") in ("restart", "rollback"):
        result["recovery_action"] = value["recovery_action"]
    incident = value.get("last_incident")
    if isinstance(incident, dict):
        if type(incident.get("at")) in (int, float) and 0 <= incident["at"] <= 1e12:
            result["last_failure_at"] = incident["at"]
        if isinstance(incident.get("component"), str) and incident["component"] in {"startup", "supervisor", "polling", "worker", "delivery", "maintenance", "heartbeat", "signal"}:
            result["last_failure_component"] = incident["component"]
    return result


def _change(containers, guardian, when):
    value = {"containers": containers, "guardian": guardian}
    return {"at": when, "fingerprint": hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(), **value}


def _history(value, now):
    """Rebuild even operator-owned history from allowed fields only."""
    if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
        return []
    previous = value["data"].get("state_changes")
    if not isinstance(previous, list):
        return []
    result = []
    for row in previous[-49:]:
        if not isinstance(row, dict):
            continue
        when, containers = row.get("at"), row.get("containers")
        if type(when) not in {int, float} or not 0 <= when <= now + 60 or not isinstance(containers, list):
            continue
        clean = [_container(item, item["name"]) for item in containers[:3]
                 if isinstance(item, dict) and item.get("name") in CONTAINERS]
        result.append(_change(clean, _guardian(row.get("guardian")), when))
    return result


def collect(root, output):
    if os.geteuid() != 0 or not root.is_absolute() or not output.is_absolute() or any(
            part.is_symlink() for directory in (root, output) for part in (directory, *directory.parents)):
        raise ValueError("Collector requires protected directories")
    root_info = root.stat()
    if not stat.S_ISDIR(root_info.st_mode) or not _protected(root_info):
        raise ValueError("Collector root must be operator owned")
    output.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = output.stat()
    if not _protected(info):
        raise ValueError("Output directory must be operator owned")
    now = time.time()
    disk = shutil.disk_usage("/")
    status = {"scope": "Mark Runtime only", "disk": {"total_bytes": disk.total, "free_bytes": disk.free,
               "used_percent": round(100 * disk.used / disk.total, 1)}, "containers": [], "guardian": {}}
    logs = {"scope": "technical summaries without raw logs or conversations", "services": []}
    for name in CONTAINERS:
        try:
            result = run([*DOCKER_PREFIX, "inspect", "--type=container", "--format=" + INSPECT_FORMAT, name])
            if result.returncode:
                raise ValueError("Container unavailable")
            obj = json.loads(result.stdout)
            status["containers"].append(_container({**obj, "available": True}, name))
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            status["containers"].append({"name": name, "available": False})
            continue
        try:
            result = run([*DOCKER_PREFIX, "logs", "--since=10m", "--tail=200", name])
            summary = log_summary(result.stdout + b"\n" + result.stderr)
            logs["services"].append({"name": name, "available": result.returncode == 0, **summary})
        except (OSError, ValueError, subprocess.SubprocessError):
            logs["services"].append({"name": name, "available": False})
    try:
        result = run(["/usr/bin/systemctl", "is-active", "marka-guardian.service"])
        status["guardian"]["service_active"] = result.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        status["guardian"]["service_active"] = False
    try:
        guardian = protected_json(root / "status/status.json")
        phase = guardian.get("phase") if isinstance(guardian, dict) else None
        status["guardian"]["phase"] = phase if isinstance(phase, str) and phase in PHASES else "other"
        status["guardian"] = _guardian({**status["guardian"],
            "current_runtime_version": guardian.get("current_runtime_version"),
            "last_incident": guardian.get("last_incident"),
            "recovery_action": (guardian.get("last_result") or {}).get("action")})
    except (OSError, ValueError, TypeError):
        status["guardian"]["phase"] = "unavailable"
    config = {"runtime": sanitized_config(protected_json(root / "masks/settings.json")),
              "provider": sanitized_config(protected_json(root / "bridge.json")),
              "access": {"read_only": True, "raw_logs": False, "credentials": False,
                         "user_data": False, "arbitrary_paths": False, "shell": False}}
    # A bounded history of state changes, never a copy of application messages.
    previous = []
    try:
        old = protected_json(output / "events.json")
        previous = _history(old, now)
    except (OSError, ValueError, TypeError, KeyError):
        pass
    change = _change(status["containers"], status["guardian"], now)
    if not previous or previous[-1]["fingerprint"] != change["fingerprint"]:
        previous.append(change)
    logs["state_changes"] = previous[-50:]
    for section, data in (("status", status), ("config", config), ("events", logs)):
        atomic(output, section, data, now)
    for section, path in SOURCES:
        atomic(output, section, protected_bytes(path, 128 * 1024).decode("utf-8"), now)
    return {"ok": True, "sections": 5, "generated_at": now, "free_bytes": disk.free}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/var/lib/marka-guardian"))
    parser.add_argument("--output", type=Path, default=Path("/var/lib/marka-guardian/observability"))
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.root, args.output)))
    except Exception:
        # Do not let captured command output or config errors enter the journal.
        print('{"ok":false,"error":"diagnostic_collection_failed"}')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
