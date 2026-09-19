import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from marka.acceptance import freeze_criteria, get_criteria, evaluate_criteria, normalize_criteria
from marka.evaluation import verify_completion
from marka.queue import Queue
from marka.store import Store
from marka.tools import Workspace


def pair(name, arguments, result=None, *, ok=True):
    return [{"kind": "tool", "name": name, "arguments": json.dumps(arguments)},
            {"kind": "observation", "event_id": 7, "content": json.dumps({"ok": ok, "result": result})}]


def command(argv, *, code=0, inputs=None, error=None, timed_out=False):
    result = {"argv": argv, "exit_code": code, "input_manifest": inputs or {}, "timed_out": timed_out}
    if error:
        result["error"] = error
    return pair("code.run", {"argv": argv}, result)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = Store(self.root / "state.sqlite3")
        self.queue = Queue(self.store.path)
        self.workspace = Workspace(self.root / "workspace")
        self.identifier = self.queue.enqueue("Create a report with findings and next steps", 42, source="telegram:123")
        self.job = self.queue.claim()

    def freeze(self, criteria=None):
        return freeze_criteria(self.queue, self.identifier, self.job["lease"], criteria or [
            {"id": "report", "kind": "artifact", "path": "report.md"}])

    def evaluate(self, contract, trace, **kwargs):
        return evaluate_criteria(contract, trace, workspace=self.workspace, **kwargs)

    def test_frozen_contract_is_bound_to_actual_job_and_not_owner_approval(self):
        contract = self.freeze()
        self.assertEqual(contract["job_id"], self.identifier)
        self.assertEqual(contract["source"], "telegram:123")
        self.assertEqual(contract["prompt_sha256"], hashlib.sha256(self.job["prompt"].encode()).hexdigest())
        self.assertEqual(contract["proposer"], "model")
        self.assertIs(contract["owner_accepted"], False)
        self.assertEqual(get_criteria(Queue(self.store.path), self.identifier), contract)

    def test_same_criteria_are_idempotent_but_weakening_replacement_and_empty_are_refused(self):
        first = self.freeze()
        self.assertEqual(self.freeze(), first)
        for criteria in ([{"id": "report", "kind": "artifact", "path": "other.md"}],
                         [{"id": "report", "kind": "artifact", "path": "report.md", "min_bytes": 0}], []):
            with self.assertRaises(ValueError):
                freeze_criteria(self.queue, self.identifier, self.job["lease"], criteria)
        self.assertEqual(get_criteria(self.queue, self.identifier), first)

    def test_stale_or_cancelled_task_cannot_freeze(self):
        self.queue.cancel(self.identifier)
        with self.assertRaises(ValueError):
            self.freeze()
        self.queue.resume(self.identifier)
        self.queue.claim()
        with self.assertRaises(ValueError):
            self.freeze()

    def test_read_only_inspection_before_freeze_is_allowed(self):
        self.queue.record_step(self.identifier, lease=self.job["lease"], number=1, name="workspace.read", outcome={"ok": True})
        self.assertEqual(self.freeze()["criteria"][0]["id"], "report")

    def test_effectful_work_in_durable_or_legacy_trace_blocks_late_declaration(self):
        self.queue.record_step(self.identifier, lease=self.job["lease"], number=1, name="workspace.write", outcome={"ok": True})
        with self.assertRaisesRegex(ValueError, "before effectful"):
            self.freeze()
        with self.queue.connection() as db:
            db.execute("DELETE FROM task_steps WHERE job_id=?", (self.identifier,))
        self.queue.checkpoint(self.identifier, pair("code.run", {"argv": ["python", "a.py"]}, {"exit_code": 0}), lease=self.job["lease"])
        with self.assertRaisesRegex(ValueError, "before effectful"):
            self.freeze()

    def test_existing_contract_cannot_be_changed_after_work_but_exact_replay_is_allowed(self):
        frozen = self.freeze()
        self.queue.record_step(self.identifier, lease=self.job["lease"], number=1, name="workspace.write", outcome={"ok": True})
        self.assertEqual(self.freeze(), frozen)

    def test_malformed_metadata_and_changed_request_fail_closed(self):
        self.freeze()
        with self.queue.connection() as db:
            db.execute("UPDATE meta SET value='broken' WHERE key=?", ("task-criteria:v1:" + self.identifier,))
        stored = get_criteria(self.queue, self.identifier)
        self.assertTrue(stored["invalid"])
        self.assertFalse(self.evaluate(stored, [])["completion_allowed"])
        with self.assertRaises(ValueError):
            self.freeze()

    def test_metadata_hash_detects_criterion_tampering(self):
        frozen = self.freeze()
        frozen["criteria"][0]["min_bytes"] = 0
        with self.queue.connection() as db:
            db.execute("UPDATE meta SET value=? WHERE key=?", (json.dumps(frozen), "task-criteria:v1:" + self.identifier))
        self.assertTrue(get_criteria(self.queue, self.identifier)["invalid"])

    def test_frozen_binding_detects_prompt_revision(self):
        self.freeze()
        with self.queue.connection() as db:
            db.execute("UPDATE jobs SET prompt='different owner request' WHERE id=?", (self.identifier,))
        self.assertTrue(get_criteria(self.queue, self.identifier)["invalid"])

    def test_no_criteria_preserves_ordinary_chat_contract(self):
        self.assertIsNone(get_criteria(self.queue, self.identifier))
        self.assertTrue(evaluate_criteria(None, [])["completion_allowed"])
        self.assertEqual(verify_completion([])["status"], "unverified")
        self.assertNotIn("acceptance", verify_completion([]))

    def test_artifact_receipt_and_current_bytes_are_both_required(self):
        frozen = self.freeze()
        receipt = self.workspace.write("report.md", "A real report")
        self.assertEqual(self.evaluate(frozen, [])["status"], "missing")
        trace = pair("workspace.write", {"path": "report.md"}, receipt)
        self.assertEqual(self.evaluate(frozen, trace)["status"], "pass")
        self.workspace.write("report.md", "Edited report")
        self.assertEqual(self.evaluate(frozen, trace)["status"], "failed")

    def test_preexisting_file_can_be_verified_by_this_tasks_read_receipt(self):
        self.workspace.write("report.md", "Existing reviewed file")
        frozen = self.freeze()
        receipt = self.workspace.read("report.md")
        result = self.evaluate(frozen, pair("workspace.read", {"path": "report.md"}, receipt))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["checks"][0]["receipt_origin"], "read")

    def test_final_prose_and_consultation_cannot_substitute_required_artifact(self):
        frozen = self.freeze()
        trace = pair("consult", {}, {"answer": "Report was created and verified"})
        trace.append({"kind": "final", "message": "All done"})
        result = verify_completion(trace, workspace=self.workspace, criteria_contract=frozen)
        self.assertEqual(result["status"], "contradicted")
        self.assertEqual(result["acceptance"]["status"], "missing")

    def test_empty_artifact_fails_default_minimum(self):
        frozen = self.freeze()
        receipt = self.workspace.write("report.md", "")
        self.assertEqual(self.evaluate(frozen, [], expected_artifacts=[receipt])["status"], "failed")

    def test_literal_content_contract_catches_incomplete_report_and_accepts_repair(self):
        frozen = self.freeze([{"id": "sections", "kind": "text_contains", "path": "report.md", "contains": ["Findings", "Next steps"]}])
        receipt = self.workspace.write("report.md", "Findings\nUseful evidence")
        trace = pair("workspace.write", {"path": "report.md"}, receipt)
        self.assertEqual(self.evaluate(frozen, trace)["status"], "failed")
        repaired = self.workspace.write("report.md", "Findings\nUseful evidence\nNext steps\nRun a pilot")
        trace += pair("workspace.write", {"path": "report.md"}, repaired)
        self.assertEqual(self.evaluate(frozen, trace)["status"], "pass")

    def test_json_pointer_handles_arrays_and_escaped_keys(self):
        frozen = self.freeze([{"id": "json", "kind": "json_matches", "path": "report.json", "assertions": [
            {"pointer": "/items/0/status", "equals": "ready"}, {"pointer": "/a~1b/~0key", "equals": True}]}])
        receipt = self.workspace.write("report.json", '{"items":[{"status":"ready"}],"a/b":{"~key":true}}')
        self.assertEqual(self.evaluate(frozen, [], expected_artifacts=[receipt])["status"], "pass")

    def test_json_boolean_is_not_number_and_missing_pointer_fails(self):
        frozen = self.freeze([{"id": "json", "kind": "json_matches", "path": "report.json", "assertions": [{"pointer": "/ready", "equals": True}]}])
        for data in ('{"ready":1}', '{}'):
            receipt = self.workspace.write("report.json", data)
            self.assertEqual(self.evaluate(frozen, [], expected_artifacts=[receipt])["status"], "failed")

    def test_json_duplicate_nonfinite_invalid_utf8_are_refused(self):
        frozen = self.freeze([{"id": "json", "kind": "json_matches", "path": "report.json", "assertions": [{"pointer": "/ready", "equals": True}]}])
        for data in (b'{"ready":false,"ready":true}', b'{"ready":true,"x":NaN}', b'{"ready":true,"x":1e9999}', b'\xff'):
            receipt = self.workspace.write_bytes("report.json", data)
            self.assertEqual(self.evaluate(frozen, [], expected_artifacts=[receipt])["status"], "failed")

    def test_exact_known_command_success_and_same_target_recovery(self):
        argv = ["python", "-c", "print(42)"]
        frozen = self.freeze([{"id": "run", "kind": "command_succeeded", "argv": argv}])
        trace = command(argv, code=1)
        self.assertEqual(self.evaluate(frozen, trace)["status"], "failed")
        trace += command(["python", "-c", "print(99)"])
        self.assertEqual(self.evaluate(frozen, trace)["status"], "failed")
        trace += command(argv)
        self.assertEqual(self.evaluate(frozen, trace)["status"], "pass")

    def test_partial_later_attempt_does_not_reuse_earlier_command_success(self):
        argv = ["python", "report.py"]
        frozen = self.freeze([{"id": "run", "kind": "command_succeeded", "argv": argv}])
        trace = command(argv)
        trace.append({"kind": "tool", "name": "code.run", "arguments": json.dumps({"argv": argv})})
        self.assertEqual(self.evaluate(frozen, trace)["status"], "missing")

    def test_command_timeout_artifact_error_and_incomplete_receipt_cannot_pass(self):
        argv = ["python", "report.py"]
        frozen = self.freeze([{"id": "run", "kind": "command_succeeded", "argv": argv}])
        for trace in (command(argv, timed_out=True), command(argv, error="Artifact gathering failed"),
                      pair("code.run", {"argv": argv}, {"exit_code": 0})):
            self.assertFalse(self.evaluate(frozen, trace)["completion_allowed"])

    def test_changed_tested_code_invalidates_command_contract(self):
        argv = ["python", "report.py"]
        frozen = self.freeze([{"id": "run", "kind": "command_succeeded", "argv": argv}])
        receipt = self.workspace.write("report.py", "print(42)")
        trace = command(argv, inputs={"report.py": receipt})
        self.assertEqual(self.evaluate(frozen, trace)["status"], "pass")
        self.workspace.write("report.py", "raise RuntimeError('broken after test')")
        self.assertEqual(self.evaluate(frozen, trace)["status"], "failed")

    def test_input_manifest_size_bound_prevents_unbounded_verifier_reads(self):
        argv = ["python", "report.py"]
        frozen = self.freeze([{"id": "run", "kind": "command_succeeded", "argv": argv}])
        inputs = {"huge.py": {"bytes": 512 * 1024 + 1, "sha256": "0" * 64}}
        self.assertEqual(self.evaluate(frozen, command(argv, inputs=inputs))["status"], "failed")

    def test_passing_criteria_do_not_hide_other_runtime_failures(self):
        frozen = self.freeze()
        receipt = self.workspace.write("report.md", "Report exists")
        trace = pair("workspace.write", {"path": "report.md"}, receipt) + command(["python", "other.py"], code=1)
        result = verify_completion(trace, workspace=self.workspace, criteria_contract=frozen)
        self.assertEqual(result["acceptance"]["status"], "pass")
        self.assertEqual(result["status"], "contradicted")

    def test_unsafe_path_unknown_fields_arbitrary_verifier_code_are_rejected(self):
        for criteria in ([{"id": "x", "kind": "artifact", "path": "../private"}],
                         [{"id": "x", "kind": "artifact", "path": "report.md", "optional": True}],
                         [{"id": "x", "kind": "command_succeeded", "argv": ["powershell", "danger"]}],
                         [{"id": "x", "kind": "python", "code": "raise RuntimeError()"}],
                         [{"id": "x", "kind": "json_matches", "path": "a.json", "assertions": [{"pointer": "/bad~2key", "equals": 1}]}]):
            with self.assertRaises(ValueError):
                normalize_criteria(criteria)

    def test_verifier_never_executes_the_declared_command(self):
        argv = ["python", "-c", "raise RuntimeError('must not execute')"]
        frozen = self.freeze([{"id": "run", "kind": "command_succeeded", "argv": argv}])
        with mock.patch("subprocess.run", side_effect=AssertionError("verifier executed code")):
            self.assertEqual(self.evaluate(frozen, command(argv))["status"], "pass")


if __name__ == "__main__":
    unittest.main()
