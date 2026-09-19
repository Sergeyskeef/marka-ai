"""Export verified experiment evidence to an independent, operator-enabled guardian.

This module cannot install code. The guardian owns deployment, independent tests,
known-good images and recovery; runtime evidence is never its trust anchor.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .evolution import Evolution


MAX_REQUEST = 4 * 1024 * 1024
PHASES = {"requested", "validating", "waiting_idle", "checkpoint", "activating", "probation", "accepted",
          "rolling_back", "recovered", "rejected", "manual_intervention"}


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def manifest(sources) -> str:
    return hashlib.sha256(canonical({name: hashlib.sha256(text.encode("utf-8")).hexdigest()
                                     for name, text in sources.items()})).hexdigest()


class Promotion:
    def __init__(self, settings, store, queue, workspace, *, evolution=None):
        self.settings, self.store, self.queue = settings, store, queue
        self.evolution = evolution or Evolution(settings, workspace)

    def _owner(self, job, sources):
        current = self.queue.get(job["id"])
        owner = self.store.get_meta("owner_id")
        source = current.get("source", "") if current else ""
        if (not current or current["state"] != "running" or current["lease"] != job.get("lease")
                or type(owner) is not int or current["chat_id"] != owner
                or not isinstance(source, str) or not re.fullmatch(r"telegram:[0-9]+", source)
                or current["kind"] not in {"chat", "task", "self_improve", "voice", "image"}
                or current["root_id"] != current["id"]):
            raise ValueError("An upgrade requires an active original owner task, not scheduled or imported instructions")
        receipt = self.store.get_meta("owner-request:" + source)
        if not isinstance(receipt, dict) or receipt != {"job_id": current["id"], "owner_id": owner, "source": source}:
            raise ValueError("Original gateway ownership receipt is missing")
        with self.store._connect() as db:
            rows = db.execute("SELECT id,role,meta FROM events WHERE id IN (" + ",".join("?" for _ in sources[:8]) + ")",
                              sources[:8]).fetchall() if sources else []
        for row in rows:
            meta = json.loads(row["meta"])
            if (row["role"] == "user" and meta.get("job") == current["id"] and not meta.get("imported")
                    and not meta.get("scheduled")):
                return current
        raise ValueError("Upgrade requires the current task's original owner event")

    def _sources(self, identifier, label, report):
        data = self.evolution._archive_file(identifier, label + ".json", MAX_REQUEST)
        try:
            sources = json.loads(data)
        except (ValueError, UnicodeError):
            raise ValueError("Experiment source bundle is invalid") from None
        hashes = report[label + "_hashes"]
        if not isinstance(sources, dict) or set(sources) != set(hashes):
            raise ValueError("Experiment source bundle does not match archived manifest")
        for name, text in sources.items():
            if not isinstance(text, str) or hashlib.sha256(text.encode("utf-8")).hexdigest() != hashes[name]:
                raise ValueError("Experiment source bytes do not match archived digest")
        return {name: text for name, text in sources.items() if re.fullmatch(r"src/marka/[A-Za-z_][A-Za-z0-9_]*\.py", name)}

    def request(self, identifier, job, sources):
        if not self.settings.guarded_upgrades:
            raise ValueError("Guarded installation is not enabled by the operator; the experiment remains available for review")
        current = self._owner(job, sources)
        report, report_bytes = self.evolution._read_report(identifier)
        if report["status"] not in {"regression_passed", "improved_on_provided_case"}:
            raise ValueError("Only a completed passing experiment may request installation")
        if report_bytes != canonical(report):
            raise ValueError("Experiment report must retain its canonical archive bytes")
        for label in ("baseline", "candidate"):
            if not isinstance(report.get(label), dict) or not report[label].get("outcomes"):
                raise ValueError("Experiment is missing completed evaluation evidence")
            try:
                run = json.loads(self.evolution._archive_file(identifier, label + "-run.json", 512 * 1024))
                raw = json.loads(self.evolution._archive_file(identifier, label + "-result.json", 512 * 1024))
                if run["file_hashes"] != report[label + "_hashes"] or self.evolution._parse(raw, run["nonce"]) != report[label]:
                    raise ValueError("Experiment evaluation evidence differs from the report")
            except (KeyError, TypeError, UnicodeError):
                raise ValueError("Experiment evaluation evidence is invalid") from None
        compared, _, _ = self.evolution._compare(report["baseline"], report["candidate"])
        if compared != report["status"]:
            raise ValueError("Experiment status disagrees with its completed test outcomes")
        baseline = self._sources(identifier, "baseline", report)
        candidate = self._sources(identifier, "candidate", report)
        changed = {name for name in baseline.keys() | candidate.keys() if baseline.get(name) != candidate.get(name)}
        if (not baseline or not candidate or not 1 <= len(changed) <= 3
                or changed != set(report["changed_paths"]) or any(name not in candidate or len(candidate[name].encode()) > 60000 for name in changed)):
            raise ValueError("Candidate must preserve the archive and change at most three bounded Python modules")
        baseline_manifest, candidate_manifest = manifest(baseline), manifest(candidate)
        identity = {"job_id": current["id"], "source": current["source"], "experiment_id": identifier,
                    "candidate_manifest": candidate_manifest}
        request_id = hashlib.sha256(canonical(identity)).hexdigest()
        value = {"version": 1, "request_id": request_id, **identity, "objective": report["objective"],
                 "baseline": baseline, "candidate": candidate, "baseline_manifest": baseline_manifest,
                 "report": report, "report_sha256": hashlib.sha256(report_bytes).hexdigest()}
        payload = canonical(value)
        if len(payload) > MAX_REQUEST:
            raise ValueError("Upgrade request exceeds the bounded archive export size")
        inbox = Path(self.settings.upgrade_inbox)
        if inbox.is_symlink() or not inbox.is_dir():
            raise ValueError("Operator upgrade inbox is unavailable")
        target = inbox / (request_id + ".json")
        if target.is_symlink():
            raise ValueError("Upgrade receipt path is unsafe")
        previous = self.store.get_meta("upgrade-request:" + request_id)
        if previous:
            return previous | {"replayed": True}
        if target.exists():
            if target.stat().st_size != len(payload) or target.read_bytes() != payload:
                raise ValueError("Upgrade identity conflicts with an existing request")
        else:
            # Bound queue growth before writing; the protected guardian retains
            # consumed request receipts independently of this mutable directory.
            if sum(1 for _ in inbox.iterdir()) >= 32:
                raise ValueError("Upgrade inbox is full; inspect guardian status before retrying")
            descriptor, name = tempfile.mkstemp(prefix=".upgrade-", suffix=".tmp", dir=inbox)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                if os.name != "nt":
                    directory = os.open(inbox, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)
        receipt = {"request_id": request_id, "experiment_id": identifier, "status": "requested",
                   "candidate_manifest": candidate_manifest, "promotion": "guardian_pending",
                   "installed": False, "limitation": "The independent guardian must validate, install and observe this candidate"}
        self.store.set_meta("upgrade-request:" + request_id, receipt)
        return receipt

    def status(self):
        if not self.settings.upgrade_status:
            return {"enabled": False, "phase": "unconfigured"}
        path = Path(self.settings.upgrade_status)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            return {"enabled": self.settings.guarded_upgrades, "phase": "unavailable"}
        try:
            value = json.loads(path.read_bytes())
            if not isinstance(value, dict) or value.get("version") != 1 or value.get("phase") not in PHASES:
                raise ValueError()
            result = {"enabled": self.settings.guarded_upgrades, "phase": value["phase"]}
            for name in ("request_id", "current_image", "fallback_image"):
                item = value.get(name, "")
                if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_:-]{0,160}", item):
                    result[name] = item
            if type(value.get("updated")) in {int, float} and math.isfinite(value["updated"]):
                result["updated"] = value["updated"]
            # Host failure text can contain paths or private diagnostic material.
            # Expose only a deliberately bounded generic reason, never raw logs.
            from .redact import redact
            if isinstance(value.get("reason"), str):
                result["reason"] = redact(value["reason"])[:500]
            return result
        except (ValueError, OSError, UnicodeError, TypeError, RecursionError):
            return {"enabled": self.settings.guarded_upgrades, "phase": "unavailable"}
