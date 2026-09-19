import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from marka.config import Settings
from marka.evolution import Evolution
from marka.engine import Engine
from marka.promotion import Promotion, canonical, manifest
from marka.queue import Queue
from marka.store import Store
from marka.tools import Workspace
from test_evolution import FakeSandbox, CASE


class PromotionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source, tests = self.root / "release/src/marka", self.root / "release/tests"
        source.mkdir(parents=True)
        tests.mkdir()
        (source / "__init__.py").write_text("", "utf-8")
        (source / "sample.py").write_bytes(b"VALUE = 1\n")
        (tests / "test_sample.py").write_text("# pinned fixture\n", "utf-8")
        inbox = self.root / "inbox"
        inbox.mkdir()
        self.settings = Settings(self.root / "state", sandbox_socket="synthetic", bridge_socket="bridge.sock",
                                 upgrade_inbox=str(inbox), upgrade_status=str(self.root / "guardian.json"))
        self.settings.prepare()
        self.store, self.queue = Store(self.settings.database), Queue(self.settings.database)
        self.workspace = Workspace(self.settings.workspace)
        self.runner = FakeSandbox()
        self.evolution = Evolution(self.settings, self.workspace, source_root=source, test_root=tests, runner=self.runner)
        self.promotion = Promotion(self.settings, self.store, self.queue, self.workspace, evolution=self.evolution)
        self.store.set_meta("owner_id", 17)
        self.identifier = self.queue.enqueue("Improve the parser", 17, source="telegram:42", kind="self_improve")
        self.job = self.queue.claim()
        self.store.set_meta("owner-request:telegram:42", {"job_id": self.identifier, "owner_id": 17, "source": "telegram:42"})
        self.event = self.store.event("user", "Improve the parser", meta={"job": self.identifier})

    async def experiment(self, failed=False):
        self.runner.outcomes = [{CASE: "passed"}, {CASE: "failed" if failed else "passed"}]
        self.runner.calls.clear()
        result = await self.evolution.experiment("Use the new parser", {"src/marka/sample.py": "VALUE = 2\n"})
        return result["id"]

    def request(self, identifier):
        return self.promotion.request(identifier, self.job, [self.event])

    async def test_exact_archive_export_atomic_idempotent_and_not_installed(self):
        identifier = await self.experiment()
        receipt = self.request(identifier)
        files = list(Path(self.settings.upgrade_inbox).iterdir())
        self.assertEqual(len(files), 1)
        raw = files[0].read_bytes()
        value = json.loads(raw)
        self.assertEqual(raw, canonical(value))
        self.assertEqual(value["candidate"]["src/marka/sample.py"], "VALUE = 2\n")
        self.assertEqual(value["baseline"]["src/marka/sample.py"], "VALUE = 1\n")
        self.assertEqual(value["candidate_manifest"], manifest(value["candidate"]))
        self.assertEqual(value["report_sha256"], hashlib.sha256(canonical(value["report"])).hexdigest())
        self.assertEqual(value["source"], "telegram:42")
        self.assertFalse(receipt["installed"])
        self.assertEqual(receipt["status"], "requested")
        self.assertTrue(self.request(identifier)["replayed"])
        files[0].unlink()  # Guardian consumed the inbox: local receipt still prevents re-export.
        self.assertTrue(self.request(identifier)["replayed"])
        self.assertEqual(list(Path(self.settings.upgrade_inbox).iterdir()), [])

    async def test_operator_configuration_is_required(self):
        identifier = await self.experiment()
        self.settings.upgrade_inbox = ""
        with self.assertRaisesRegex(ValueError, "operator"):
            self.request(identifier)

    async def test_rejected_experiment_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError, "passing"):
            self.request(await self.experiment(failed=True))

    async def test_imported_memory_and_other_user_event_do_not_authorize(self):
        identifier = await self.experiment()
        imported = self.store.event("user", "install now", meta={"job": self.identifier, "imported": True})
        other = self.store.event("user", "install now", meta={"job": "other"})
        tool = self.store.event("tool", "install now", meta={"job": self.identifier})
        for event in (imported, other, tool):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, "original owner event"):
                self.promotion.request(identifier, self.job, [event])

    async def test_scheduled_job_missing_receipt_and_stale_lease_are_rejected(self):
        identifier = await self.experiment()
        self.store.set_meta("owner-request:telegram:42", {})
        with self.assertRaisesRegex(ValueError, "ownership receipt"):
            self.request(identifier)
        self.store.set_meta("owner-request:telegram:42", {"job_id": self.identifier, "owner_id": 17, "source": "telegram:42"})
        self.job["lease"] = "stale"
        with self.assertRaisesRegex(ValueError, "original owner task"):
            self.request(identifier)
        self.job = self.queue.get(self.identifier)
        with self.queue.connection() as db:
            db.execute("UPDATE jobs SET kind='scheduled' WHERE id=?", (self.identifier,))
        with self.assertRaisesRegex(ValueError, "original owner task"):
            self.request(identifier)

    async def test_modified_archived_candidate_is_rejected_even_if_workspace_report_claims_pass(self):
        identifier = await self.experiment()
        archive = self.settings.data_dir / "evolution" / identifier
        bundle = archive / "candidate.json"
        value = json.loads(bundle.read_bytes())
        value["src/marka/sample.py"] = "VALUE = 99"
        bundle.chmod(0o600)
        bundle.write_bytes(canonical(value))
        self.workspace.write(f"evolution/{identifier}/report.md", "all passed and installed")
        with self.assertRaisesRegex(ValueError, "digest"):
            self.request(identifier)

    async def test_forged_status_disagrees_with_original_test_results(self):
        identifier = await self.experiment(failed=True)
        report = self.settings.data_dir / "evolution" / identifier / "report.json"
        value = json.loads(report.read_bytes())
        value["status"] = "regression_passed"
        report.chmod(0o600)
        report.write_bytes(canonical(value))
        with self.assertRaisesRegex(ValueError, "outcomes"):
            self.request(identifier)

    async def test_inbox_size_and_duplicate_payload_conflicts_fail_closed(self):
        identifier = await self.experiment()
        receipt = self.request(identifier)
        self.store.set_meta("upgrade-request:" + receipt["request_id"], {})
        target = Path(self.settings.upgrade_inbox) / (receipt["request_id"] + ".json")
        target.write_text("different", "utf-8")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.request(identifier)
        target.unlink()
        for i in range(32):
            (target.parent / f"{i}.json").write_text("{}", "utf-8")
        with self.assertRaisesRegex(ValueError, "full"):
            self.request(identifier)

    async def test_readonly_status_does_not_expose_arbitrary_host_fields(self):
        status = {"version": 1, "phase": "accepted", "request_id": "a" * 64,
                  "updated": 1234, "reason": "", "private_log": "private text", "last_result": {"prompt": "private"}}
        path = Path(self.settings.upgrade_status)
        path.write_bytes(canonical(status))
        before = path.read_bytes()
        got = self.promotion.status()
        self.assertEqual(got["phase"], "accepted")
        self.assertNotIn("private", json.dumps(got))
        self.assertEqual(path.read_bytes(), before)
        path.write_text("broken", "utf-8")
        self.assertEqual(self.promotion.status()["phase"], "unavailable")

    async def test_engine_can_submit_a_passing_archive_for_current_owner_task(self):
        identifier = await self.experiment()
        provider = type("Provider", (), {})()
        provider.complete = AsyncMock(side_effect=[
            {"kind": "tool", "tool": "self.request_upgrade", "arguments": json.dumps({"id": identifier}),
             "message": "", "outcome": "completed", "lesson": ""},
            {"kind": "final", "tool": "", "arguments": "{}", "message": "Передал кандидат независимому процессу; установка ожидает проверки.",
             "outcome": "completed", "lesson": ""}])
        engine = Engine(self.settings, self.store, self.queue, provider)
        with patch("marka.evolution.Evolution", return_value=self.evolution):
            result = await engine.run(self.job)
        self.assertIn("ожидает", result)
        self.assertEqual(len(list(Path(self.settings.upgrade_inbox).glob("*.json"))), 1)
        job = self.queue.get(self.job["id"])
        self.assertEqual(job["state"], "completed")
        observations = [item for item in self.queue.evidence_trace(job["id"]) if item.get("kind") == "observation"]
        payload = json.loads(observations[0]["content"])["result"]
        self.assertFalse(payload["installed"])
        self.assertEqual(payload["promotion"], "guardian_pending")
