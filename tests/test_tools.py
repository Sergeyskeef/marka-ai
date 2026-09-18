"""Behavioral checks for workspace boundaries and owner-only effects."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.config import Settings
from marka.queue import Queue
from marka.store import Store
from marka.tools import Tools, Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "workspace"
        self.workspace = Workspace(self.root)

    def test_traversal_absolute_and_credential_paths_cannot_be_read_or_written(self):
        outside = Path(self.temporary.name) / "private.txt"
        outside.write_text("sentinel", encoding="utf-8")
        targets = ["../private.txt", "a/../../private.txt", str(outside),
                   "auth.json", "nested/settings.json", ".env", ".history/old",
                   "a/.hidden/value", "file:alternate", "bad\0name"]
        for target in targets:
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    self.workspace.read(target)
                with self.assertRaises(ValueError):
                    self.workspace.write(target, "changed")
        self.assertEqual(outside.read_text("utf-8"), "sentinel")

    def test_symlink_cannot_read_or_replace_outside_file(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("unchanged", encoding="utf-8")
        link = self.root / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name == "nt" and getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows account has no symlink creation privilege; run this case on Linux CI")
            raise
        with self.assertRaises(ValueError):
            self.workspace.read("linked/private.txt")
        with self.assertRaises(ValueError):
            self.workspace.write("linked/private.txt", "bad")
        self.assertEqual((outside / "private.txt").read_text("utf-8"), "unchanged")

    def test_previous_revision_preserves_exact_bytes_and_is_hidden_from_tools(self):
        original = b"original\r\n\x00binary-compatible\r\n"
        destination = self.root / "notes.txt"
        destination.write_bytes(original)
        updated = 'Новый текст\n"quotes"\t🙂'
        result = self.workspace.write("notes.txt", updated)
        self.assertEqual(destination.read_bytes(), updated.encode("utf-8"))
        revisions = list((self.root / ".history").iterdir())
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].read_bytes(), original)
        self.assertEqual(result["bytes"], len(updated.encode("utf-8")))
        self.assertNotIn(".history", [item["name"] for item in self.workspace.listing()])
        with self.assertRaises(ValueError):
            self.workspace.read(".history/" + revisions[0].name)

    def test_oversize_write_does_not_modify_previous_file(self):
        self.workspace.write("file.txt", "keep")
        with self.assertRaises(ValueError):
            self.workspace.write("file.txt", "x" * 120001)
        self.assertEqual((self.root / "file.txt").read_text(), "keep")

    def test_existing_temporary_target_is_not_overwritten(self):
        self.workspace.write("file.txt", "original")
        temporary = self.root / "file.txt.marka-tmp"
        temporary.write_text("owned by another operation", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.workspace.write("file.txt", "replace")
        self.assertEqual((self.root / "file.txt").read_text(), "original")
        self.assertEqual(temporary.read_text(), "owned by another operation")


class ToolAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name))
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)
        self.tools = Tools(self.settings, self.store, self.queue)
        self.queue.enqueue("owner request", 17)
        self.job = self.queue.claim()
        self.source = self.store.event("user", "owner source")

    async def call(self, name, args, *, job=None):
        return await self.tools.call(name, args, job or self.job, [self.source], 1)

    async def test_memory_proposal_cannot_smuggle_owner_acceptance(self):
        result = await self.call("memory.propose", {"content": "A hypothesis", "kind": "lesson",
                                "actor": "owner", "status": "accepted"})
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(self.store.list_memories("accepted"), [])
        self.assertEqual(self.store.list_memories()[0]["actor"], "model")
        with self.assertRaises(ValueError):
            await self.call("memory.accept", {"id": result["id"]})
        with self.assertRaises(ValueError):
            await self.call("memory.forget", {"id": result["id"]})

    async def test_file_delivery_uses_job_owner_not_model_supplied_recipient(self):
        self.tools.workspace.write("report.txt", "report")
        await self.call("workspace.send", {"path": "report.txt", "chat_id": 99999, "caption": "done"})
        delivery = self.queue.next_delivery()
        self.assertEqual(delivery["chat_id"], 17)
        self.assertEqual(delivery["document"], "report.txt")
        with self.assertRaises(ValueError):
            await self.call("workspace.send", {"path": "report.txt"}, job=self.job | {"chat_id": 0})

    async def test_scheduled_job_cannot_create_another_schedule(self):
        with self.assertRaises(ValueError):
            await self.call("task.schedule", {"prompt": "repeat", "delay_seconds": 10},
                            job=self.job | {"kind": "scheduled"})
        self.assertEqual(len(self.queue.list()), 1)

    async def test_schedule_enforces_finite_runs_and_minimum_interval(self):
        for args in [dict(prompt="repeat", delay_seconds=10, interval_seconds=1),
                     dict(prompt="repeat", delay_seconds=10, runs=101)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                await self.call("task.schedule", args)
        self.assertEqual(len(self.queue.list()), 1)

    async def test_code_runner_is_only_an_explicit_boundary_call(self):
        self.settings.sandbox_socket = "fake-socket"
        self.tools.workspace.write("script.py", "print('ok')\n")
        with patch("marka.tools.sandbox.run_client", return_value={"exit_code": 0, "output": "ok"}) as runner:
            result = await self.call("code.run", {"argv": ["python", "script.py"], "timeout": 4})
        runner.assert_called_once_with("fake-socket", ["python", "script.py"], 4,
                                      {"script.py": base64.b64encode(b"print('ok')\n").decode()})
        self.assertEqual(result["exit_code"], 0)
        with patch("marka.tools.sandbox.run_client") as runner:
            with self.assertRaises(ValueError):
                await self.call("code.run", {"argv": ["python", "script.py"], "timeout": 61})
            runner.assert_not_called()

    async def test_untrusted_runner_artifact_paths_are_validated_before_any_import(self):
        payload = base64.b64encode(b"artifact").decode()
        for path in ["../escape.txt", ".env", "auth.json", "nested/settings.json", "/absolute.txt", "C:\\outside.txt"]:
            with self.subTest(path=path):
                result = {"exit_code": 0, "_files": {"valid.txt": payload, path: payload}}
                with patch("marka.tools.sandbox.run_client", return_value=result):
                    with self.assertRaises(ValueError):
                        await self.call("code.run", {"argv": ["python", "script.py"]})
                self.assertFalse((self.settings.workspace / "valid.txt").exists())
                self.assertFalse((self.settings.data_dir / "escape.txt").exists())

    async def test_oversized_or_invalid_runner_artifacts_do_not_import_partial_files(self):
        valid = base64.b64encode(b"small").decode()
        oversized = base64.b64encode(b"x" * 524289).decode()
        excessive_total = {f"large-{i}.bin": base64.b64encode(b"x" * 500000).decode() for i in range(5)}
        for outputs in [{"first.txt": valid, "large.bin": oversized},
                        {"first.txt": valid, "invalid.bin": "not base64!"}, excessive_total,
                        {f"file-{i}.txt": valid for i in range(201)}]:
            with self.subTest(output_count=len(outputs)):
                with patch("marka.tools.sandbox.run_client", return_value={"exit_code": 0, "_files": outputs}):
                    with self.assertRaises(ValueError):
                        await self.call("code.run", {"argv": ["python", "script.py"]})
                self.assertEqual(self.tools.workspace.listing(), [])

    async def test_runner_binary_artifact_is_imported_with_original_revision(self):
        self.tools.workspace.write_bytes("output.bin", b"old\x00bytes")
        new = b"\x00\xff\xfePNG\r\n"
        with patch("marka.tools.sandbox.run_client", return_value={"exit_code": 0,
                   "_files": {"output.bin": base64.b64encode(new).decode()}}):
            result = await self.call("code.run", {"argv": ["python", "script.py"]})
        self.assertEqual((self.settings.workspace / "output.bin").read_bytes(), new)
        self.assertEqual(result["artifacts"][0]["bytes"], len(new))
        self.assertNotIn("_files", result)
        self.assertIn(b"old\x00bytes", [p.read_bytes() for p in (self.settings.workspace / ".history").iterdir()])


if __name__ == "__main__":
    unittest.main()
