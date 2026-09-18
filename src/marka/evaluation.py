"""Observed completion checks and an independent, deterministic acceptance suite.

This module never infers successful actions from an assistant's prose. The suite
is maintained separately from proposed regression tests; its public fixtures are
not a secret or statistically held-out benchmark of model intelligence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

_LIMITATIONS = [
    "Checks establish observed runtime facts, not whether every semantic user requirement was satisfied.",
    "A model's final answer and consultations are not independent evidence.",
    "Queued delivery is not a Telegram delivery receipt; passing code is not proof of all possible behaviors.",
]


def _object(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    return value if isinstance(value, dict) else None


def _target(name, args):
    def identity(field):
        if field in args:
            encoded = json.dumps(args[field], ensure_ascii=False, default=str)
            return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        summary = args.get(field + "_summary")
        digest = summary.get("sha256") if isinstance(summary, dict) else None
        if isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
            return digest
        return None

    if set(args) == {"truncated", "sha256", "preview"} and args.get("truncated") is True:
        # An outer task-ledger snapshot still identifies the complete argument
        # object. It must not collapse different large calls into one target.
        return name + ":snapshot:" + str(args.get("sha256"))
    if name.startswith("workspace.") or name == "self.inspect":
        return name + ":" + str(args.get("path", ""))[:600]
    if name == "code.run":
        # A successful unrelated command must not hide a failed command. Source
        # corrections can write the same script, then rerun the same argv.
        return name + ":" + str(identity("argv"))
    if name == "skill.run":
        target = {key: identity(key) for key in ("name", "parameters", "inputs")}
        return name + ":" + hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()[:16]
    if name == "web.fetch":
        return name + ":" + hashlib.sha256(str(args.get("url", "")).encode()).hexdigest()[:16]
    if name in {"memory.search", "memory.episodes", "web.search"}:
        return name + ":" + hashlib.sha256(str(args.get("query", "")).encode()).hexdigest()[:16]
    return name


def _artifact_check(receipt, workspace):
    from .tools import Workspace
    path = receipt.get("path") if isinstance(receipt, dict) else None
    check = {"kind": "artifact", "target": str(path)[:600], "status": "unverified"}
    if not isinstance(receipt, dict) or not isinstance(path, str):
        return check | {"status": "failed", "reason": "invalid_artifact_receipt"}
    expected_hash, expected_size = receipt.get("sha256"), receipt.get("bytes")
    if (not isinstance(expected_hash, str) or len(expected_hash) != 64
            or any(c not in "0123456789abcdef" for c in expected_hash)
            or type(expected_size) is not int or not 0 <= expected_size <= 20 * 1024 * 1024):
        return check | {"status": "failed", "reason": "invalid_artifact_receipt"}
    if workspace is None:
        return check | {"reason": "workspace_unavailable"}
    try:
        root = workspace if isinstance(workspace, Workspace) else Workspace(Path(workspace))
        target = root.path(path)
        if not target.is_file():
            return check | {"status": "failed", "reason": "artifact_missing"}
        size = target.stat().st_size
        if size != expected_size or size > 20 * 1024 * 1024:
            return check | {"status": "failed", "reason": "artifact_size_changed"}
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            return check | {"status": "failed", "reason": "artifact_hash_changed"}
        return check | {"status": "passed", "sha256": expected_hash, "bytes": size}
    except (OSError, ValueError, TypeError):
        return check | {"status": "failed", "reason": "artifact_unreadable_or_unsafe"}


def verify_completion(trace: list, *, workspace=None, model_outcome="completed", expected_artifacts=None) -> dict:
    """Evaluate runtime-owned observations; never pass model-authored trace data.

    Later success can resolve an earlier failure of the *same* tool/target. File
    receipts are rechecked against the actual latest workspace bytes. This is
    deliberately separate from the model's self-reported outcome.
    """
    latest, receipts, rejections, uncertainties = {}, {}, {}, {}
    pending = None
    observation_count = 0
    if not isinstance(trace, list):
        raise ValueError("Verification requires a runtime trace")
    for item in trace:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "tool":
            name = item.get("name")
            if not isinstance(name, str):
                pending = None
                continue
            args = _object(item.get("arguments", {})) or {}
            pending = (name, args, _target(name, args))
        elif item.get("kind") == "observation" and pending:
            name, args, key = pending
            pending = None
            observation_count += 1
            observation = _object(item.get("content"))
            check = {"kind": "tool", "tool": name, "target": key,
                     "event_id": item.get("event_id"), "status": "unverified"}
            if observation is None or type(observation.get("ok")) is not bool:
                uncertainties[key] = check | {"reason": "incomplete_observation"}
                continue
            if not observation["ok"]:
                if observation.get("error_kind") == "validation_rejected":
                    # Only the runtime can attest that input was rejected before
                    # any effect. Keep this separate: it cannot erase an earlier
                    # execution failure of the same target.
                    rejections[name] = check | {"status": "failed", "reason": "validation_rejected"}
                    continue
                latest[key] = check | {"status": "failed", "reason": "tool_error"}
                uncertainties.pop(key, None)
                continue
            result = observation.get("result")
            result_object = result if isinstance(result, dict) else {}
            if result_object.get("error"):
                latest[key] = check | {"status": "failed", "reason": "tool_reported_error"}
                uncertainties.pop(key, None)
                continue
            if name in {"code.run", "skill.run"}:
                if result_object.get("timed_out") is True:
                    check.update(status="failed", reason="code_timeout")
                elif type(result_object.get("exit_code")) is not int:
                    check.update(reason="code_exit_unavailable")
                elif result_object["exit_code"] != 0:
                    check.update(status="failed", reason="code_failed", exit_code=result_object["exit_code"])
                else:
                    check.update(status="passed", reason="code_exited_successfully", exit_code=0,
                                 output_truncated=bool(result_object.get("truncated")))
                artifacts = result_object.get("artifacts", [])
                if isinstance(artifacts, list):
                    for receipt in artifacts:
                        if isinstance(receipt, dict) and isinstance(receipt.get("path"), str):
                            receipts[receipt["path"]] = receipt
            elif name in {"workspace.write", "workspace.replace"}:
                if isinstance(result_object.get("path"), str):
                    receipts[result_object["path"]] = result_object
                    check.update(status="passed", reason="write_receipt_observed")
                else:
                    check.update(status="failed", reason="write_receipt_missing")
            elif name == "workspace.send":
                check.update(reason="delivery_pending" if result_object.get("status") == "queued" else "delivery_receipt_unavailable")
            elif name == "consult":
                check.update(reason="consultation_is_opinion")
            elif name == "self.experiment":
                state = result_object.get("status")
                check.update(status="passed" if state in {"regression_passed", "improved_on_provided_case"} else "unverified",
                             reason="experiment_report_observed", experiment_status=state, promotion=result_object.get("promotion"))
            else:
                check.update(status="passed", reason="tool_receipt_observed")
            if check["status"] == "passed" or check.get("reason") in {"delivery_pending", "consultation_is_opinion"}:
                # A corrected path/argument may change the target. That can
                # resolve a prior no-effect rejection of this tool only; normal
                # execution failures still require the same target to succeed.
                rejections.pop(name, None)
            if check["status"] == "unverified":
                # An incomplete later attempt is not evidence that an earlier
                # execution failure was corrected.
                uncertainties[key] = check
            else:
                latest[key] = check
                uncertainties.pop(key, None)
    if pending:
        name, _, key = pending
        uncertainties[key] = {"kind": "tool", "tool": name, "target": key, "status": "unverified", "reason": "missing_observation"}
    if expected_artifacts is not None:
        if not isinstance(expected_artifacts, list) or len(expected_artifacts) > 200:
            raise ValueError("Expected artifacts must contain at most 200 receipts")
        for receipt in expected_artifacts:
            if isinstance(receipt, dict) and isinstance(receipt.get("path"), str):
                receipts[receipt["path"]] = receipt
            else:
                latest["invalid_artifact_receipt"] = {"kind": "artifact", "status": "failed", "reason": "invalid_artifact_receipt"}
    artifact_checks = [_artifact_check(receipt, workspace) for receipt in receipts.values()]
    checks = [*latest.values(), *rejections.values(), *uncertainties.values(), *artifact_checks]
    failures = [check for check in checks if check["status"] == "failed"]
    return {"status": "contradicted" if failures else "observed" if any(check["status"] == "passed" for check in checks) else "unverified",
            "model_outcome": model_outcome, "observation_count": observation_count, "checks": checks,
            "failures": failures, "artifacts": artifact_checks, "limitations": list(_LIMITATIONS)}


def _pair(name, arguments, result=None, *, ok=True):
    return [{"kind": "tool", "name": name, "arguments": json.dumps(arguments)},
            {"kind": "observation", "content": json.dumps({"ok": ok, "result": result})}]


def run_acceptance_suite() -> dict:
    """No model, credentials, Telegram, network or installed-state changes.

    These acceptance scenarios are separate from unittest discovery and from
    Evolution's candidate test injection. A scripted scenario measures runtime
    behavior and evidence integrity, not the quality of a model's decisions.
    """
    if not __debug__:
        raise RuntimeError("Acceptance assertions require Python without -O")
    from .queue import Queue
    from .store import Store
    from .tools import Workspace
    results = []

    def scenario(name, execute):
        started = time.monotonic()
        try:
            details = execute()
            results.append({"name": name, "passed": True, "details": details or {}})
        except Exception as exc:
            # A safe exception class is enough for an independently rerunnable
            # fixture. Do not publish arbitrary database/host exception text.
            results.append({"name": name, "passed": False, "error": type(exc).__name__})
        results[-1]["seconds"] = round(time.monotonic() - started, 4)

    with tempfile.TemporaryDirectory(prefix="marka-acceptance-") as directory:
        root = Path(directory)

        def memory_recall():
            store = Store(root / "memory.sqlite3")
            source = store.event("user", "В оценочном сценарии проект Сапфир хранит отчёты по пятницам.")
            identifier = store.remember("Проект Сапфир: отчёты по пятницам", sources=[source], status="accepted", actor="owner")
            found = Store(store.path).search("Сапфир")
            assert any(item["id"] == identifier for item in found)
            return {"recalled_after_restart": True}
        scenario("accepted_memory_recall_after_restart", memory_recall)

        def candidate_isolation():
            store = Store(root / "candidate.sqlite3")
            source = store.event("assistant", "Возможно, кодовое слово Топаз.")
            store.remember("Кодовое слово Топаз", sources=[source])
            assert not store.search("Топаз")
            return {"unaccepted_memory_excluded": True}
        scenario("candidate_not_promoted_to_fact", candidate_isolation)

        def correction():
            store = Store(root / "correction.sqlite3")
            old_source = store.event("user", "Встреча Янтарь назначена на вторник")
            old = store.remember("Встреча Янтарь во вторник", key="meeting", sources=[old_source], status="accepted", actor="owner")
            source = store.event("user", "Исправление: встреча Янтарь в четверг")
            current = store.remember("Встреча Янтарь в четверг", key="meeting", sources=[source], status="accepted", actor="owner")
            found = store.search("Янтарь")
            assert any(item["id"] == current for item in found) and not any(item["id"] == old for item in found)
            return {"old_fact_excluded": True}
        scenario("owner_correction_supersedes_old_memory", correction)

        def forgotten():
            store = Store(root / "forgotten.sqlite3")
            source = store.event("user", "Оценочная запись Берилл")
            identifier = store.remember("Оценочная запись Берилл", sources=[source], status="accepted", actor="owner")
            store.forget(identifier)
            assert not Store(store.path).search("Берилл")
        scenario("forgotten_memory_stays_out_of_recall", forgotten)

        def long_task():
            queue = Queue(root / "long.sqlite3")
            identifier = queue.enqueue("Compile twenty sections", 0)
            queue.configure_task(identifier, max_steps=25, max_model_calls=25)
            for batch in range(2):
                job = queue.claim()
                for _ in range(10):
                    assert queue.reserve_call(identifier, job["lease"])["allowed"]
                assert queue.requeue(identifier, job["lease"], [], f"Completed {(batch + 1) * 10} sections")
            progress = Queue(queue.path).progress(identifier)
            assert progress["budget"]["used"]["steps"] == 20 and queue.next_delivery() is None
            return {"steps": 20, "continuations": 2}
        scenario("twenty_step_task_survives_continuations", long_task)

        def stopped():
            queue = Queue(root / "stopped.sqlite3")
            identifier = queue.enqueue("Resume a report", 0)
            queue.configure_task(identifier, max_steps=4, max_model_calls=4)
            job = queue.claim()
            queue.reserve_call(identifier, job["lease"])
            queue.cancel(identifier)
            queue.resume(identifier)
            current = queue.claim()
            assert not queue.finish(identifier, "completed", lease=job["lease"])
            assert queue.reserve_call(identifier, current["lease"])["step_number"] == 2
        scenario("cancel_resume_rejects_stale_worker", stopped)

        def exhausted():
            queue = Queue(root / "budget.sqlite3")
            identifier = queue.enqueue("Finite task", 0)
            queue.configure_task(identifier, max_steps=1, max_model_calls=1)
            job = queue.claim()
            assert queue.reserve_call(identifier, job["lease"])["allowed"]
            queue.cancel(identifier)
            queue.resume(identifier)
            new = queue.claim()
            assert not queue.reserve_call(identifier, new["lease"])["allowed"]
        scenario("resume_cannot_reset_model_budget", exhausted)

        def ambiguous():
            queue = Queue(root / "ambiguous.sqlite3")
            identifier = queue.enqueue("Interrupted artifact generation", 0)
            job = queue.claim()
            queue.checkpoint(identifier, [], inflight=True, lease=job["lease"])
            queue.recover()
            assert queue.get(identifier)["state"] == "blocked" and queue.claim() is None
        scenario("restart_blocks_ambiguous_tool_replay", ambiguous)

        workspace = Workspace(root / "workspace")

        def file_build():
            receipt = workspace.write("report.txt", "Раздел 1\nРаздел 2 🙂")
            report = verify_completion(_pair("workspace.write", {"path": "report.txt"}, receipt), workspace=workspace)
            assert report["status"] == "observed" and report["artifacts"][0]["status"] == "passed"
            return {"bytes": receipt["bytes"], "sha256": receipt["sha256"]}
        scenario("utf8_report_has_matching_bytes_and_hash", file_build)

        def stale_file():
            receipt = workspace.write("stale.txt", "approved content")
            workspace.write("stale.txt", "tampered content")
            assert verify_completion([], workspace=workspace, expected_artifacts=[receipt])["status"] == "contradicted"
        scenario("changed_artifact_cannot_pass_old_receipt", stale_file)

        def absent_file():
            receipt = workspace.write("removed.txt", "temporary report")
            workspace.path("removed.txt").unlink()
            assert verify_completion([], workspace=workspace, expected_artifacts=[receipt])["status"] == "contradicted"
        scenario("missing_artifact_blocks_completion_claim", absent_file)

        def corrected_code():
            args = {"argv": ["python", "report.py"]}
            trace = _pair("code.run", args, {"exit_code": 1, "timed_out": False})
            assert verify_completion(trace)["status"] == "contradicted"
            trace += _pair("code.run", args, {"exit_code": 0, "timed_out": False})
            assert verify_completion(trace)["status"] == "observed"
        scenario("same_command_correction_resolves_failure", corrected_code)

        def unrelated_code():
            trace = _pair("code.run", {"argv": ["python", "report.py"]}, {"exit_code": 1})
            trace += _pair("code.run", {"argv": ["python", "other.py"]}, {"exit_code": 0})
            assert verify_completion(trace)["status"] == "contradicted"
        scenario("unrelated_success_cannot_hide_code_failure", unrelated_code)

        def runner_output_error():
            trace = _pair("code.run", {"argv": ["python", "large.py"]}, {"exit_code": 0, "error": "Artifacts exceed limit"})
            assert verify_completion(trace)["status"] == "contradicted"
        scenario("zero_exit_with_artifact_error_is_not_success", runner_output_error)

        def delivery_pending():
            trace = _pair("workspace.send", {"path": "report.txt"}, {"status": "queued", "path": "report.txt"})
            report = verify_completion(trace)
            assert report["status"] == "unverified" and report["checks"][0]["reason"] == "delivery_pending"
        scenario("queued_document_is_not_confirmed_delivery", delivery_pending)

        def prose_is_not_evidence():
            assert verify_completion([{"kind": "final", "message": "I tested and deployed everything"}])["status"] == "unverified"
        scenario("model_completion_prose_is_not_observation", prose_is_not_evidence)

    passed = sum(item["passed"] for item in results)
    return {"suite": "marka-runtime-acceptance-v1", "model_calls": 0, "network_calls": 0,
            "passed": passed, "total": len(results), "ok": passed == len(results), "scenarios": results,
            "scope": "Public deterministic runtime acceptance; independent of model-proposed tests, not a model-intelligence benchmark."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a JSON receipt to this local path")
    args = parser.parse_args()
    report = run_acceptance_suite()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
