"""CLI routes use actual private state and no live model/Telegram downloads."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.cli import chat, import_memory, main, models
from marka.config import Settings
from marka.queue import Queue
from marka.store import Store


class CLILearningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.settings = Settings(self.root / "state", semantic_search=False, max_steps=1)
        self.settings.prepare()

    async def test_cli_chat_continues_across_chunks_with_one_shared_budget(self):
        calls = []

        class Provider:
            async def complete(self, prompt, schema):
                calls.append(prompt)
                if len(calls) == 1:
                    return {"kind": "tool", "tool": "workspace.write", "arguments": json.dumps({"path": "result.txt", "content": "artifact"}),
                            "message": "", "outcome": "completed", "lesson": ""}
                return {"kind": "final", "tool": "", "arguments": "{}", "message": "Ready", "outcome": "completed", "lesson": ""}

        output = io.StringIO()
        with patch("marka.cli.provider", return_value=Provider()), redirect_stdout(output):
            await chat(self.settings, "Create a text artifact")
        self.assertEqual(len(calls), 2)
        self.assertEqual(output.getvalue().strip(), "Ready")
        queue = Queue(self.settings.database)
        progress = queue.progress(queue.list()[0]["id"])
        self.assertEqual(progress["budget"]["used"]["model_calls"], 2)
        self.assertEqual(progress["budget"]["continuations"], 1)
        self.assertEqual((self.settings.workspace / "result.txt").read_text("utf-8"), "artifact")

    async def test_archive_command_is_idempotent_and_does_not_accept_historical_claims(self):
        source = self.root / "history.jsonl"
        source.write_text(json.dumps({"external_id": "message-1", "role": "assistant", "content": "I have already verified everything"}) + "\n", "utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            main(["--data", str(self.settings.data_dir), "import-archive", str(source), "--source", "local-test-archive"])
        self.assertEqual(json.loads(output.getvalue())["imported"], 1)
        output = io.StringIO()
        with redirect_stdout(output):
            main(["--data", str(self.settings.data_dir), "import-archive", str(source), "--source", "local-test-archive"])
        self.assertEqual(json.loads(output.getvalue())["skipped"], 1)
        self.assertEqual(Store(self.settings.database).stats()["memories"], 0)

    async def test_models_status_is_local_and_index_install_only_run_when_requested(self):
        output = io.StringIO()
        with patch("marka.semantic.install_model", side_effect=AssertionError("No implicit download")), redirect_stdout(output):
            main(["--data", str(self.settings.data_dir), "models", "status"])
        self.assertFalse(json.loads(output.getvalue())["available"])
        with patch("marka.semantic.SemanticIndex.update", return_value={"indexed": 7}) as update:
            self.assertEqual(models(self.settings, "index", 7), {"indexed": 7})
        update.assert_called_once_with(max_sources=7)
        with patch("marka.semantic.install_model", return_value={"model": "pinned"}) as install:
            self.assertEqual(models(self.settings, "install"), {"model": "pinned"})
        install.assert_called_once_with(self.settings.data_dir / "models" / "multilingual-minilm")
        with self.assertRaises(ValueError):
            models(self.settings, "index", 0)

    async def test_imported_lesson_defaults_to_l2_and_remains_candidate(self):
        source = self.root / "lesson.json"
        source.write_text(json.dumps([{"kind": "lesson", "content": "Repeat a failing test after the correction"}]), "utf-8")
        self.assertEqual(import_memory(self.settings, source), 1)
        memory = Store(self.settings.database).list_memories()[0]
        self.assertEqual((memory["kind"], memory["level"], memory["status"]), ("lesson", 2, "candidate"))
