"""Frozen task criteria and bounded checks of runtime-owned evidence.

Criteria proposed by the model are not owner approval and do not prove that the
model understood every requirement. No check in this module executes code.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

MAX_CRITERIA = 12
MAX_CONTRACT_BYTES = 32768
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CONTENT_BYTES = 1024 * 1024
_KEY = "task-criteria:v1:"
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,47}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_READ_ONLY = {"memory.search", "memory.episodes", "memory.read", "memory.source", "memory.related", "memory.entities",
              "workspace.list", "workspace.read", "workspace.find", "web.search", "web.fetch", "skill.search", "skill.inspect",
              "task.list", "task.plan", "task.progress", "task.recall", "task.criteria", "consult", "self.inspect", "self.search", "self.history",
              "self.read_experiment", "self.upgrade_status", "server.inspect", "server.read",
              "connections.list", "connections.check", "server.files"}


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("Criteria must contain bounded JSON values") from None


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value
    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite JSON value")
        return number
    return json.loads(raw, object_pairs_hook=pairs, parse_float=floating,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON value")))


def _pointer(value):
    if not isinstance(value, str) or len(value) > 600 or (value and not value.startswith("/")):
        raise ValueError("JSON pointer must be empty or begin with /")
    parts = value.split("/")[1:] if value else []
    if len(parts) > 12 or any(re.search(r"~(?![01])", item) for item in parts):
        raise ValueError("JSON pointer exceeds supported depth or escaping")
    return [item.replace("~1", "/").replace("~0", "~") for item in parts]


def normalize_criteria(criteria):
    from .redact import redact_value
    from .sandbox import _safe_name, _validate_command
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= MAX_CRITERIA:
        raise ValueError("Declare one to twelve criteria")
    if len(_canonical(criteria)) > 16000 or redact_value(criteria) != criteria:
        raise ValueError("Criteria exceed the safe text budget or contain protected secrets")
    result, names = [], set()
    for item in criteria:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not _ID.fullmatch(item["id"]):
            raise ValueError("Each criterion needs a short unique ASCII id")
        if item["id"] in names:
            raise ValueError("Criterion ids must be unique")
        names.add(item["id"])
        kind = item.get("kind")
        fields = {"artifact": {"id", "kind", "path", "min_bytes", "max_bytes", "sha256"},
                  "text_contains": {"id", "kind", "path", "contains"},
                  "json_matches": {"id", "kind", "path", "assertions"},
                  "command_succeeded": {"id", "kind", "argv"}}.get(kind)
        if fields is None or set(item) - fields:
            raise ValueError("Unknown criterion type or field")
        value = {"id": item["id"], "kind": kind}
        if kind != "command_succeeded":
            value["path"] = _safe_name(item.get("path"))
            if any(part.casefold() in {"auth.json", "settings.json"} for part in value["path"].split("/")):
                raise ValueError("State and credential paths cannot be task artifacts")
        if kind == "artifact":
            minimum, maximum = item.get("min_bytes", 1), item.get("max_bytes", MAX_FILE_BYTES)
            if type(minimum) is not int or type(maximum) is not int or not 0 <= minimum <= maximum <= MAX_FILE_BYTES:
                raise ValueError("Artifact byte bounds are invalid")
            value.update(min_bytes=minimum, max_bytes=maximum)
            if "sha256" in item:
                if not isinstance(item["sha256"], str) or not _HEX.fullmatch(item["sha256"]):
                    raise ValueError("Artifact hash must be SHA-256")
                value["sha256"] = item["sha256"]
        elif kind == "text_contains":
            needles = item.get("contains")
            if (not isinstance(needles, list) or not 1 <= len(needles) <= 16
                    or any(not isinstance(s, str) or not 1 <= len(s) <= 1000 for s in needles)
                    or sum(map(len, needles)) > 8000):
                raise ValueError("Text criteria need one to sixteen bounded literal strings")
            value["contains"] = list(needles)
        elif kind == "json_matches":
            assertions = item.get("assertions")
            if not isinstance(assertions, list) or not 1 <= len(assertions) <= 16:
                raise ValueError("JSON criteria need one to sixteen assertions")
            checks = []
            for assertion in assertions:
                if not isinstance(assertion, dict) or set(assertion) != {"pointer", "equals"}:
                    raise ValueError("JSON assertions require pointer and equals")
                _pointer(assertion["pointer"])
                if len(_canonical(assertion["equals"])) > 2048:
                    raise ValueError("JSON expected value exceeds limit")
                checks.append(_json(_canonical(assertion).decode()))
            value["assertions"] = checks
        else:
            argv = item.get("argv")
            _validate_command(argv, 1)
            if sum(map(len, argv)) > 8000:
                raise ValueError("Command criterion exceeds argv budget")
            value["argv"] = list(argv)
        result.append(value)
    return result


def _validate_contract(value, *, job=None):
    fields = {"version", "job_id", "source", "prompt_sha256", "proposer", "owner_accepted", "frozen_at", "step_number", "criteria", "sha256"}
    if not isinstance(value, dict) or set(value) != fields or len(_canonical(value)) > MAX_CONTRACT_BYTES:
        raise ValueError("Invalid frozen criteria metadata")
    if (value["version"] != 1 or type(value["version"]) is not int or value["proposer"] != "model"
            or value["owner_accepted"] is not False or not isinstance(value["job_id"], str)
            or not 1 <= len(value["job_id"]) <= 80 or (value["source"] is not None and not isinstance(value["source"], str))
            or not isinstance(value["prompt_sha256"], str) or not _HEX.fullmatch(value["prompt_sha256"])
            or type(value["step_number"]) is not int or value["step_number"] < 0
            or type(value["frozen_at"]) not in (int, float) or not math.isfinite(value["frozen_at"])):
        raise ValueError("Invalid frozen criteria identity")
    if normalize_criteria(value["criteria"]) != value["criteria"]:
        raise ValueError("Frozen criteria are not canonical")
    body = {key: item for key, item in value.items() if key != "sha256"}
    if value["sha256"] != _hash(_canonical(body)):
        raise ValueError("Frozen criteria hash mismatch")
    if job is not None and (value["job_id"] != job["id"] or value["source"] != job["source"]
                            or value["prompt_sha256"] != _hash(job["prompt"].encode("utf-8"))):
        raise ValueError("Frozen criteria belong to another request revision")
    return value


def _stored(db, job_id):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone() is None:
        return None
    row = db.execute("SELECT substr(value,1,32769),length(value) FROM meta WHERE key=?", (_KEY + job_id,)).fetchone()
    if row is None:
        return None
    if type(row[1]) is not int or row[1] > MAX_CONTRACT_BYTES or not isinstance(row[0], str):
        raise ValueError("Frozen criteria metadata exceeds limit")
    return _json(row[0])


def get_criteria(queue, job_id):
    """None means absent. Damaged metadata returns an explicit blocking record."""
    try:
        with queue.connection() as db:
            db.execute("BEGIN")
            value = _stored(db, job_id)
            if value is None:
                return None
            job = db.execute("SELECT id,source,prompt FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise ValueError("Frozen criteria task is missing")
            return _validate_contract(value, job=job)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return {"invalid": True, "job_id": job_id, "reason": "criteria_metadata_invalid"}


def freeze_criteria(queue, job_id, lease, criteria):
    """Freeze once, before effectful work, using the active runtime task lease."""
    normalized = normalize_criteria(criteria)
    with queue.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job is None or job["state"] != "running" or not isinstance(lease, str) or not lease or job["lease"] != lease:
            raise ValueError("A current running task lease is required")
        existing = _stored(db, job_id)
        if existing is not None:
            existing = _validate_contract(existing, job=job)
            if existing["criteria"] != normalized:
                raise ValueError("Frozen criteria cannot be replaced, weakened or removed")
            return existing
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone() is None:
            raise ValueError("Canonical task metadata is unavailable")
        # Unknown tools are conservative: freeze first, then perform them.
        names = [row[0] for row in db.execute("SELECT name FROM task_steps WHERE job_id=? LIMIT 2001", (job_id,))]
        if len(names) > 2000:
            raise ValueError("Task evidence exceeds criteria freeze budget")
        try:
            legacy = _json(job["trace"])
        except (ValueError, TypeError, RecursionError):
            raise ValueError("Task trace is unavailable for criteria freeze") from None
        if not isinstance(legacy, list):
            raise ValueError("Task trace must be a list")
        names += [item.get("name") for item in legacy if isinstance(item, dict) and item.get("kind") == "tool"]
        if any(name not in _READ_ONLY for name in names):
            raise ValueError("Criteria must be frozen before effectful work")
        body = {"version": 1, "job_id": job_id, "source": job["source"], "prompt_sha256": _hash(job["prompt"].encode("utf-8")),
                "proposer": "model", "owner_accepted": False, "frozen_at": time.time(), "step_number": job["steps_used"], "criteria": normalized}
        value = body | {"sha256": _hash(_canonical(body))}
        _validate_contract(value, job=job)
        db.execute("INSERT INTO meta(key,value) VALUES(?,?)", (_KEY + job_id, _canonical(value).decode("utf-8")))
        return value


def _object(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or len(value) > 512000:
        return None
    try:
        result = _json(value)
    except (ValueError, TypeError, RecursionError):
        return None
    return result if isinstance(result, dict) else None


def _evidence(trace, expected_artifacts):
    if not isinstance(trace, list) or len(trace) > 4000:
        raise ValueError("Runtime evidence exceeds criteria budget")
    receipts, commands, pending = {}, {}, None
    for item in trace:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "tool":
            if pending and pending[0] == "code.run":
                commands[_canonical(pending[1].get("argv"))] = None
            args = _object(item.get("arguments"))
            pending = (item.get("name"), args) if args is not None else None
        elif item.get("kind") == "observation" and pending:
            name, args = pending
            pending = None
            observed = _object(item.get("content"))
            if name == "code.run":
                commands[_canonical(args.get("argv"))] = observed
            if not observed or observed.get("ok") is not True or not isinstance(observed.get("result"), dict):
                continue
            result = observed["result"]
            if name in {"workspace.write", "workspace.replace", "workspace.read"} and isinstance(result.get("path"), str):
                receipts[result["path"]] = dict(result, _origin="read" if name == "workspace.read" else "output")
            if name in {"code.run", "skill.run"} and isinstance(result.get("artifacts"), list):
                for receipt in result["artifacts"][:200]:
                    if isinstance(receipt, dict) and isinstance(receipt.get("path"), str):
                        receipts[receipt["path"]] = dict(receipt, _origin="output")
    if pending and pending[0] == "code.run":
        commands[_canonical(pending[1].get("argv"))] = None
    if expected_artifacts is not None:
        if not isinstance(expected_artifacts, list) or len(expected_artifacts) > 200:
            raise ValueError("Artifact evidence exceeds criteria budget")
        for receipt in expected_artifacts:
            if isinstance(receipt, dict) and isinstance(receipt.get("path"), str):
                receipts[receipt["path"]] = dict(receipt, _origin="output")
    return receipts, commands


def _file(path, receipt, workspace, *, content=False):
    from .tools import Workspace
    if receipt is None:
        return {"status": "missing", "reason": "task_file_receipt_missing"}, None
    expected_hash, expected_size = receipt.get("sha256"), receipt.get("bytes")
    read_receipt = receipt.get("_origin") == "read"
    if not isinstance(expected_hash, str) or not _HEX.fullmatch(expected_hash) or (not read_receipt and (
            type(expected_size) is not int or not 0 <= expected_size <= MAX_FILE_BYTES)):
        return {"status": "failed", "reason": "invalid_file_receipt"}, None
    if workspace is None:
        return {"status": "missing", "reason": "workspace_unavailable"}, None
    try:
        root = workspace if isinstance(workspace, Workspace) else Workspace(Path(workspace))
        target = root.path(path)
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            bound = MAX_CONTENT_BYTES if content else MAX_FILE_BYTES
            if not stat.S_ISREG(before.st_mode) or before.st_size > bound:
                return {"status": "failed", "reason": "file_type_or_size_limit"}, None
            if not read_receipt and before.st_size != expected_size:
                return {"status": "failed", "reason": "file_size_changed"}, None
            fingerprint, pieces, consumed = hashlib.sha256(), [], 0
            while True:
                block = stream.read(min(65536, bound + 1 - consumed))
                if not block:
                    break
                consumed += len(block)
                if consumed > bound:
                    return {"status": "failed", "reason": "file_changed_during_check"}, None
                fingerprint.update(block)
                if content:
                    pieces.append(block)
            after = os.fstat(stream.fileno())
        current = target.stat(follow_symlinks=False)
        if (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) != (
                after.st_size, after.st_mtime_ns, current.st_ino, current.st_dev):
            return {"status": "failed", "reason": "file_changed_during_check"}, None
        if fingerprint.hexdigest() != expected_hash:
            return {"status": "failed", "reason": "file_hash_changed"}, None
        return {"status": "pass", "reason": "task_file_bytes_verified", "bytes": consumed, "sha256": expected_hash,
                "receipt_origin": "read" if read_receipt else "output"}, b"".join(pieces) if content else None
    except (OSError, ValueError, TypeError):
        return {"status": "failed", "reason": "file_missing_or_unsafe"}, None


def _resolve(document, pointer):
    value = document
    for part in _pointer(pointer):
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]{0,8}", part):
            value = value[int(part)]
        else:
            raise KeyError("JSON path does not exist")
    return value


def _equal(actual, expected):
    if type(actual) is bool or type(expected) is bool:
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_equal(actual[k], expected[k]) for k in actual)
    return actual == expected


def _command(criterion, commands, workspace):
    key = _canonical(criterion["argv"])
    if key not in commands or commands[key] is None:
        return {"status": "missing", "reason": "exact_command_receipt_missing"}
    observed = commands[key]
    if observed.get("ok") is not True:
        return {"status": "failed", "reason": "command_tool_failed"}
    result = observed.get("result")
    if not isinstance(result, dict):
        return {"status": "missing", "reason": "command_result_missing"}
    if result.get("error") or result.get("timed_out") is True or (type(result.get("exit_code")) is int and result["exit_code"] != 0):
        return {"status": "failed", "reason": "command_execution_failed"}
    if (type(result.get("exit_code")) is not int or result.get("argv") != criterion["argv"]
            or not isinstance(result.get("input_manifest"), dict)):
        return {"status": "missing", "reason": "complete_command_receipt_missing"}
    inputs = result["input_manifest"]
    if len(inputs) > 200:
        return {"status": "failed", "reason": "command_input_manifest_invalid"}
    checked, total = 0, 0
    for path, receipt in inputs.items():
        if not isinstance(path, str) or not isinstance(receipt, dict):
            return {"status": "failed", "reason": "command_input_manifest_invalid"}
        size = receipt.get("bytes")
        if type(size) is not int or not 0 <= size <= 512 * 1024:
            return {"status": "failed", "reason": "command_input_manifest_invalid"}
        total += size
        if total > 2 * 1024 * 1024:
            return {"status": "failed", "reason": "command_input_manifest_invalid"}
        if Path(path).suffix.casefold() in {".py", ".js", ".mjs", ".cjs", ".sh"}:
            check, _ = _file(path, receipt, workspace)
            if check["status"] != "pass":
                return {"status": check["status"], "reason": "tested_source_no_longer_matches", "path": path}
            checked += 1
    return {"status": "pass", "reason": "exact_command_succeeded", "exit_code": 0, "verified_code_inputs": checked}


def evaluate_criteria(contract, trace, *, workspace=None, expected_artifacts=None):
    if contract is None:
        return {"status": "missing", "required": False, "completion_allowed": True, "reason": "criteria_not_declared", "checks": []}
    try:
        _validate_contract(contract)
        receipts, commands = _evidence(trace, expected_artifacts)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return {"status": "failed", "required": True, "completion_allowed": False,
                "reason": "criteria_contract_or_evidence_invalid", "checks": []}
    checks = []
    for criterion in contract["criteria"]:
        check = {"id": criterion["id"], "kind": criterion["kind"]}
        kind = criterion["kind"]
        if kind == "command_succeeded":
            check.update(_command(criterion, commands, workspace))
        else:
            check["path"] = criterion["path"]
            outcome, payload = _file(criterion["path"], receipts.get(criterion["path"]), workspace,
                                     content=kind in {"text_contains", "json_matches"})
            check.update(outcome)
            if check["status"] == "pass":
                if kind == "artifact":
                    if not criterion["min_bytes"] <= check["bytes"] <= criterion["max_bytes"]:
                        check.update(status="failed", reason="artifact_byte_contract_failed")
                    elif "sha256" in criterion and criterion["sha256"] != check["sha256"]:
                        check.update(status="failed", reason="artifact_expected_hash_mismatch")
                else:
                    try:
                        text = payload.decode("utf-8-sig")
                        if kind == "text_contains":
                            count = sum(needle in text for needle in criterion["contains"])
                            check.update(matched=count, required=len(criterion["contains"]))
                            if count != len(criterion["contains"]):
                                check.update(status="failed", reason="required_literal_text_missing")
                        else:
                            document = _json(text)
                            matched = 0
                            for assertion in criterion["assertions"]:
                                try:
                                    same = _equal(_resolve(document, assertion["pointer"]), assertion["equals"])
                                except (KeyError, IndexError):
                                    same = False
                                matched += same
                            check.update(matched=matched, required=len(criterion["assertions"]))
                            if matched != len(criterion["assertions"]):
                                check.update(status="failed", reason="json_value_contract_failed")
                    except (UnicodeError, ValueError, RecursionError):
                        check.update(status="failed", reason="file_content_invalid")
        checks.append(check)
    status = "failed" if any(c["status"] == "failed" for c in checks) else "missing" if any(c["status"] == "missing" for c in checks) else "pass"
    return {"status": status, "required": True, "completion_allowed": status == "pass", "contract_sha256": contract["sha256"],
            "proposer": "model", "owner_accepted": False, "checks": checks,
            "scope": "Declared objective checks of runtime evidence; not proof that all owner requirements were understood."}
