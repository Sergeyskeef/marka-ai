"""Gateway integration checks with SQLite persistence and no Telegram network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.app import Application, issue_pairing
from marka.config import Settings
from marka.telegram import TelegramError


def update(identifier=1, text="hello", *, user=17, chat=None, chat_type="private", **fields):
    return {"update_id": identifier, "message": {"message_id": identifier,
            "from": {"id": user, "is_bot": False},
            "chat": {"id": user if chat is None else chat, "type": chat_type},
            "text": text, **fields}}


class FakeClient:
    def __init__(self):
        self.sent = []
        self.on_send = None
        self.error = None

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        if self.on_send:
            self.on_send()
        if self.error:
            raise self.error
        return [100 + len(self.sent)]

    async def send_document(self, chat_id, path, caption=""):
        self.sent.append((chat_id, Path(path).read_bytes(), caption))
        if self.on_send:
            self.on_send()
        return 101


class FinalProvider:
    def __init__(self):
        self.calls = []
        self.on_call = None

    async def complete(self, prompt, schema):
        self.calls.append(prompt)
        if self.on_call:
            self.on_call()
        return {"kind": "final", "tool": "", "arguments": "{}", "message": "Проверенный ответ",
                "outcome": "completed", "lesson": ""}


class AppAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name) / "state")
        self.settings.prepare()
        self.client = FakeClient()
        self.provider = FinalProvider()
        self.app = Application(self.settings, provider=self.provider, client=self.client)

    def restart(self):
        self.app = Application(self.settings, provider=self.provider, client=self.client)
        return self.app

    def owner(self):
        self.app.store.set_meta("owner_id", 17)

    def delivery_rows(self):
        with self.app.queue.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM deliveries ORDER BY id")]

    async def test_cancel_without_identifier_preserves_work_and_future_reminders(self):
        self.owner()
        current = self.app.queue.enqueue("working", 17)
        future = self.app.queue.enqueue("reminder", 17, kind="scheduled", due=9999999999)
        claimed = self.app.queue.claim()
        self.assertEqual(claimed["id"], current)
        await self.app.ingest(update(1, "/cancel"))
        self.assertEqual(self.app.queue.get(current)["state"], "running")
        self.assertEqual(self.app.queue.get(future)["state"], "queued")
        self.assertIn("/cancel номер", self.delivery_rows()[0]["text"])
        await self.app.ingest(update(2, "/cancel " + future))
        self.assertEqual(self.app.queue.get(current)["state"], "running")
        self.assertEqual(self.app.queue.get(future)["state"], "cancelled")
        await self.app.ingest(update(3, "/stop"))
        self.assertEqual(self.app.queue.get(current)["state"], "cancelled")

    async def test_pairing_requires_local_code_and_matching_private_human_chat(self):
        code = issue_pairing(self.app.store)
        attempts = [update(1, "/start wrong"),
                    update(2, "/start " + code, chat=-17, chat_type="group"),
                    update(3, "/start " + code, chat=18),
                    update(4, "/start " + code, forward_origin={"type": "user"})]
        for attempt in attempts:
            await self.app.ingest(attempt)
            self.assertIsNone(self.app.store.get_meta("owner_id"))
        await self.app.ingest(update(5, "/start " + code))
        self.assertEqual(self.app.store.get_meta("owner_id"), 17)
        self.assertEqual(self.app.store.get_meta("pairing"), {})
        self.assertEqual(self.app.queue.offset(), 6)
        self.assertEqual(len(self.delivery_rows()), 1)
        self.assertEqual(self.app.store.history(), [])
        self.assertNotIn(code, json.dumps(self.delivery_rows()))
        self.restart()
        self.assertEqual(self.app.store.get_meta("owner_id"), 17)
        self.assertEqual(self.app.queue.offset(), 6)
        with self.assertRaises(ValueError):
            issue_pairing(self.app.store)
        self.assertEqual(self.provider.calls, [])

    async def test_expired_code_and_foreign_sender_never_gain_access(self):
        code = issue_pairing(self.app.store)
        pairing = self.app.store.get_meta("pairing")
        self.app.store.set_meta("pairing", pairing | {"expires": 1})
        await self.app.ingest(update(1, "/start " + code))
        self.assertIsNone(self.app.store.get_meta("owner_id"))
        self.owner()
        await self.app.ingest(update(2, "/task write something", user=99))
        await self.app.ingest(update(3, "do this", user=17, chat=99))
        self.assertEqual(self.app.queue.list(), [])
        self.assertEqual(self.delivery_rows(), [])
        self.assertEqual(self.app.queue.offset(), 4)

    async def test_pairing_transaction_rolls_back_if_receipt_cannot_be_saved(self):
        code = issue_pairing(self.app.store)
        with patch.object(self.app, "_reply_in_transaction", side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(update(1, "/start " + code))
        self.assertIsNone(self.app.store.get_meta("owner_id"))
        self.assertTrue(self.app.store.get_meta("pairing")["hash"])
        self.assertEqual(self.app.queue.offset(), 0)
        self.restart()
        await self.app.ingest(update(1, "/start " + code))
        self.assertEqual(self.app.store.get_meta("owner_id"), 17)
        self.assertEqual(len(self.delivery_rows()), 1)

    async def test_duplicate_text_update_after_cursor_crash_creates_one_job(self):
        self.owner()
        message = update(7, "Create an artifact")
        with patch.object(self.app.queue, "advance", side_effect=RuntimeError("before cursor commit")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(message)
        self.assertEqual(len(self.app.queue.list()), 1)
        self.assertEqual(self.app.queue.offset(), 0)
        self.restart()
        await self.app.ingest(message)
        await self.app.ingest(message)
        self.assertEqual(len(self.app.queue.list()), 1)
        self.assertEqual(self.app.queue.offset(), 8)

    async def test_remember_replay_after_cursor_crash_is_exactly_one_effect(self):
        self.owner()
        message = update(7, "/remember report uses UTC")
        with patch.object(self.app.queue, "advance", side_effect=RuntimeError("before cursor commit")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(message)
        self.assertEqual(self.app.store.stats()["memories"], 1)
        self.assertEqual(self.app.store.stats()["events"], 1)
        self.restart()
        await self.app.ingest(message)
        self.assertEqual(self.app.store.stats()["memories"], 1)
        self.assertEqual(self.app.store.stats()["events"], 1)
        self.assertEqual(len(self.delivery_rows()), 1)
        self.assertEqual(self.app.queue.offset(), 8)
        # An intentionally repeated owner statement in a new update is new evidence.
        await self.app.ingest(update(8, "/remember report uses UTC"))
        self.assertEqual(self.app.store.stats()["memories"], 2)
        self.assertEqual(self.app.store.stats()["events"], 2)

    async def test_remember_source_memory_and_receipt_rollback_together(self):
        self.owner()
        with patch.object(self.app, "_reply_in_transaction", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(update(1, "/learn check exit status"))
        self.assertEqual(self.app.store.stats()["events"], 0)
        self.assertEqual(self.app.store.stats()["memories"], 0)
        self.assertEqual(self.delivery_rows(), [])
        await self.app.ingest(update(1, "/learn check exit status"))
        memory = self.app.store.list_memories("accepted")[0]
        self.assertEqual((memory["kind"], memory["level"], memory["actor"]), ("lesson", 2, "owner"))
        self.assertEqual(len(memory["source_snapshots"]), 1)

    async def test_owner_command_respects_event_id_high_watermark(self):
        self.owner()
        self.app.store.set_meta("_event_high_watermark", 500)
        await self.app.ingest(update(1, "/remember retained provenance"))
        memory = self.app.store.list_memories("accepted")[0]
        self.assertEqual(memory["sources"], [501])
        self.assertGreater(self.app.store.event("tool", "later event"), 501)

    async def test_only_owner_can_accept_a_candidate(self):
        self.owner()
        source = self.app.store.event("tool", "a result")
        identifier = self.app.store.remember("Candidate hypothesis", sources=[source])
        await self.app.ingest(update(1, f"/accept {identifier}", user=99))
        self.assertEqual(self.app.store.list_memories("accepted"), [])
        await self.app.ingest(update(2, f"/accept {identifier}"))
        self.assertEqual(self.app.store.list_memories("accepted")[0]["id"], identifier)
        self.assertEqual(len(self.delivery_rows()), 1)

    async def test_stop_and_resume_persist_across_restart(self):
        self.owner()
        await self.app.ingest(update(1, "/task first task"))
        await self.app.ingest(update(2, "second task"))
        job = self.app.queue.claim()
        self.app.queue.checkpoint(job["id"], [{"kind": "note", "content": "saved progress"}])
        await self.app.ingest(update(3, "/stop"))
        self.assertTrue(all(x["state"] == "cancelled" for x in self.app.queue.list()))
        self.restart()
        await self.app.ingest(update(4, "/resume " + job["id"]))
        restored = self.app.queue.get(job["id"])
        self.assertEqual(restored["state"], "queued")
        self.assertEqual(restored["trace"], [{"kind": "note", "content": "saved progress"}])
        await self.app.ingest(update(4, "/resume " + job["id"]))
        self.assertEqual(len([x for x in self.delivery_rows() if x["source"] == "command:4"]), 1)

    async def test_worker_completion_is_atomically_wired_to_final_outbox(self):
        self.owner()
        await self.app.ingest(update(1, "Ответь на вопрос"))
        self.provider.on_call = self.app.stopping.set
        await self.app.worker()
        job = self.app.queue.get(self.app.queue.list()[0]["id"])
        self.assertEqual(job["state"], "completed")
        deliveries = self.delivery_rows()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["text"], "Проверенный ответ")
        self.restart()
        self.client.on_send = self.app.stopping.set
        await self.app.delivery()
        self.assertEqual(self.client.sent, [(17, "Проверенный ответ")])
        self.assertEqual(self.delivery_rows()[0]["state"], "sent")

    async def test_evolve_creates_one_owned_reviewable_job_after_restart(self):
        self.owner()
        await self.app.ingest(update(1, "/evolve foreign request", user=99))
        self.assertEqual(self.app.queue.list(), [])
        message = update(2, "/evolve improve workspace file search")
        with patch.object(self.app.queue, "advance", side_effect=RuntimeError("before cursor commit")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(message)
        self.restart()
        await self.app.ingest(message)
        jobs = self.app.queue.list()
        self.assertEqual(len(jobs), 1)
        job = self.app.queue.get(jobs[0]["id"])
        self.assertEqual((job["kind"], job["chat_id"], job["prompt"]),
                         ("self_improve", 17, "improve workspace file search"))
        self.assertEqual(len(self.delivery_rows()), 1)
        self.assertIn("патч", self.delivery_rows()[0]["text"])
        self.assertIn("отдельного решения", self.delivery_rows()[0]["text"])
        self.assertEqual(self.provider.calls, [])

    async def test_evolve_requires_specific_nonempty_improvement(self):
        self.owner()
        await self.app.ingest(update(1, "/evolve   "))
        self.assertEqual(self.app.queue.list(), [])
        self.assertIn("Не удалось", self.delivery_rows()[0]["text"])

    async def test_stop_interrupts_active_provider_and_keeps_cancelled_job(self):
        self.owner()
        started = asyncio.Event()

        async def wait_for_cancellation(prompt, schema):
            started.set()
            await asyncio.Event().wait()

        self.provider.complete = wait_for_cancellation
        await self.app.ingest(update(1, "long running task"))
        worker = asyncio.create_task(self.app.worker())
        try:
            await asyncio.wait_for(started.wait(), 3)
            identifier = self.app.current_id
            await self.app.ingest(update(2, "/stop"))
            self.app.stopping.set()
            await asyncio.wait_for(worker, 3)
            self.assertEqual(self.app.queue.get(identifier)["state"], "cancelled")
            self.assertTrue(any(row["role"] == "system" for row in self.app.store.history("work:" + identifier)))
            self.assertFalse(any(row["source"].startswith("job:") for row in self.delivery_rows()))
        finally:
            if not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

    async def test_ambiguous_delivery_is_persistent_and_not_retried(self):
        self.owner()
        self.app.queue.deliver("test-delivery", 17, "response")
        self.client.error = TelegramError("Network timeout", uncertain=True)
        self.client.on_send = self.app.stopping.set
        await self.app.delivery()
        self.assertEqual(self.delivery_rows()[0]["state"], "uncertain")
        self.restart()
        self.app.queue.recover()
        self.assertIsNone(self.app.queue.next_delivery())
        self.assertEqual(len(self.client.sent), 1)

    async def test_owner_backlog_is_bounded_and_commands_still_work(self):
        self.owner()
        for identifier in range(100):
            self.app.queue.enqueue(f"task {identifier}", 17, source=f"seed:{identifier}")
        await self.app.ingest(update(101, "one more task"))
        with self.app.queue.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 100)
        self.assertIn("100", self.delivery_rows()[-1]["text"])
        await self.app.ingest(update(102, "/stop"))
        self.assertTrue(all(x["state"] == "cancelled" for x in self.app.queue.list()))
        await self.app.ingest(update(103, "a new task"))
        self.assertEqual(self.app.queue.list()[0]["state"], "queued")

    async def test_malformed_updates_do_not_advance_the_cursor(self):
        for message in [None, [], {"update_id": True}, {"update_id": -1}, {"update_id": "10"}]:
            await self.app.ingest(message)
        self.assertEqual(self.app.queue.offset(), 0)
        self.assertEqual(self.provider.calls, [])


if __name__ == "__main__":
    unittest.main()
