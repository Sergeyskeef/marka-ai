import ast
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zlib
from unittest.mock import patch

from marka.config import Settings
from marka.evolution import Evolution, _HARNESS, _MARKER
from marka.tools import Workspace


CASE = "test_sample.Sample.test_value"
PROPOSED = "test_model_proposed.Regression.test_corrected_case"


def result_for(nonce, outcomes, **overrides):
    successful = all(value in {"passed", "skipped", "expected_failure"} for value in outcomes.values())
    report = {"nonce": nonce, "tests_run": len(outcomes), "discovered_count": len(outcomes),
              "discovered_sha256": hashlib.sha256(json.dumps(sorted(outcomes), ensure_ascii=False,
                                                             separators=(",", ":")).encode()).hexdigest(),
              "outcomes": outcomes, "test_integrity": True, "source_integrity": True,
              "successful": successful, "log": "", "failures": []}
    report.update(overrides)
    return {"exit_code": 0 if successful else 1, "timed_out": False, "truncated": False,
            "output": _MARKER + json.dumps(report) + "\n", "_files": {}}


class FakeSandbox:
    def __init__(self, outcomes=None, transform=None):
        self.outcomes = outcomes or [{CASE: "passed"}, {CASE: "passed"}]
        self.transform = transform
        self.calls = []

    def __call__(self, socket, argv, timeout, files):
        decoded = {name: base64.b64decode(value) for name, value in files.items()}
        manifest = json.loads(decoded["eval_manifest.json"])
        self.calls.append({"socket": socket, "argv": argv, "timeout": timeout,
                           "files": decoded, "manifest": manifest})
        result = result_for(manifest["nonce"], self.outcomes[len(self.calls) - 1])
        return self.transform(result) if self.transform else result


class EvolutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "release" / "src" / "marka"
        self.tests = self.root / "release" / "tests"
        self.source.mkdir(parents=True)
        self.tests.mkdir()
        (self.source / "__init__.py").write_text("", "utf-8")
        (self.source / "sample.py").write_text("def value():\n    return 1\n", "utf-8")
        (self.source / "identity.md").write_text("Public identity", "utf-8")
        (self.tests / "test_sample.py").write_text(
            "import unittest\nfrom marka.sample import value\n"
            "class Sample(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 1)\n", "utf-8")
        self.settings = Settings(self.root / "state", sandbox_socket="/synthetic/socket")
        self.settings.prepare()
        self.workspace = Workspace(self.settings.workspace)
        self.changes = {"src/marka/sample.py": "def value():\n    return 2\n"}

    def evolution(self, runner):
        return Evolution(self.settings, self.workspace, source_root=self.source, test_root=self.tests, runner=runner)

    def archive(self, result):
        return self.settings.data_dir / "evolution" / result["id"]

    def test_large_complete_report_uses_bounded_compression_without_losing_cases(self):
        cases = {f"test_module.LongMeaningfulClass.test_behavior_{number:04d}_with_real_evidence": "passed" for number in range(700)}
        value = result_for("nonce", cases)
        raw = value["output"][len(_MARKER):].strip().encode()
        self.assertGreater(len(raw), 32000)
        value["output"] = _MARKER + json.dumps({"encoding": "zlib-base64", "data": base64.b64encode(zlib.compress(raw)).decode()})
        self.assertLess(len(value["output"]), 32000)
        self.assertEqual(Evolution._parse(value, "nonce")["outcomes"], cases)
        value["output"] = _MARKER + json.dumps({"encoding": "zlib-base64", "data": base64.b64encode(zlib.compress(b"x" * 300000)).decode()})
        with self.assertRaises(ValueError):
            Evolution._parse(value, "nonce")

    def test_inspection_only_exposes_public_snapshot(self):
        evolution = self.evolution(FakeSandbox())
        names = {item["path"] for item in evolution.inspect()["files"]}
        self.assertIn("src/marka/identity.md", names)
        self.assertIn("tests/test_sample.py", names)
        self.assertIn("return 1", evolution.inspect("src/marka/sample.py")["content"])
        for name in ("../settings.json", "auth.json", str(self.settings.data_dir)):
            with self.assertRaises(ValueError):
                evolution.inspect(name)
        ast.parse(_HARNESS)

    async def test_regression_run_archives_exact_snapshot_without_host_execution(self):
        runner = FakeSandbox()
        with patch("subprocess.Popen", side_effect=AssertionError("No host code execution permitted")):
            result = await self.evolution(runner).experiment("Improve one module", self.changes)
        self.assertEqual(result["status"], "regression_passed")
        self.assertEqual(result["promotion"], "none")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(runner.calls[0]["timeout"], 60)
        self.assertEqual(runner.calls[0]["argv"], ["python", "eval_runner.py"])
        self.assertNotEqual(runner.calls[0]["files"]["src/marka/sample.py"], runner.calls[1]["files"]["src/marka/sample.py"])
        self.assertEqual(runner.calls[0]["files"]["tests/test_sample.py"], runner.calls[1]["files"]["tests/test_sample.py"])
        self.assertIn("return 1", (self.source / "sample.py").read_text("utf-8"))
        archive = self.archive(result)
        report = json.loads((archive / "report.json").read_text("utf-8"))
        self.assertNotEqual(report["baseline_hashes"]["src/marka/sample.py"], report["candidate_hashes"]["src/marka/sample.py"])
        self.assertTrue((archive / "baseline-result.json").is_file())
        self.assertTrue((archive / "candidate-result.json").is_file())
        self.assertTrue(self.workspace.path(result["report_path"]).is_file())
        patch_text = self.workspace.path(result["patch_path"]).read_text("utf-8")
        self.assertIn("-    return 1", patch_text)
        self.assertIn("+    return 2", patch_text)
        self.assertIn("tamper", report["limitation"])

    async def test_provided_regression_is_identical_on_both_sides_and_labeled(self):
        runner = FakeSandbox([{CASE: "passed", PROPOSED: "failed"}, {CASE: "passed", PROPOSED: "passed"}])
        proposed = "import unittest\nclass Regression(unittest.TestCase):\n    def test_corrected_case(self):\n        self.fail('synthetic')\n"
        result = await self.evolution(runner).experiment("Correct provided case", self.changes, proposed)
        self.assertEqual(result["status"], "improved_on_provided_case")
        self.assertEqual(result["improved_tests"], [PROPOSED])
        self.assertEqual(runner.calls[0]["files"]["tests/test_model_proposed.py"], runner.calls[1]["files"]["tests/test_model_proposed.py"])
        report = json.loads((self.archive(result) / "report.json").read_text("utf-8"))
        self.assertTrue(report["model_proposed_test"])
        self.assertIn("model-proposed", self.workspace.path(result["report_path"]).read_text("utf-8"))

    async def test_failing_candidate_is_rejected(self):
        result = await self.evolution(FakeSandbox([{CASE: "passed"}, {CASE: "failed"}])).experiment("Try", self.changes)
        self.assertEqual(result["status"], "rejected")

    async def test_new_skip_is_rejected_instead_of_reporting_improvement(self):
        second_case = "test_sample.Sample.test_other"
        runner = FakeSandbox([{CASE: "passed", second_case: "passed"}, {CASE: "skipped", second_case: "passed"}])
        result = await self.evolution(runner).experiment("Try", self.changes)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("weakened", result["reason"])

    async def test_changed_test_ids_make_evaluation_incomparable(self):
        runner = FakeSandbox([{CASE: "passed"}, {"test_other.Sample.test_missing": "passed"}])
        result = await self.evolution(runner).experiment("Try", self.changes)
        self.assertEqual(result["status"], "evaluation_failed")
        self.assertIn("different test identifiers", result["reason"])

    async def test_bad_raw_result_is_archived_before_rejection(self):
        runner = FakeSandbox(transform=lambda result: result | {"output": "No structured report"})
        result = await self.evolution(runner).experiment("Try", self.changes)
        self.assertEqual(result["status"], "evaluation_failed")
        self.assertEqual(len(runner.calls), 1)
        saved = json.loads((self.archive(result) / "baseline-result.json").read_text("utf-8"))
        self.assertEqual(saved["output"], "No structured report")

    async def test_missing_runner_exports_reviewable_candidate_without_executing(self):
        self.settings.sandbox_socket = ""
        runner = FakeSandbox()
        result = await self.evolution(runner).experiment("Try", self.changes)
        self.assertEqual(result["status"], "evaluation_failed")
        self.assertIn("ordinary host execution is disabled", result["reason"])
        self.assertEqual(runner.calls, [])
        self.assertTrue(self.workspace.path(result["patch_path"]).is_file())

    async def test_invalid_or_out_of_scope_changes_are_rejected_before_execution(self):
        runner = FakeSandbox()
        evolution = self.evolution(runner)
        invalid = [{"tests/test_sample.py": "pass"}, {"src/marka/identity.md": "changed"},
                   {"../sample.py": "pass"}, {"src/marka/sample.py": "def invalid("},
                   {"src/marka/sample.py": "#" + "a" * 60000},
                   {f"src/marka/mod{i}.py": "pass" for i in range(4)}]
        for changes in invalid:
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                await evolution.experiment("Try", changes)
        self.assertEqual(runner.calls, [])
        self.assertFalse((self.settings.data_dir / "evolution").exists())

    def test_result_validation_catches_harness_tampering_counts_timeouts_and_forgery(self):
        nonce = "synthetic-run"
        valid = result_for(nonce, {CASE: "passed"})
        self.assertEqual(Evolution._parse(valid, nonce)["tests_run"], 1)
        invalid = [valid | {"timed_out": True}, valid | {"truncated": True},
                   valid | {"exit_code": 1}, valid | {"output": valid["output"] * 2},
                   result_for(nonce, {CASE: "passed"}, test_integrity=False),
                   result_for(nonce, {CASE: "passed"}, source_integrity=False),
                   result_for(nonce, {CASE: "passed"}, tests_run=0),
                   result_for(nonce, {CASE: "passed"}, discovered_count=2),
                   result_for(nonce, {CASE: "skipped"}), result_for("wrong", {CASE: "passed"})]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                Evolution._parse(raw, nonce)

    async def test_new_module_and_missing_final_newline_produce_reviewable_patch(self):
        changes = {"src/marka/new_feature.py": "def feature():\n    return True"}
        result = await self.evolution(FakeSandbox()).experiment("Add helper", changes)
        patch_text = self.workspace.path(result["patch_path"]).read_text("utf-8")
        self.assertIn("\\ No newline at end of file", patch_text)
        self.assertFalse((self.source / "new_feature.py").exists())


if __name__ == "__main__":
    unittest.main()
