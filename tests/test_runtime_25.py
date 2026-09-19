"""Whole task tests: objective results, dated memory and bounded server reads."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from marka.app import Application
from marka.config import Settings
from marka.engine import Engine
from marka.memory_context import MemoryContext
from marka.queue import Queue
from marka.store import Store
from marka.tools import Tools, ToolInputError


def decision(name=None, args=None, message="Готово"):
    return {"kind": "tool" if name else "final", "tool": name or "",
            "arguments": json.dumps(args or {}), "message": message,
            "outcome": "completed", "lesson": ""}


class Model:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    async def complete(self, prompt, schema):
        self.prompts.append(prompt)
        return self.answers.pop(0)


class Runtime25Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(Path(self.temp.name), semantic_search=False, max_steps=8)
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)

    def engine(self, *answers):
        model = Model(*answers)
        engine = Engine(self.settings, self.store, self.queue, model)
        job_id = self.queue.enqueue("Сохрани result.json: поле status должно быть ready", 17)
        job = self.queue.claim()
        return engine, model, job

    def criteria(self):
        return decision("task.criteria", {"criteria": [
            {"id": "status", "kind": "json_matches", "path": "result.json",
             "assertions": [{"pointer": "/status", "equals": "ready"}]}]})

    async def test_false_success_stays_blocked_despite_existing_file_and_zero_errors(self):
        engine, model, job = self.engine(self.criteria(),
            decision("workspace.write", {"path": "result.json", "content": '{"status":"wrong"}'}),
            decision(), decision(), decision())
        await engine.run(job)
        final = self.queue.get(job["id"])
        self.assertEqual(final["state"], "blocked")
        progress = self.queue.progress(job["id"])
        self.assertEqual(progress["verification"]["acceptance"]["status"], "failed")
        self.assertIn("criteria", model.prompts[-1])

    async def test_failed_criterion_can_be_repaired_and_then_completed(self):
        engine, model, job = self.engine(self.criteria(),
            decision("workspace.write", {"path": "result.json", "content": '{"status":"wrong"}'}),
            decision(),
            decision("workspace.write", {"path": "result.json", "content": '{"status":"ready"}'}),
            decision())
        await engine.run(job)
        self.assertEqual(self.queue.get(job["id"])["state"], "completed")
        self.assertEqual(self.queue.progress(job["id"])["verification"]["acceptance"]["status"], "pass")

    async def test_progress_contains_frozen_criteria_after_restart(self):
        from marka.acceptance import freeze_criteria
        engine, model, job = self.engine()
        criteria = [{"id": "report", "kind": "artifact", "path": "report.txt"}]
        freeze_criteria(self.queue, job["id"], job["lease"], criteria)
        other = Tools(self.settings, Store(self.settings.database), Queue(self.settings.database))
        progress = await other.call("task.progress", {}, job, [], 1)
        self.assertEqual(progress["acceptance_criteria"]["criteria"][0]["path"], "report.txt")
        with self.assertRaises(ToolInputError):
            await other.call("task.criteria", {"criteria": []}, job, [], 2)

    async def test_expired_memory_reaches_prompt_with_recheck_marker(self):
        source = self.store.event("user", "Публичный пилот проекта пока отложен")
        memory_id = self.store.remember("Публичный пилот проекта отложен", sources=[source], actor="owner", status="accepted")
        MemoryContext(self.store).annotate(memory_id, label="dated_observation", valid_until="2020-01-01T00:00:00Z")
        engine, _, job = self.engine(decision())
        job["prompt"] = "проект пилот"
        context = json.loads(engine.prompt(job, []).split("\nCONTEXT_DATA:\n")[1])
        records = context["relevant_memories"] + context["recent_accepted_knowledge"]
        matching = [row for row in records if row["id"] == memory_id]
        self.assertTrue(matching)
        self.assertTrue(all(row["memory_context"]["needs_recheck"] for row in matching))
        self.assertEqual(self.store.get_memory(memory_id)["status"], "accepted")

    async def test_model_cannot_supply_owner_actor_for_memory_metadata(self):
        source = self.store.event("user", "An actual instruction")
        memory_id = self.store.remember("A candidate", sources=[source])
        tools = Tools(self.settings, self.store, self.queue)
        with self.assertRaises(ToolInputError):
            await tools.call("memory.annotate", {"id": memory_id, "label": "decision", "actor": "owner"}, {}, [source], 1)

    async def test_server_tool_cannot_add_path_or_command_fields(self):
        self.settings.bridge_socket = "/run/example.sock"
        tools = Tools(self.settings, self.store, self.queue)
        with patch("marka.bridge_client.server_read", new_callable=AsyncMock) as read:
            with self.assertRaises(ToolInputError):
                await tools.call("server.read", {"section": "status", "path": "/etc/shadow"}, {}, [], 1)
            read.assert_not_called()
            read.return_value = {"content": "diagnostics", "stale": False}
            result = await tools.call("server.read", {"section": "status"}, {}, [], 1)
            self.assertEqual(result["content"], "diagnostics")
            read.assert_awaited_once_with("/run/example.sock", "status", offset=0, expected_sha256="")

    async def test_status_displays_explicit_model_effort_without_claiming_resolved(self):
        from test_app import FakeClient, update
        self.settings.model = "gpt-5.6-sol"
        self.settings.reasoning_effort = "high"
        app = Application(self.settings, provider=Model(), client=FakeClient())
        app.store.set_meta("owner_id", 17)
        await app.ingest(update(1, "/status"))
        with app.queue.connection() as db:
            text = db.execute("SELECT text FROM deliveries").fetchone()[0]
        self.assertIn("gpt-5.6-sol", text)
        self.assertIn("high", text)
        self.assertIn("точное внутреннее имя не подтверждено", text)

    async def test_connection_tools_reject_secret_and_arbitrary_endpoint_arguments(self):
        self.settings.bridge_socket = "/run/example.sock"
        tools = Tools(self.settings, self.store, self.queue)
        with patch("marka.bridge_client.connections_check", new_callable=AsyncMock) as check:
            for args in ({"connection": "openai_speech", "url": "https://example.org"},
                         {"connection": "telegram", "key": "private"}, {"connection": []}):
                with self.assertRaises(ToolInputError):
                    await tools.call("connections.check", args, {}, [], 1)
            check.assert_not_called()
            check.return_value = {"ok": True, "verification_scope": "model_metadata", "inference_performed": False}
            result = await tools.call("connections.check", {"connection": "openai_speech"}, {}, [], 1)
            self.assertEqual(result["verification_scope"], "model_metadata")
            self.assertFalse(result["inference_performed"])

    async def test_connection_command_preserves_limited_verification_scope(self):
        from test_app import FakeClient, update
        self.settings.bridge_socket = "/run/example.sock"
        app = Application(self.settings, provider=Model(), client=FakeClient())
        app.store.set_meta("owner_id", 17)
        with patch("marka.bridge_client.connections_check", new_callable=AsyncMock) as check:
            check.return_value = {"ok": True, "verification_scope": "model_metadata",
                                  "details": {"transcription_verified": False}}
            await app.ingest(update(1, "/connections openai_speech"))
        with app.queue.connection() as db:
            text = db.execute("SELECT text FROM deliveries").fetchone()[0]
        self.assertIn("model_metadata", text)
        self.assertIn('"transcription_verified": false', text)

    def test_unrelated_diagnostic_success_cannot_erase_a_failed_target(self):
        from marka.evaluation import verify_completion
        for name, first, second in (
            ("connections.check", {"connection": "openai_speech"}, {"connection": "telegram"}),
            ("server.read", {"section": "events"}, {"section": "status"}),
            ("server.read", {"section": "guardian_source", "offset": 12000}, {"section": "guardian_source"}),
        ):
            trace = [{"kind": "tool", "name": name, "arguments": first},
                     {"kind": "observation", "content": {"ok": True, "result": {"error": "unavailable"}}},
                     {"kind": "tool", "name": name, "arguments": second},
                     {"kind": "observation", "content": {"ok": True, "result": {"ok": True}}}]
            self.assertEqual(verify_completion(trace)["status"], "contradicted")
            trace.extend([{"kind": "tool", "name": name, "arguments": first},
                          {"kind": "observation", "content": {"ok": True, "result": {"ok": True}}}])
            self.assertEqual(verify_completion(trace)["status"], "observed")

    async def test_server_owner_command_preserves_snapshot_age(self):
        from test_app import FakeClient, update
        self.settings.bridge_socket = "/run/example.sock"
        app = Application(self.settings, provider=Model(), client=FakeClient())
        app.store.set_meta("owner_id", 17)
        with patch("marka.bridge_client.server_read", new_callable=AsyncMock) as read:
            read.return_value = {"content": "technical data", "age_seconds": 250, "stale": True}
            await app.ingest(update(1, "/server"))
        with app.queue.connection() as db:
            text = db.execute("SELECT text FROM deliveries").fetchone()[0]
        self.assertIn("250", text)
        self.assertIn("требуется обновление", text)


if __name__ == "__main__":
    unittest.main()
