import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from marka.app import Application
from marka.config import Settings
from marka.telegram import parse_voice, TelegramClient, TelegramError
from marka.voice import VoiceError
from test_app_learning import FakeClient, FakeProvider, message
from test_telegram import FakeHTTP, HTTPResponse, TOKEN, response
from voice_fixtures import OGG, transcript, voice_update


class VoiceProvider(FakeProvider):
    def __init__(self):
        self.prompts = []

    async def complete(self, prompt, schema):
        self.prompts.append(prompt)
        return await super().complete(prompt, schema)


class VoiceGatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.settings = Settings(Path(temp.name), semantic_search=False)
        self.settings.prepare()
        self.settings.voice_key_file.write_text("synthetic-test-key-not-used")
        self.client, self.provider = FakeClient(), VoiceProvider()
        self.client.data = OGG
        self.restart()
        self.app.store.set_meta("owner_id", 17)

    def restart(self):
        self.app = Application(self.settings, provider=self.provider, client=self.client)

    def deliveries(self):
        with self.app.queue.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM deliveries")]

    async def test_foreign_unpaired_forwarded_edited_group_and_bot_do_not_download(self):
        await self.app.ingest(voice_update(1, user=99))
        for i, change in enumerate(({"forward_origin": {}}, {"via_bot": {}}, {"chat": {"id": 17, "type": "group"}},
                                    {"from": {"id": 17, "is_bot": True}}, {"chat": {"id": 18, "type": "private"}}), 2):
            item = voice_update(i)
            item["message"].update(change)
            await self.app.ingest(item)
        await self.app.ingest(voice_update(8) | {"edited_message": {}})
        self.app.store.set_meta("owner_id", None)
        await self.app.ingest(voice_update(9))
        self.assertEqual(self.client.downloads, [])
        self.assertEqual(self.app.queue.list(), [])

    async def test_off_and_metadata_limits_fail_before_download_with_useful_reply(self):
        self.settings.voice_key_file.unlink()
        await self.app.ingest(voice_update(1))
        self.assertIn("не настроено", self.deliveries()[0]["text"])
        self.settings.voice_key_file.write_text("synthetic-test-key-not-used")
        await self.app.ingest(voice_update(2, duration=61))
        item = voice_update(3)
        item["message"]["voice"]["file_size"] = 2097153
        await self.app.ingest(item)
        self.assertEqual(self.client.downloads, [])
        self.assertEqual(self.app.queue.list(), [])

    async def test_intake_deduplicates_after_crash_before_enqueue_and_reply(self):
        item = voice_update(1, caption="original caption")
        with patch.object(self.app, "_enqueue_owner", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(item)
        self.restart()
        item["message"]["caption"] = "changed replay"
        with patch.object(self.app, "reply", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                await self.app.ingest(item)
        self.restart()
        await self.app.ingest(item)
        await self.app.ingest(item)
        self.assertEqual(len(self.client.downloads), 1)
        self.assertEqual(len(self.app.queue.list()), 1)
        self.assertEqual(self.app.voices.get("telegram:1", 17)["caption"], "original caption")

    async def test_transcript_becomes_unverified_task_with_source_not_memory_or_command(self):
        await self.app.ingest(voice_update())
        job = self.app.queue.claim()
        with patch("marka.app.transcribe", return_value=transcript(text="/remember secret instruction")) as stt:
            await self.app.run_job(job)
        stt.assert_awaited_once()
        final = self.app.queue.get(job["id"])
        self.assertEqual(final["state"], "completed")
        self.assertIn("НЕ дословная", final["prompt"])
        self.assertNotIn(str(self.settings.data_dir), final["prompt"])
        request = next(event for event in self.app.store.history() if event["role"] == "user")
        self.assertEqual(request["meta"]["trust"], "unverified_transcription")
        self.assertFalse(request["meta"]["exact_owner_quote"])
        self.assertEqual(self.app.store.get_event(request["id"])["trust"], "unverified_transcription")
        recalled = self.app.store.recall_events("secret instruction")
        self.assertTrue(any(row["id"] == request["id"] and row["trust"] == "unverified_transcription" for row in recalled))
        self.assertEqual(self.app.store.list_memories("accepted"), [])
        self.assertTrue(any(row["source"] == "job:" + job["id"] + ":final:1" for row in self.deliveries()))

    async def test_restart_after_transcript_commit_reuses_it_without_second_stt(self):
        await self.app.ingest(voice_update())
        job = self.app.queue.claim()
        with patch("marka.app.transcribe", return_value=transcript()), patch.object(self.app.engine, "run", side_effect=RuntimeError("power loss")):
            with self.assertRaises(RuntimeError):
                await self.app.run_job(job)
        self.restart()
        self.app.queue.recover()
        with patch("marka.app.transcribe", side_effect=AssertionError("must reuse saved transcript")):
            await self.app.run_job(self.app.queue.claim())
        self.assertEqual(self.app.queue.get(job["id"])["state"], "completed")

    async def test_restart_during_paid_request_blocks_instead_of_automatic_resubmit(self):
        await self.app.ingest(voice_update())
        job = self.app.queue.claim()
        with patch("marka.app.transcribe", side_effect=RuntimeError("power loss before response")):
            with self.assertRaises(RuntimeError):
                await self.app.run_job(job)
        self.restart()
        self.app.queue.recover()
        self.assertEqual(self.app.queue.get(job["id"])["state"], "blocked")
        self.assertIsNone(self.app.queue.claim())
        self.assertEqual(self.app.voices.for_job(job)["transcript"], {})

    async def test_exhausted_budget_and_resume_cannot_spend_stt_api(self):
        for number, change in ((1, "deadline=1"), (2, "steps_used=max_steps"), (3, "model_calls=max_model_calls")):
            await self.app.ingest(voice_update(number))
            job = self.app.queue.claim()
            with self.app.queue.connection() as db:
                db.execute("UPDATE jobs SET " + change + " WHERE id=?", (job["id"],))
            with patch("marka.app.transcribe", side_effect=AssertionError("no paid request")) as stt:
                await self.app.run_job(job)
                self.assertEqual(self.app.queue.get(job["id"])["state"], "blocked")
                self.assertIn("/extend", self.app.queue.get(job["id"])["error"])
                self.app.queue.resume(job["id"])
                await self.app.run_job(self.app.queue.claim())
                stt.assert_not_awaited()
            self.assertEqual(self.app.voices.for_job(job)["transcript"], {})

    async def test_stt_timeout_is_capped_by_remaining_job_time(self):
        await self.app.ingest(voice_update())
        job = self.app.queue.claim()
        with self.app.queue.connection() as db:
            db.execute("UPDATE jobs SET deadline=? WHERE id=?", (time.time() + 30, job["id"]))
        with patch("marka.app.transcribe", return_value=transcript()) as stt:
            await self.app.run_job(job)
        self.assertGreater(stt.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(stt.call_args.kwargs["timeout"], 30)

    async def test_deadline_expiring_during_checkpoint_does_not_send_audio(self):
        await self.app.ingest(voice_update())
        job = self.app.queue.claim()
        now = time.time()
        with self.app.queue.connection() as db:
            db.execute("UPDATE jobs SET deadline=? WHERE id=?", (now + 10, job["id"]))
        clock = MagicMock(wraps=time)
        clock.time.return_value = now
        checkpoint = self.app.queue.checkpoint
        def delayed(*args, **kwargs):
            result = checkpoint(*args, **kwargs)
            clock.time.return_value = now + 20
            return result
        with patch("marka.app.time", clock), patch.object(self.app.queue, "checkpoint", side_effect=delayed), \
                patch("marka.app.transcribe", side_effect=AssertionError("deadline elapsed")) as stt:
            await self.app.run_job(job)
        stt.assert_not_awaited()
        self.assertEqual(self.app.queue.get(job["id"])["state"], "blocked")
        self.assertFalse(self.app.queue.get(job["id"])["inflight"])

    async def test_empty_invalid_failed_and_missing_audio_block_without_model(self):
        for number, result in ((1, transcript(text="")), (2, transcript() | {"sha256": "wrong"}), (3, VoiceError("worker unavailable"))):
            await self.app.ingest(voice_update(number))
            job = self.app.queue.claim()
            kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
            with patch("marka.app.transcribe", **kwargs):
                await self.app.run_job(job)
            self.assertEqual(self.app.queue.get(job["id"])["state"], "blocked")
        await self.app.ingest(voice_update(4))
        path = next(self.app.voices.root.iterdir())
        path.chmod(0o600)
        path.unlink()
        with patch("marka.app.transcribe", side_effect=AssertionError("no changed source")):
            job = self.app.queue.claim()
            await self.app.run_job(job)
            self.assertEqual(self.app.queue.get(job["id"])["state"], "blocked")
        self.assertEqual(self.provider.prompts, [])

    async def test_polling_commands_remain_available_and_stop_cancels_stt(self):
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def slow(*args, **kwargs):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        await self.app.ingest(voice_update())
        with patch("marka.app.transcribe", side_effect=slow):
            worker = asyncio.create_task(self.app.worker())
            try:
                await asyncio.wait_for(started.wait(), 3)
                await self.app.ingest(message(2, "/status"))
                await self.app.ingest(message(3, "/stop"))
                await asyncio.wait_for(cancelled.wait(), 3)
            finally:
                self.app.stopping.set()
                self.app.wake_worker()
                await worker
        job = self.app.queue.list()[0]
        self.assertEqual(job["state"], "cancelled")
        self.assertEqual(self.app.voices.for_job(self.app.queue.get(job["id"]))["transcript"], {})
        self.assertEqual(self.provider.prompts, [])

    async def test_help_and_status_distinguish_disabled_from_unavailable_worker(self):
        self.settings.voice_key_file.unlink()
        await self.app.ingest(message(1, "/help"))
        self.assertIn("OpenAI API не настроен", self.deliveries()[-1]["text"])
        self.settings.voice_key_file.write_text("synthetic-test-key-not-used")
        await self.app.ingest(message(2, "/status"))
        self.assertIn("Аудио передаётся в OpenAI", self.deliveries()[-1]["text"])


class VoiceTransportTests(unittest.IsolatedAsyncioTestCase):
    def test_voice_metadata_is_original_private_and_valid(self):
        self.assertEqual(parse_voice(voice_update()).duration, 1)
        for duration in (True, -1, "5", None):
            item = voice_update(duration=duration)
            self.assertIsNone(parse_voice(item))

    async def test_voice_opt_in_download_is_bounded_and_cannot_combine_media_flags(self):
        data = b"x" * 524289
        fake = FakeHTTP(response({"file_id": "voice-id", "file_path": "voice/file.oga", "file_size": len(data)}), HTTPResponse(200, data))
        client = TelegramClient(TOKEN, transport=fake)
        for kwargs in ({}, {"voice": True, "image": True}, {"voice": "yes"}):
            with self.assertRaises(TelegramError):
                await client.download_file("voice-id", max_bytes=2097152, **kwargs)
        self.assertEqual(fake.requests, [])
        self.assertEqual(await client.download_file("voice-id", max_bytes=2097152, expected_size=len(data), voice=True), data)
