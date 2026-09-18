"""Read-only reuse of canonical experiment history, independent of workspace copies."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from marka.config import Settings
from marka.evolution import Evolution
from marka.tools import Workspace
from test_evolution import FakeSandbox, CASE


class EvolutionArchiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "release/src/marka"
        self.tests = self.root / "release/tests"
        self.source.mkdir(parents=True)
        self.tests.mkdir()
        (self.source / "__init__.py").write_text("", "utf-8")
        (self.source / "sample.py").write_text("def value():\n    return 1\n", "utf-8")
        (self.tests / "test_sample.py").write_text("# fixture suite\n", "utf-8")
        self.settings = Settings(self.root / "state", sandbox_socket="/synthetic/socket")
        self.settings.prepare()
        self.workspace = Workspace(self.settings.workspace)
        self.runner = FakeSandbox()
        self.evolution = Evolution(self.settings, self.workspace, source_root=self.source, test_root=self.tests, runner=self.runner)

    async def experiment(self, *, failed=False, suffix=""):
        self.runner.outcomes = [{CASE: "passed"}, {CASE: "failed" if failed else "passed"}]
        self.runner.calls.clear()
        self.code = "# A complete source snapshot " + "x" * 20000 + "\ndef value():\n    return 2\n"
        return await self.evolution.experiment("Change sample " + suffix, {"src/marka/sample.py": self.code})

    def archive(self, identifier):
        return self.settings.data_dir / "evolution" / identifier

    async def test_history_reads_failed_canonical_experiment_not_editable_workspace_report(self):
        result = await self.experiment(failed=True)
        self.workspace.write(result["report_path"], "Forgery: candidate installed and all tests passed")
        history = self.evolution.history()
        self.assertEqual(history["experiments"][0]["id"], result["id"])
        self.assertEqual(history["experiments"][0]["status"], "rejected")
        self.assertEqual(history["promotion"], "none")
        report = self.evolution.read_experiment(result["id"])
        self.assertEqual(json.loads(report["content"])["status"], "rejected")
        self.assertNotIn("Forgery", report["content"])

    async def test_complete_source_can_be_reassembled_and_verified_without_modification(self):
        result = await self.experiment()
        original = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.archive(result["id"]).iterdir()}
        parts, offset = [], 0
        while True:
            page = self.evolution.read_experiment(result["id"], "candidate", "src/marka/sample.py", offset=offset, limit=2700)
            self.assertLessEqual(len(page["content"]), 2700)
            self.assertEqual(page["sha256"], hashlib.sha256(self.code.encode()).hexdigest())
            self.assertEqual(page["total_chars"], len(self.code))
            self.assertEqual(page["integrity"], "matched_report_manifest")
            self.assertEqual(page["promotion"], "none")
            parts.append(page["content"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        self.assertEqual("".join(parts), self.code)
        baseline = self.evolution.read_experiment(result["id"], "baseline", "src/marka/sample.py")
        self.assertIn("return 1", baseline["content"])
        self.assertEqual(original, {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.archive(result["id"]).iterdir()})
        self.assertEqual(len(self.runner.calls), 2)

    async def test_manifest_and_patch_are_paged_and_hashes_cover_full_content(self):
        result = await self.experiment()
        manifest = self.evolution.read_experiment(result["id"], "candidate", limit=8000)
        self.assertTrue(manifest["manifest_listing"])
        self.assertIn("src/marka/sample.py", [item["path"] for item in json.loads(manifest["content"])])
        self.assertEqual(manifest["total_files"], 3)
        patch = self.evolution.read_experiment(result["id"], "patch", limit=120)
        self.assertLessEqual(len(patch["content"]), 120)
        self.assertIsNotNone(patch["next_offset"])
        self.assertEqual(patch["integrity"], "matched_report_digest")
        self.assertEqual(patch["sha256"], hashlib.sha256((self.archive(result["id"]) / "candidate.patch").read_bytes()).hexdigest())

    async def test_corrupt_or_incomplete_entries_are_reported_without_hiding_healthy_history(self):
        good = await self.experiment()
        for index, data in enumerate((b"not-json", b'{"status":[]}', b"x" * (512 * 1024 + 1))):
            directory = self.settings.data_dir / "evolution" / f"{index + 1:032x}"
            directory.mkdir()
            (directory / "report.json").write_bytes(data)
        incomplete = self.settings.data_dir / "evolution" / ("f" * 32)
        incomplete.mkdir()
        history = self.evolution.history()
        self.assertEqual([item["id"] for item in history["experiments"]], [good["id"]])
        self.assertEqual(history["skipped_corrupt"], 4)
        self.assertEqual(len(history["errors"]), 4)

    async def test_tampered_source_or_patch_rejected_against_report_manifest(self):
        result = await self.experiment()
        directory = self.archive(result["id"])
        bundle = directory / "candidate.json"
        sources = json.loads(bundle.read_text("utf-8"))
        sources["src/marka/sample.py"] = "print('tampered')"
        bundle.chmod(0o600)
        bundle.write_text(json.dumps(sources), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.evolution.read_experiment(result["id"], "candidate", "src/marka/sample.py")
        patch = directory / "candidate.patch"
        patch.chmod(0o600)
        patch.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.evolution.read_experiment(result["id"], "patch")

    async def test_ids_paths_and_page_limits_fail_closed(self):
        result = await self.experiment()
        for identifier in ("../settings.json", "a" * 31, "A" * 32, str(self.archive(result["id"]))):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.evolution.read_experiment(identifier)
        for path in ("../../settings.json", "src/marka/auth.json", "tests/../auth.py", "C:/private.py", "tests\\private.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.evolution.read_experiment(result["id"], "candidate", path)
        for kwargs in ({"limit": 8001}, {"limit": 0}, {"offset": -1}, {"offset": True}, {"artifact": "report.json"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.evolution.read_experiment(result["id"], **kwargs)

    async def test_oversized_candidate_bundle_is_rejected_before_loading(self):
        result = await self.experiment()
        path = self.archive(result["id"]) / "candidate.json"
        path.chmod(0o600)
        with path.open("wb") as stream:
            stream.truncate(4 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "reading limit"):
            self.evolution.read_experiment(result["id"], "candidate")

    async def test_legacy_patch_without_hash_is_explicitly_labeled(self):
        result = await self.experiment()
        path = self.archive(result["id"]) / "report.json"
        report = json.loads(path.read_text("utf-8"))
        report.pop("patch_sha256")
        path.chmod(0o600)
        path.write_text(json.dumps(report), encoding="utf-8")
        patch = self.evolution.read_experiment(result["id"], "patch")
        self.assertEqual(patch["integrity"], "legacy_archive_without_recorded_patch_digest")

    async def test_history_limit_reports_more_available(self):
        await self.experiment(suffix="first")
        await self.experiment(suffix="second")
        result = self.evolution.history(limit=1)
        self.assertEqual(len(result["experiments"]), 1)
        self.assertTrue(result["truncated"])

    async def test_report_larger_than_one_page_is_complete_when_paged(self):
        result = await self.experiment()
        data = (self.archive(result["id"]) / "report.json").read_bytes()
        first = self.evolution.read_experiment(result["id"], limit=200)
        second = self.evolution.read_experiment(result["id"], offset=first["next_offset"])
        self.assertEqual(first["content"] + second["content"], data.decode())
        self.assertEqual(first["sha256"], hashlib.sha256(data).hexdigest())

    def symlink(self, path, destination, *, directory=False):
        try:
            path.symlink_to(destination, target_is_directory=directory)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable")
            raise

    async def test_archive_file_symlink_cannot_expose_another_file(self):
        result = await self.experiment()
        path = self.archive(result["id"]) / "report.json"
        destination = self.root / "outside-report.json"
        destination.write_bytes(path.read_bytes())
        path.chmod(0o600)
        path.unlink()
        self.symlink(path, destination)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.evolution.read_experiment(result["id"])
        self.assertEqual(self.evolution.history()["skipped_corrupt"], 1)

    async def test_archive_root_symlink_is_rejected(self):
        result = await self.experiment()
        root = self.settings.data_dir / "evolution"
        moved = self.settings.data_dir / "moved"
        root.rename(moved)
        self.symlink(root, moved, directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.evolution.history()
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.evolution.read_experiment(result["id"])


if __name__ == "__main__":
    unittest.main()
