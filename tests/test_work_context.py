"""Independent fixtures for durable recall, valid context and loop recovery."""

from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.config import Settings
from marka.engine import Engine
from marka.queue import Queue, _snapshot_payload
from marka.store import Store
from marka.tools import ToolInputError, Tools
from marka.work_context import WorkContext, compact_observation
from test_engine import FakeProvider, context, final, tool


class WorkContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = Settings(Path(temporary.name), max_steps=8)
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)

    def claimed(self, prompt="Проверь исходник"):
        identifier = self.queue.enqueue(prompt, 17)
        self.queue.configure_task(identifier, max_steps=40, max_model_calls=48, max_seconds=900)
        return self.queue.claim()

    def record(self, job, number, name="self.inspect", *, args=None, outcome=None):
        args = args if args is not None else {"path": "src/marka/sample.py", "offset": 0}
        outcome = outcome if outcome is not None else {"ok": True, "result": {
            "path": "src/marka/sample.py", "sha256": "a" * 64,
            "offset": args.get("offset", 0), "next_offset": 12000, "content": "source"}}
        event_id = self.store.event("tool", json.dumps(outcome, ensure_ascii=False), session="work:" + job["id"],
                                    meta={"job": job["id"], "tool": name, "arguments": args})
        self.assertTrue(self.queue.record_step(job["id"], lease=job["lease"], number=number, name=name,
                                               arguments=args, outcome=outcome, event_id=event_id))
        return event_id

    def test_compacted_checkpoint_and_prompt_observations_remain_valid_json(self):
        job = self.claimed()
        observation = {"ok": True, "result": {"content": 'Большой текст \\"\n' * 2500,
                                                "nested": [{"description": "я" * 3000}]}}
        raw = json.dumps(observation, ensure_ascii=False)
        trace = [{"kind": "observation", "event_id": index + 1, "content": raw} for index in range(8)]
        trace[0]["content"] = '{"ok":true,"result":{"content":"legacy truncated'
        original = copy.deepcopy(trace)
        trimmed = Engine._trim_trace(trace)
        for item in trimmed:
            json.loads(item["content"])
        self.assertEqual(trace, original)
        engine = Engine(self.settings, self.store, self.queue, FakeProvider())
        payload = context(engine.prompt(job, trimmed))
        self.assertTrue(payload["current_work_log"])
        for item in payload["current_work_log"]:
            json.loads(item["content"])
        self.assertIn("task_working_memory", payload)
        shortened = json.loads(compact_observation(raw, 2000))
        self.assertTrue(shortened["ok"])
        self.assertEqual(shortened["context_summary"]["full_evidence"], "task.recall")

    def test_recall_restores_full_old_canonical_output_after_restart_and_truncated_checkpoint(self):
        job = self.claimed()
        observation = {"ok": True, "result": {"output": "Ж" * 30000 + "END_OF_REAL_OBSERVATION"}}
        event_id = self.record(job, 1, "code.run", args={"argv": ["python", "sample.py"]}, outcome=observation)
        self.queue.checkpoint(job["id"], [{"kind": "observation", "event_id": event_id, "content": '{"ok":true,"result":'}], lease=job["lease"])
        self.assertTrue(self.queue.progress(job["id"])["steps"][0]["outcome"]["truncated"])
        restarted = WorkContext(Queue(self.settings.database))
        pieces, offset, digests = [], 0, set()
        while True:
            page = restarted.recall(job["id"], 1, offset=offset, limit=7000)
            self.assertTrue(page["canonical_event"])
            self.assertTrue(page["read_only"])
            self.assertLessEqual(len(page["content"]), 7000)
            pieces.append(page["content"])
            digests.add(page["sha256"])
            offset = page["next_offset"]
            if offset is None:
                break
        full = "".join(pieces)
        self.assertEqual(json.loads(full), observation)
        self.assertEqual(digests, {hashlib.sha256(full.encode()).hexdigest()})

    def test_recall_never_borrows_wrong_job_role_session_tool_or_invalid_metadata(self):
        job = self.claimed()
        variants = [
            ("assistant", "work:" + job["id"], {"job": job["id"], "tool": "self.inspect"}),
            ("tool", "work:another", {"job": job["id"], "tool": "self.inspect"}),
            ("tool", "work:" + job["id"], {"job": "another", "tool": "self.inspect"}),
            ("tool", "work:" + job["id"], {"job": job["id"], "tool": "code.run"}),
            ("tool", "work:" + job["id"], []),
        ]
        local = {"ok": False, "error": "LOCAL_OBSERVATION"}
        for number, (role, session, meta) in enumerate(variants, 1):
            with self.subTest(number=number):
                event_id = self.store.event(role, '{"ok":true,"result":"FOREIGN_CANARY"}', session=session)
                with self.store._connect() as db:
                    db.execute("UPDATE events SET meta=? WHERE id=?", (json.dumps(meta), event_id))
                self.queue.record_step(job["id"], lease=job["lease"], number=number, name="self.inspect", outcome=local, event_id=event_id)
                page = WorkContext(self.queue).recall(job["id"], number)
                self.assertFalse(page["canonical_event"])
                self.assertNotIn("FOREIGN_CANARY", page["content"])
                self.assertEqual(json.loads(page["content"]), local)

    async def test_recall_tool_cannot_select_another_job(self):
        first = self.claimed()
        self.record(first, 1, outcome={"ok": True, "result": "FIRST_JOB_ONLY"})
        self.queue.finish(first["id"], "blocked", lease=first["lease"])
        second = self.claimed()
        tools = Tools(self.settings, self.store, self.queue)
        with self.assertRaises(ValueError):
            WorkContext(self.queue).recall(second["id"], 1)
        with self.assertRaises((ValueError, ToolInputError)):
            await tools.call("task.recall", {"number": 1, "job_id": first["id"]}, second, [], 1)
        self.record(second, 1, outcome={"ok": True, "result": "SECOND_JOB_ONLY"})
        result = await tools.call("task.recall", {"number": 1}, second, [], 2)
        self.assertNotIn("FIRST_JOB_ONLY", result["content"])
        self.assertIn("SECOND_JOB_ONLY", result["content"])

    def test_recall_redacts_legacy_values_without_changing_canonical_event(self):
        job = self.claimed()
        fake_token = "1234567890:" + "SyntheticCanary_" + "x" * 19
        original = json.dumps({"ok": True, "result": {"text": "legacy\\n" + fake_token,
                                                      "api_key": {"nested": "STRUCTURED_CANARY"}}})
        event_id = self.record(job, 1, outcome={"ok": True, "result": "previous observation"})
        with self.store._connect() as db:
            db.execute("UPDATE events SET content=? WHERE id=?", (original, event_id))
            db.execute("UPDATE task_steps SET outcome=? WHERE job_id=? AND number=1", (original, job["id"]))
        result = WorkContext(self.queue).recall(job["id"], 1)
        self.assertNotIn(fake_token, result["content"])
        self.assertNotIn("STRUCTURED_CANARY", result["content"])
        self.assertIn("REDACTED", result["content"])
        with self.store._connect() as db:
            self.assertEqual(db.execute("SELECT content FROM events WHERE id=?", (event_id,)).fetchone()[0], original)

    def test_changed_canonical_event_cannot_replace_intact_or_hashed_task_evidence(self):
        job = self.claimed()
        intact = {"ok": True, "result": {"exit_code": 2, "output": "ORIGINAL_FAILURE"}}
        large = {"ok": True, "result": {"exit_code": 2, "output": "Ж" * 30000 + "ORIGINAL_FAILURE"}}
        for number, original in enumerate((intact, large), 1):
            with self.subTest(number=number):
                event_id = self.record(job, number, "code.run", outcome=original)
                saved = WorkContext(self.queue).recall(job["id"], number)
                self.assertTrue(saved["canonical_event"])
                with self.store._connect() as db:
                    db.execute("UPDATE events SET content=? WHERE id=?", ('{"ok":true,"result":{"exit_code":0,"output":"FORGED_SUCCESS"}}', event_id))
                recalled = WorkContext(self.queue).recall(job["id"], number)
                self.assertFalse(recalled["canonical_event"])
                self.assertNotIn("FORGED_SUCCESS", recalled["content"])
                pieces = [recalled["content"]]
                while recalled["next_offset"] is not None:
                    recalled = WorkContext(self.queue).recall(job["id"], number, offset=recalled["next_offset"])
                    pieces.append(recalled["content"])
                result = json.loads("".join(pieces))
                if number == 1:
                    self.assertEqual(result, intact)
                else:
                    self.assertTrue(result["truncated"])

    def test_repeated_unchanged_reads_warn_at_three_and_block_at_five_across_restart(self):
        job = self.claimed()
        for number in range(1, 6):
            self.record(job, number)
            guard = WorkContext(Queue(self.settings.database)).summary(job["id"])["loop_guard"]
            self.assertEqual(guard["same_read_count"], number)
            self.assertEqual(guard["status"], "blocked" if number == 5 else "warning" if number >= 3 else "clear")

    def test_repeated_errors_block_at_four_and_narrative_plan_is_not_progress(self):
        job = self.claimed()
        for number in range(1, 5):
            self.record(job, number * 2 - 1, outcome={"ok": False, "error": "same failure"})
            self.record(job, number * 2, "task.plan", args={"steps": ["I will try again"]}, outcome={"ok": True, "result": "plan saved"})
        guard = WorkContext(self.queue).summary(job["id"])["loop_guard"]
        self.assertEqual(guard["same_failure_count"], 4)
        self.assertEqual(guard["status"], "blocked")

    def test_failed_execution_and_rejected_experiment_do_not_reset_failure_counts(self):
        for name in ("code.run", "self.experiment"):
            with self.subTest(name=name):
                job = self.claimed()
                for number in range(1, 5):
                    result = ({"exit_code": 2, "output": "same failure", "duration": number / 10,
                               "input_manifest": {"sample.py": "a" * 64}}
                              if name == "code.run" else {"status": "rejected", "reason": "same regression",
                                                          "id": str(number) * 32, "duration": number})
                    self.record(job, number, name, args={"request": "same action"}, outcome={"ok": True, "result": result})
                guard = WorkContext(self.queue).summary(job["id"])["loop_guard"]
                self.assertEqual(guard["same_failure_count"], 4)
                self.assertEqual(guard["status"], "blocked")

    def test_corrected_runner_input_manifest_distinguishes_new_attempt(self):
        job = self.claimed()
        for number in range(1, 5):
            result = {"exit_code": 2, "input_manifest": {"sample.py": str(number) * 64}}
            self.record(job, number, "code.run", args={"argv": ["python", "sample.py"]}, outcome={"ok": True, "result": result})
        guard = WorkContext(self.queue).summary(job["id"])["loop_guard"]
        self.assertEqual(guard["same_failure_count"], 1)
        self.assertEqual(guard["status"], "clear")

    def test_different_pages_versions_and_real_actions_do_not_create_false_read_loop(self):
        job = self.claimed()
        for number in range(1, 9):
            self.record(job, number, args={"path": "src/marka/sample.py", "offset": number * 12000})
        guard = WorkContext(self.queue).summary(job["id"])["loop_guard"]
        self.assertEqual(guard["status"], "clear")
        self.assertEqual(guard["same_read_count"], 1)
        for number in range(9, 12):
            self.record(job, number)
        self.assertEqual(WorkContext(self.queue).summary(job["id"])["loop_guard"]["status"], "warning")
        self.record(job, 12, "workspace.write", args={"path": "fixed.py"}, outcome={"ok": True, "result": {"path": "fixed.py"}})
        for number in range(13, 16):
            self.record(job, number, outcome={"ok": True, "result": {"path": "src/marka/sample.py", "sha256": str(number) * 32,
                                                                      "offset": 0, "content": "new version"}})
        guard = WorkContext(self.queue).summary(job["id"])["loop_guard"]
        self.assertEqual(guard["status"], "clear")
        self.assertEqual(guard["same_read_count"], 1)
        self.assertEqual(guard["static_reads_since_action"], 3)

    async def test_engine_continuations_preserve_repeat_counts_and_stop_before_sixth_read(self):
        self.settings.max_steps = 2
        job = self.claimed()
        identifier = job["id"]
        decisions = [tool("self.inspect", {"path": "src/marka/sample.py"}) for _ in range(8)]
        for decision in decisions:
            decision["message"] = "I already changed everything (untrusted narration)"
        provider = FakeProvider(*decisions)
        reads, statuses = [], []

        async def read(*args, **kwargs):
            reads.append("executed")
            return {"path": "src/marka/sample.py", "sha256": "a" * 64, "content": "same source"}

        async def progress(_, status):
            self.assertTrue(reads, "No progress callback before the actual action")
            self.assertTrue(self.queue.progress(identifier)["steps"], "Observation must be durable first")
            statuses.append(status)

        batches = 0
        while job:
            engine = Engine(self.settings, Store(self.settings.database), Queue(self.settings.database), provider, progress)
            with patch.object(engine.tools, "call", side_effect=read):
                await engine.run(job)
            batches += 1
            if self.queue.get(identifier)["state"] != "queued":
                break
            job = self.queue.claim()
        self.assertEqual(batches, 3)
        self.assertEqual(len(reads), 5)
        self.assertEqual(len(provider.calls), 5)
        self.assertEqual(self.queue.get(identifier)["state"], "blocked")
        self.assertEqual(self.queue.progress(identifier)["budget"]["continuations"], 2)
        self.assertEqual(WorkContext(self.queue).summary(identifier)["loop_guard"]["same_read_count"], 5)
        self.assertEqual(statuses, [""] * 4, "Read liveness must follow actual results, not narrate imagined work")

    async def test_scripted_agent_uses_warning_to_change_approach_and_completes(self):
        job = self.claimed()
        for_read = tool("self.inspect", {"path": "src/marka/sample.py"})

        def change_approach(prompt, schema):
            self.assertEqual(context(prompt)["task_working_memory"]["loop_guard"]["status"], "warning")
            return tool("self.search", {"query": "target", "path": "src/marka/sample.py"})

        provider = FakeProvider(for_read, for_read, for_read, change_approach, final("Нужный участок найден"))
        engine = Engine(self.settings, self.store, self.queue, provider)

        async def execute(name, args, *unused):
            if name == "self.search":
                return {"matches": [{"path": "src/marka/sample.py", "line": 9, "excerpt": "target"}]}
            return {"path": "src/marka/sample.py", "sha256": "a" * 64, "content": "source"}

        with patch.object(engine.tools, "call", side_effect=execute):
            result = await engine.run(job)
        self.assertEqual(result, "Нужный участок найден")
        self.assertEqual(self.queue.get(job["id"])["state"], "completed")
        self.assertEqual(len(provider.calls), 5)


