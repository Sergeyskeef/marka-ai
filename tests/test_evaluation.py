import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from marka.evaluation import verify_completion
from marka.queue import Queue
from marka.tools import Workspace


def observation(name, args, result=None, *, ok=True, error_kind=None):
    return [{"kind": "tool", "name": name, "arguments": json.dumps(args)},
            {"kind": "observation", "event_id": 7,
             "content": json.dumps({"ok": ok, "result": result, **({"error_kind": error_kind} if error_kind else {})})}]


class CompletionChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.workspace = Workspace(self.root / "workspace")

    def test_no_model_prose_or_consultation_is_treated_as_observation(self):
        report = verify_completion([{"kind": "final", "message": "Tests pass, file sent"}])
        self.assertEqual(report["model_outcome"], "completed")
        self.assertEqual(report["status"], "unverified")
        trace = observation("consult", {}, {"answer": "Everything works", "uncertainty": "none"})
        self.assertEqual(verify_completion(trace)["status"], "unverified")

    def test_code_requires_exit_status_and_no_timeout_or_artifact_error(self):
        for result in ({"exit_code": 1}, {"exit_code": 0, "timed_out": True},
                       {"exit_code": 0, "error": "Artifact collection failed"}):
            with self.subTest(result=result):
                report = verify_completion(observation("code.run", {"argv": ["python", "a.py"]}, result))
                self.assertEqual(report["status"], "contradicted")
        self.assertEqual(verify_completion(observation("code.run", {}, {"output": "all tests passed"}))["status"], "unverified")
        self.assertEqual(verify_completion(observation("code.run", {}, {"exit_code": 0}))["status"], "observed")

    def test_only_same_target_success_resolves_previous_failure(self):
        args = {"argv": ["python", "a.py"]}
        trace = observation("code.run", args, {"exit_code": 1})
        trace += observation("code.run", {"argv": ["python", "b.py"]}, {"exit_code": 0})
        self.assertEqual(verify_completion(trace)["status"], "contradicted")
        trace += observation("code.run", args, {"exit_code": 0})
        report = verify_completion(trace)
        self.assertEqual(report["status"], "observed")
        self.assertEqual(len(report["checks"]), 2)
        self.assertEqual(report["observation_count"], 3)

    def test_latest_file_revision_is_verified_against_real_bytes(self):
        original = self.workspace.write("report.txt", "same size A")
        trace = observation("workspace.write", {"path": "report.txt"}, original)
        changed = self.workspace.write("report.txt", "same size B")
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "contradicted")
        trace += observation("workspace.write", {"path": "report.txt"}, changed)
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "observed")
        self.workspace.path("report.txt").unlink()
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "contradicted")

    def test_code_artifact_receipts_are_rechecked_not_just_trusted(self):
        receipt = self.workspace.write_bytes("chart.png", b"binary\x00\xff")
        trace = observation("code.run", {"argv": ["python", "chart.py"]}, {"exit_code": 0, "artifacts": [receipt]})
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["artifacts"][0]["status"], "passed")
        self.workspace.write_bytes("chart.png", b"broken")
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "contradicted")

    def test_private_path_or_malformed_receipt_is_not_read(self):
        (self.root / "secret.txt").write_bytes(b"private")
        receipt = {"path": "../secret.txt", "bytes": 7, "sha256": hashlib.sha256(b"private").hexdigest()}
        report = verify_completion([], workspace=self.workspace, expected_artifacts=[receipt])
        self.assertEqual(report["status"], "contradicted")
        self.assertEqual(report["failures"][0]["reason"], "artifact_unreadable_or_unsafe")
        self.assertEqual(verify_completion([], expected_artifacts=[{}])["status"], "contradicted")

    def test_missing_or_truncated_observation_is_explicitly_unverified(self):
        trace = [{"kind": "tool", "name": "code.run", "arguments": "{}"},
                 {"kind": "observation", "content": '{"ok": true, "res'}]
        self.assertEqual(verify_completion(trace)["checks"][0]["reason"], "incomplete_observation")
        self.assertEqual(verify_completion(trace[:1])["checks"][0]["reason"], "missing_observation")

    def test_queued_file_delivery_does_not_become_sent(self):
        report = verify_completion(observation("workspace.send", {"path": "report.txt"}, {"status": "queued"}))
        self.assertEqual(report["status"], "unverified")
        self.assertEqual(report["checks"][0]["reason"], "delivery_pending")

    def test_write_without_artifact_receipt_does_not_prove_file_creation(self):
        report = verify_completion(observation("workspace.write", {"path": "report.txt"}, {}))
        self.assertEqual(report["status"], "contradicted")
        self.assertEqual(report["failures"][0]["reason"], "write_receipt_missing")

    def test_pre_effect_rejected_path_can_be_corrected_to_another_safe_path(self):
        trace = observation("workspace.write", {"path": "../escape.txt"}, ok=False, error_kind="validation_rejected")
        self.assertEqual(verify_completion(trace)["status"], "contradicted")
        receipt = self.workspace.write("safe/result.txt", "Checked report")
        trace += observation("workspace.write", {"path": "safe/result.txt"}, receipt)
        report = verify_completion(trace, workspace=self.workspace)
        self.assertEqual(report["status"], "observed")
        self.assertFalse(report["failures"])
        self.workspace.path("safe/result.txt").unlink()
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "contradicted")

    def test_unclassified_error_or_other_tool_success_does_not_resolve_rejection(self):
        rejected = observation("workspace.write", {"path": "../escape.txt"}, ok=False, error_kind="validation_rejected")
        rejected += observation("memory.search", {"query": "report"}, [])
        self.assertEqual(verify_completion(rejected)["status"], "contradicted")
        receipt = self.workspace.write("safe.txt", "data")
        unclassified = observation("workspace.write", {"path": "failed.txt"}, ok=False)
        unclassified += observation("workspace.write", {"path": "safe.txt"}, receipt)
        self.assertEqual(verify_completion(unclassified, workspace=self.workspace)["status"], "contradicted")

    def test_validation_rejection_cannot_erase_prior_execution_failure(self):
        for outcome in ({"exit_code": 2}, {"exit_code": 0, "timed_out": True},
                        {"exit_code": 0, "error": "Artifact limit exceeded"}):
            with self.subTest(outcome=outcome):
                args = {"argv": ["python", "main.py"]}
                trace = observation("code.run", args, outcome)
                trace += observation("code.run", args, ok=False, error_kind="validation_rejected")
                trace += observation("code.run", {"argv": ["python", "unrelated.py"]}, {"exit_code": 0})
                self.assertEqual(verify_completion(trace)["status"], "contradicted")

    def test_incomplete_later_attempt_does_not_hide_execution_failure(self):
        args = {"argv": ["python", "main.py"]}
        failed = observation("code.run", args, {"exit_code": 2})
        for later in (observation("code.run", args, {"output": "looks good"}),
                      [{"kind": "tool", "name": "code.run", "arguments": json.dumps(args)}],
                      [{"kind": "tool", "name": "code.run", "arguments": json.dumps(args)},
                       {"kind": "observation", "content": '{"ok":true,"result":'}]):
            self.assertEqual(verify_completion(failed + later)["status"], "contradicted")

    def test_corrected_consultation_resolves_validation_but_remains_an_opinion(self):
        trace = observation("consult", {"role": "unknown"}, ok=False, error_kind="validation_rejected")
        trace += observation("consult", {"role": "critic"}, {"answer": "An opinion", "uncertainty": "high"})
        report = verify_completion(trace)
        self.assertFalse(report["failures"])
        self.assertEqual(report["status"], "unverified")

    def test_skill_execution_requires_success_of_same_skill_and_real_artifact(self):
        trace = observation("skill.run", {"name": "report"}, {"exit_code": 2})
        trace += observation("skill.run", {"name": "other"}, {"exit_code": 0})
        self.assertEqual(verify_completion(trace)["status"], "contradicted")
        receipt = self.workspace.write("skill.txt", "output")
        trace += observation("skill.run", {"name": "report"}, {"exit_code": 0, "artifacts": [receipt]})
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "observed")
        self.workspace.path("skill.txt").unlink()
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "contradicted")
        timed_out = observation("skill.run", {"name": "report"}, {"exit_code": 0, "timed_out": True})
        self.assertEqual(verify_completion(timed_out)["status"], "contradicted")

    def test_skill_success_with_different_arguments_or_inputs_does_not_hide_failure(self):
        first = {"name": "report", "parameters": ["strict"], "inputs": {"data.csv": "bad.csv"}}
        for changed in (first | {"parameters": ["ignore-errors"]}, first | {"inputs": {"data.csv": "other.csv"}}):
            with self.subTest(changed=changed):
                trace = observation("skill.run", first, {"exit_code": 2})
                trace += observation("skill.run", changed, {"exit_code": 0})
                self.assertEqual(verify_completion(trace)["status"], "contradicted")

    def test_summarized_long_command_identity_does_not_collapse_to_missing_argv(self):
        from marka.engine import Engine
        first = {"argv": ["python", "-c", "print('a') # " + "a" * 4000]}
        other = {"argv": ["python", "-c", "print('b') # " + "b" * 4000]}
        trace = observation("code.run", Engine._arguments_snapshot(first), {"exit_code": 2})
        trace += observation("code.run", Engine._arguments_snapshot(other), {"exit_code": 0})
        self.assertEqual(verify_completion(trace)["status"], "contradicted")
        # Full legacy argv and a newer compact receipt name the same command.
        trace = observation("code.run", first, {"exit_code": 2})
        trace += observation("code.run", Engine._arguments_snapshot(first), {"exit_code": 0})
        self.assertEqual(verify_completion(trace)["status"], "observed")

    def test_summarized_skill_parameters_and_inputs_remain_distinct(self):
        from marka.engine import Engine
        first = {"name": "report", "parameters": ["a" * 4000], "inputs": {"data.txt": "a" * 4000}}
        for other in (first | {"parameters": ["b" * 4000]}, first | {"inputs": {"data.txt": "b" * 4000}}):
            trace = observation("skill.run", Engine._arguments_snapshot(first), {"exit_code": 1})
            trace += observation("skill.run", Engine._arguments_snapshot(other), {"exit_code": 0})
            self.assertEqual(verify_completion(trace)["status"], "contradicted")

    def test_outer_argument_snapshots_keep_different_command_identity(self):
        first = {"truncated": True, "sha256": "a" * 64, "preview": "large arguments"}
        other = first | {"sha256": "b" * 64}
        trace = observation("code.run", first, {"exit_code": 1})
        trace += observation("code.run", other, {"exit_code": 0})
        self.assertEqual(verify_completion(trace)["status"], "contradicted")

    def test_replace_receipt_updates_expected_file_revision(self):
        original = self.workspace.write("replace.txt", "first")
        changed = self.workspace.write("replace.txt", "second")
        trace = observation("workspace.write", {"path": "replace.txt"}, original)
        trace += observation("workspace.replace", {"path": "replace.txt"}, changed)
        self.assertEqual(verify_completion(trace, workspace=self.workspace)["status"], "observed")
        missing_receipt = observation("workspace.replace", {"path": "replace.txt"}, {})
        self.assertEqual(verify_completion(missing_receipt)["status"], "contradicted")

    def test_queue_evidence_covers_steps_dropped_from_model_prompt(self):
        queue = Queue(self.root / "queue.sqlite3")
        identifier = queue.enqueue("Long verification", 0)
        job = queue.claim()
        for number in range(1, 50):
            queue.record_step(identifier, lease=job["lease"], number=number, name="code.run",
                              arguments={"argv": ["python", f"script{number}.py"]},
                              outcome={"ok": True, "result": {"exit_code": 1 if number == 1 else 0}}, event_id=number)
        queue.checkpoint(identifier, [], lease=job["lease"])
        self.assertEqual(len(queue.progress(identifier)["steps"]), 20)
        trace = queue.evidence_trace(identifier)
        self.assertEqual(len(trace), 98)
        self.assertEqual(verify_completion(trace)["status"], "contradicted")


if __name__ == "__main__":
    unittest.main()
