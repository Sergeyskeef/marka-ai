import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from marka.config import Settings
from marka.engine import Engine
from marka.queue import Queue
from marka.store import Store
from marka.tools import Workspace
from test_engine import FakeProvider, context, final, tool


class RuntimeUpgradeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name), max_steps=3)
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)

    def enqueue(self, *, steps=48, seconds=900):
        identifier = self.queue.enqueue("Проверяемое поручение", 17)
        self.queue.configure_task(identifier, max_steps=steps, max_model_calls=64, max_seconds=seconds)
        return identifier

    async def test_long_task_continues_across_engines_with_single_final_and_preserved_budget(self):
        identifier = self.enqueue()
        provider = FakeProvider(*[tool("workspace.list") for _ in range(13)], final("Готово после 13 проверок"))
        runs = 0
        while self.queue.get(identifier)["state"] == "queued":
            # New objects simulate restart between bounded work slices.
            queue = Queue(self.settings.database)
            engine = Engine(self.settings, Store(self.settings.database), queue, provider)
            job = queue.claim()
            await engine.run(job)
            runs += 1
            self.assertLess(runs, 8)
        progress = self.queue.progress(identifier)
        self.assertEqual(progress["state"], "completed")
        self.assertEqual(progress["budget"]["used"]["steps"], 14)
        self.assertEqual(progress["budget"]["continuations"], 4)
        self.assertEqual(len(progress["steps"]), 13)
        with self.queue.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM deliveries WHERE source LIKE ?", (f"job:{identifier}:final:%",)).fetchone()[0], 1)
        self.assertEqual(len(provider.calls), 14)

    async def test_resume_does_not_refill_task_budget(self):
        identifier = self.enqueue(steps=4)
        provider = FakeProvider(*[tool("workspace.list") for _ in range(8)])
        engine = Engine(self.settings, self.store, self.queue, provider)
        while self.queue.get(identifier)["state"] == "queued":
            await engine.run(self.queue.claim())
        self.assertEqual(len(provider.calls), 4)
        self.assertTrue(self.queue.resume(identifier))
        await engine.run(self.queue.claim())
        self.assertEqual(len(provider.calls), 4)
        self.assertIn("/extend", self.queue.get(identifier)["error"])

    async def test_final_after_failed_execution_requests_real_recheck(self):
        self.settings.max_steps = 6
        self.settings.sandbox_socket = "fake-runner-boundary"
        identifier = self.enqueue()
        provider = FakeProvider(tool("code.run", {"argv": ["python", "-c", "print(1)"], "inputs": []}),
                                final("Всё проверено"),
                                tool("code.run", {"argv": ["python", "-c", "print(1)"], "inputs": []}), final("Проверено повторно"))
        engine = Engine(self.settings, self.store, self.queue, provider)
        with patch("marka.tools.sandbox.run_client", side_effect=[{"exit_code": 2, "output": "failed"}, {"exit_code": 0, "output": "1"}]):
            await engine.run(self.queue.claim())
        self.assertIn("runtime_verification", provider.calls[2][0])
        self.assertEqual(self.queue.get(identifier)["state"], "completed")
        self.assertEqual(self.queue.progress(identifier)["verification"]["status"], "observed")

    async def test_deadline_cancels_inflight_provider_and_keeps_charged_call(self):
        identifier = self.enqueue(seconds=60)
        job = self.queue.claim()
        reserve = self.queue.reserve_call
        def short_remaining(*args, **kwargs):
            receipt = reserve(*args, **kwargs)
            receipt["budget"]["remaining"]["seconds"] = 0.05
            return receipt
        stopped = asyncio.Event()
        class SlowProvider:
            async def complete(self, prompt, schema):
                try:
                    await asyncio.sleep(20)
                finally:
                    stopped.set()
        engine = Engine(self.settings, self.store, self.queue, SlowProvider())
        with patch.object(self.queue, "reserve_call", side_effect=short_remaining):
            await engine.run(job)
        self.assertTrue(stopped.is_set())
        self.assertEqual(self.queue.get(identifier)["state"], "blocked")
        self.assertEqual(self.store.budget_used(), 1)
        self.assertIn("/extend", self.queue.get(identifier)["error"])
        self.assertIsNone(engine.active_job)

    async def test_retrieval_failure_is_persisted_and_releases_active_job(self):
        identifier = self.enqueue()
        engine = Engine(self.settings, self.store, self.queue, FakeProvider(final()))
        with patch.object(engine.tools, "search", new=AsyncMock(side_effect=RuntimeError("index fixture failed"))):
            await engine.run(self.queue.claim())
        self.assertEqual(self.queue.get(identifier)["state"], "failed")
        self.assertIsNone(engine.active_job)

    async def test_selected_runner_inputs_ignore_unrelated_large_workspace(self):
        self.settings.sandbox_socket = "fake-boundary"
        self.settings.workspace.joinpath("huge.bin").write_bytes(b"x" * 1_100_000)
        self.settings.workspace.joinpath("main.py").write_text("print(1)", encoding="utf-8")
        identifier = self.enqueue()
        engine = Engine(self.settings, self.store, self.queue, FakeProvider(
            tool("code.run", {"argv": ["python", "main.py"], "inputs": ["main.py"]}), final()))
        with patch("marka.tools.sandbox.run_client", return_value={"exit_code": 0, "output": "1"}) as runner:
            await engine.run(self.queue.claim())
        self.assertEqual(set(runner.call_args.args[3]), {"main.py"})
        self.assertEqual(self.queue.get(identifier)["state"], "completed")

    async def test_precise_edit_conflict_does_not_destroy_original(self):
        workspace = Workspace(self.settings.workspace)
        initial = workspace.write("source.py", "line one\nline two\n")
        changed = workspace.replace("source.py", "line two", "line three", initial["sha256"])
        with self.assertRaisesRegex(ValueError, "changed"):
            workspace.replace("source.py", "line one", "lost", initial["sha256"])
        self.assertEqual(workspace.path("source.py").read_text("utf-8"), "line one\nline three\n")
        self.assertEqual(changed["sha256"], hashlib.sha256(b"line one\nline three\n").hexdigest())
        self.assertTrue(any(path.read_bytes() == b"line one\nline two\n" for path in (workspace.root / ".history").iterdir()))

    async def test_large_text_attachment_and_long_line_are_fully_readable_in_pages(self):
        workspace = Workspace(self.settings.workspace)
        original = "начало\n" + "длинная строка " * 14000 + "\nконец"
        workspace.write_bytes("large.txt", original.encode("utf-8"))
        page = workspace.read("large.txt")
        reconstructed = page["content"]
        while page["next_offset"] is not None:
            page = workspace.read("large.txt", offset=page["next_offset"])
            self.assertLessEqual(len(page["content"]), 12000)
            reconstructed += page["content"]
        self.assertEqual(reconstructed, original)
        self.assertFalse(page["truncated"])

    async def test_verified_script_becomes_reusable_skill_with_new_data_and_rechecked_outcome(self):
        self.settings.max_steps = 8
        self.settings.sandbox_socket = "fake-boundary"
        self.settings.workspace.joinpath("sum.py").write_text("import sys\nprint(sum(map(int, open(sys.argv[1]).read().split())))\n", "utf-8")
        self.settings.workspace.joinpath("data.txt").write_text("1 2", "utf-8")
        self.settings.workspace.joinpath("new-data.txt").write_text("4 5", "utf-8")
        def save_skill(prompt, schema):
            evidence = next(row["event_id"] for row in reversed(context(prompt)["current_work_log"]) if row["kind"] == "observation")
            return tool("skill.save", {"name": "sum-values", "description": "Sum integers in a text file", "event_id": evidence})
        provider = FakeProvider(tool("code.run", {"argv": ["python", "sum.py", "data.txt"], "inputs": ["sum.py", "data.txt"]}),
                                save_skill, tool("skill.run", {"name": "sum-values", "parameters": ["data.txt"],
                                                             "inputs": {"data.txt": "new-data.txt"}}), final("Новые данные проверены"))
        engine = Engine(self.settings, self.store, self.queue, provider)
        identifier = self.enqueue()
        with patch("marka.tools.sandbox.run_client", side_effect=[{"exit_code": 0, "timed_out": False, "output": "3"},
                                                               {"exit_code": 0, "timed_out": False, "output": "9"}]) as runner:
            await engine.run(self.queue.claim())
        self.assertEqual(runner.call_count, 2)
        import base64
        self.assertEqual(base64.b64decode(runner.call_args.args[3]["data.txt"]), b"4 5")
        self.assertEqual(runner.call_args.args[1], ["python", "sum.py", "data.txt"])
        self.assertEqual(self.queue.get(identifier)["state"], "completed")
        from marka.skills import SkillLibrary
        library = SkillLibrary(self.settings, self.store, self.queue)
        self.assertEqual(library.search("integers")[0]["name"], "sum-values")
        self.assertEqual(base64.b64decode(library.prepare("sum-values")["files"]["data.txt"]), b"1 2")
        with patch("marka.tools.sandbox.run_client") as runner:
            with self.assertRaisesRegex(ValueError, "immutable"):
                await engine.tools.call("skill.run", {"name": "sum-values", "inputs": {"sum.py": "new-data.txt"}}, self.queue.get(identifier), [], 9)
            runner.assert_not_called()

    async def test_large_cyrillic_tool_output_keeps_valid_canonical_failure_evidence(self):
        self.settings.sandbox_socket = "fake-boundary"
        identifier = self.enqueue()
        provider = FakeProvider(tool("code.run", {"argv": ["python", "-c", "pass"], "inputs": []}),
                                final("Требуется исправление", outcome="blocked"))
        engine = Engine(self.settings, self.store, self.queue, provider)
        output = "ошибка " * 4500
        with patch("marka.tools.sandbox.run_client", return_value={"exit_code": 2, "output": output, "timed_out": False}):
            await engine.run(self.queue.claim())
        with self.store._connect() as db:
            row = db.execute("SELECT content FROM events WHERE role='tool' AND session=?", ("work:" + identifier,)).fetchone()
        saved = json.loads(row["content"])
        self.assertEqual(saved["result"]["output"], output)
        self.assertEqual(self.queue.progress(identifier)["verification"]["status"], "contradicted")