class WorkContextLargeEvidenceTests(unittest.TestCase):
    """Real SQLite and real ledger compaction without filesystem I/O."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE task_steps(job_id TEXT,number INTEGER,name TEXT,arguments TEXT,outcome TEXT,event_id INTEGER);
            CREATE TABLE events(id INTEGER PRIMARY KEY,role TEXT,session TEXT,meta TEXT,content TEXT);
        """)
        database = self.db

        class MemoryQueue:
            @contextmanager
            def connection(self):
                with database:
                    yield database

        self.context = WorkContext(MemoryQueue())
        self.job = "large-evidence-task"
        self.args = {"argv": ["python", "script.py"]}

    def record(self, number, *, exit_code=2, large=False):
        observation = {"ok": True, "result": {"exit_code": exit_code,
            "output": "x" * (50000 if large else 10),
            "input_manifest": {"script.py": "a" * 64}}}
        content = json.dumps(observation, ensure_ascii=False, allow_nan=False)
        saved = _snapshot_payload(observation, 48000)
        self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (number, "tool", "work:" + self.job,
            json.dumps({"job": self.job, "tool": "code.run"}), content))
        self.db.execute("INSERT INTO task_steps VALUES(?,?,?,?,?,?)", (self.job, number, "code.run",
            json.dumps(self.args), saved, number))
        self.db.commit()
        return observation, saved

    def test_large_failed_commands_are_counted_from_hash_verified_same_task_events(self):
        for number in range(1, 5):
            _, saved = self.record(number, large=True)
            self.assertTrue(json.loads(saved)["truncated"])
            self.assertNotIn("ok", json.loads(saved))
        before = [tuple(row) for row in self.db.execute("SELECT * FROM task_steps ORDER BY number")]
        guard = self.context.summary(self.job)["loop_guard"]
        self.assertEqual(guard["same_failure_count"], 4)
        self.assertEqual(guard["status"], "blocked")
        self.assertEqual([tuple(row) for row in self.db.execute("SELECT * FROM task_steps ORDER BY number")], before)

    def test_forged_large_canonical_event_neither_resets_nor_increments_failure_guard(self):
        for forged_exit in (0, 2):
            with self.subTest(forged_exit=forged_exit):
                self.db.execute("DELETE FROM task_steps")
                self.db.execute("DELETE FROM events")
                for number in range(1, 4):
                    self.record(number)
                original, saved = self.record(4, exit_code=2 if forged_exit == 0 else 0, large=True)
                forged = copy.deepcopy(original)
                forged["result"]["exit_code"] = forged_exit
                self.db.execute("UPDATE events SET content=? WHERE id=4", (json.dumps(forged),))
                self.db.commit()
                guard = self.context.summary(self.job)["loop_guard"]
                self.assertEqual(guard["same_failure_count"], 3)
                self.assertEqual(guard["status"], "warning")
                self.assertEqual(self.db.execute("SELECT outcome FROM task_steps WHERE number=4").fetchone()[0], saved)


if __name__ == "__main__":
    unittest.main()
