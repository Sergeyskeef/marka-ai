"""Acceptance of self tools through the actual model-tool boundary, without host evaluation."""

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.config import Settings
from marka.engine import Engine
from marka.evolution import Evolution
from marka.queue import Queue
from marka.store import Store
from marka.tools import Tools


class SelfToolRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "release" / "src" / "marka"
        self.tests = self.root / "release" / "tests"
        self.source.mkdir(parents=True)
        self.tests.mkdir()
        (self.source / "__init__.py").write_text("", "utf-8")
        self.original = "".join(f"VALUE_{number} = {number}\n" for number in range(1, 101))
        (self.source / "sample.py").write_bytes(self.original.encode("utf-8"))
        (self.tests / "test_sample.py").write_text("import unittest\nclass Sample(unittest.TestCase):\n    def test_value(self):\n        self.assertTrue(True)\n", "utf-8")
        self.settings = Settings(self.root / "state", sandbox_socket="/fake/socket")
        self.settings.prepare()
        self.store, self.queue = Store(self.settings.database), Queue(self.settings.database)
        self.tools = Tools(self.settings, self.store, self.queue)
        self.job = {"id": "routing-test", "chat_id": 17, "kind": "self_improve"}
        self.runs = []

    def evaluator(self, socket, argv, timeout, encoded):
        files = {name: base64.b64decode(value) for name, value in encoded.items()}
        self.runs.append(files)
        nonce = json.loads(files["eval_manifest.json"])["nonce"]
        outcomes = {"test_sample.Sample.test_value": "passed"}
        report = {"nonce": nonce, "tests_run": 1, "discovered_count": 1,
                  "discovered_sha256": hashlib.sha256(json.dumps(sorted(outcomes), separators=(",", ":")).encode()).hexdigest(),
                  "outcomes": outcomes, "test_integrity": True, "source_integrity": True,
                  "successful": True, "log": "", "failures": []}
        return {"exit_code": 0, "timed_out": False, "truncated": False,
                "output": "MARKA_EVAL_REPORT=" + json.dumps(report), "_files": {}}

    def factory(self, settings, workspace):
        return Evolution(settings, workspace, source_root=self.source, test_root=self.tests, runner=self.evaluator)

    async def test_inspect_pages_installed_source_and_rejects_state_paths(self):
        with patch("marka.evolution.Evolution", side_effect=self.factory):
            index = await self.tools.call("self.inspect", {}, self.job, [], 1)
            page = await self.tools.call("self.inspect", {"path": "src/marka/sample.py", "start_line": 50, "end_line": 55}, self.job, [], 2)
            with self.assertRaises(ValueError):
                await self.tools.call("self.inspect", {"path": "../state/settings.json"}, self.job, [], 3)
            with self.assertRaises(ValueError):
                await self.tools.call("self.inspect", {"path": "src/marka/sample.py", "start_line": True}, self.job, [], 4)
        self.assertIn("src/marka/sample.py", {row["path"] for row in index["files"]})
        self.assertEqual(page["content"], "".join(self.original.splitlines(keepends=True)[49:55]))
        self.assertEqual(page["total_lines"], 100)
        self.assertEqual(self.runs, [])

    async def test_experiment_routes_to_copies_and_exports_owner_deliverable_evidence(self):
        self.queue.enqueue("Correct value 50 and send the evidence", 17, kind="self_improve")
        self.job = self.queue.claim()
        candidate = self.original.replace("VALUE_50 = 50", "VALUE_50 = 500")
        with patch("marka.evolution.Evolution", side_effect=self.factory):
            result = await self.tools.call("self.experiment", {"objective": "Correct value 50",
                "changes": {"src/marka/sample.py": candidate}}, self.job, [], 1)
        self.assertEqual(result["status"], "regression_passed")
        self.assertEqual(result["promotion"], "none")
        self.assertEqual(len(self.runs), 2)
        self.assertEqual(self.runs[0]["src/marka/sample.py"].decode(), self.original)
        self.assertEqual(self.runs[1]["src/marka/sample.py"].decode(), candidate)
        self.assertEqual((self.source / "sample.py").read_text("utf-8"), self.original)
        for step, key in enumerate(("patch_path", "report_path"), 2):
            await self.tools.call("workspace.send", {"path": result[key]}, self.job, [], step)
        with self.queue.connection() as db:
            deliveries = list(db.execute("SELECT chat_id,document FROM deliveries ORDER BY id"))
        self.assertEqual([row["chat_id"] for row in deliveries], [17, 17])
        self.assertEqual([row["document"] for row in deliveries], [result["patch_path"], result["report_path"]])
        archive = self.settings.data_dir / "evolution" / result["id"]
        self.assertTrue((archive / "baseline-result.json").exists())
        self.assertTrue((archive / "candidate-result.json").exists())

    async def test_inspected_code_survives_next_model_context_beyond_old_two_k_limit(self):
        content = "# padding to make an ordinary source page longer than 2000 chars\n" * 60 + "END_OF_INSPECTED_SOURCE = 1\n"
        (self.source / "sample.py").write_text(content, "utf-8")
        prompts = []

        class Provider:
            async def complete(self, prompt, schema):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return {"kind": "tool", "tool": "self.inspect", "arguments": json.dumps({"path": "src/marka/sample.py"}),
                            "message": "", "outcome": "completed", "lesson": ""}
                return {"kind": "final", "tool": "", "arguments": "{}", "message": "Source inspected", "outcome": "completed", "lesson": ""}

        identifier = self.queue.enqueue("Inspect your source", 17, kind="self_improve")
        engine = Engine(self.settings, self.store, self.queue, Provider())
        with patch("marka.evolution.Evolution", side_effect=self.factory):
            await engine.run(self.queue.claim())
        data = json.loads(prompts[1].split("CONTEXT_DATA:\n", 1)[1])
        observation = json.loads(data["current_work_log"][-1]["content"])
        self.assertIn("END_OF_INSPECTED_SOURCE = 1", observation["result"]["content"])
        self.assertEqual(data["task_kind"], "self_improve")
        self.assertEqual(self.queue.get(identifier)["state"], "completed")
