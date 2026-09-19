"""Ephemeral typing has no delivery receipt, credentials or model tool surface."""
import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from marka.app import Application
from marka.bridge import Bridge
from marka.bridge_client import BridgeError, BridgeTelegramClient
from marka.config import Settings
from marka.telegram import HTTPResponse, TelegramClient, TelegramError, TelegramRetryAfter


OWNER = 17
TOKEN = "123456:synthetic-test-token-not-real-123456"


class TypingTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_action_short_timeout_and_small_response(self):
        calls = []

        def transport(request, timeout):
            calls.append((request, timeout))
            return HTTPResponse(200, b'{"ok":true,"result":true}')

        client = TelegramClient(TOKEN, transport=transport)
        self.assertIs(await client.send_typing(OWNER), True)
        request, timeout = calls[0]
        self.assertTrue(request.full_url.endswith("/sendChatAction"))
        self.assertEqual(json.loads(request.data), {"chat_id": OWNER, "action": "typing"})
        self.assertLessEqual(timeout, 3)
        self.assertEqual(request._marka_response_limit, 4096)

    async def test_invalid_private_chat_never_reaches_transport(self):
        transport = AsyncMock()
        client = TelegramClient(TOKEN, transport=transport)
        for value in (True, False, -17, 0, "17", 2**63):
            with self.subTest(value=value), self.assertRaises(TelegramError):
                await client.send_typing(value)
        transport.assert_not_called()

    async def test_receipt_must_be_literal_true(self):
        for value in (False, 1, None, {"message_id": 1}):
            with self.subTest(value=value):
                client = TelegramClient(TOKEN, transport=lambda *_: HTTPResponse(
                    200, json.dumps({"ok": True, "result": value}).encode()))
                with self.assertRaises(TelegramError) as raised:
                    await client.send_typing(OWNER)
                self.assertFalse(raised.exception.uncertain)

    async def test_network_error_has_no_secret_or_delivery_uncertainty(self):
        def broken(*_):
            raise OSError("https://example.invalid/bot" + TOKEN)

        with self.assertRaises(TelegramError) as raised:
            await TelegramClient(TOKEN, transport=broken).send_typing(OWNER)
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertFalse(raised.exception.uncertain)
        self.assertEqual(raised.exception.sent_message_ids, [])

    async def test_rate_limit_remains_retry_after(self):
        client = TelegramClient(TOKEN, transport=lambda *_: HTTPResponse(429,
            b'{"ok":false,"error_code":429,"parameters":{"retry_after":30}}'))
        with self.assertRaises(TelegramRetryAfter) as raised:
            await client.send_typing(OWNER)
        self.assertEqual(raised.exception.seconds, 30)
        self.assertFalse(raised.exception.uncertain)

    async def test_timeout_and_cancellation_stop_awaiting_request(self):
        client = TelegramClient(TOKEN)
        entered, cancelled = asyncio.Event(), asyncio.Event()

        async def hung(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with patch.object(client, "_request", hung), patch("marka.telegram.TYPING_TIMEOUT", 0.01):
            with self.assertRaises(TelegramError) as raised:
                await client.send_typing(OWNER)
            self.assertFalse(raised.exception.uncertain)
            self.assertTrue(cancelled.is_set())
        cancelled.clear()
        entered.clear()
        with patch.object(client, "_request", hung):
            task = asyncio.create_task(client.send_typing(OWNER))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(cancelled.is_set())


class TypingBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.telegram = type("FakeTelegram", (), {"send_typing": AsyncMock(return_value=True)})()
        self.bridge = Bridge({"socket": str(root / "bridge.sock"), "journal": str(root / "journal.db"),
            "owner_id": OWNER, "token_file": str(root / "unused-token"), "codex_home": str(root / "unused-home"),
            "voice_key_file": str(root / "unused-key"), "model": "test-model", "daily_calls": 1,
            "provider_timeout": 60, "initial_offset": 0}, telegram=self.telegram, provider=object())

    async def request(self, **fields):
        return await self.bridge.dispatch({"op": "telegram.typing", "chat_id": OWNER, **fields})

    async def test_owner_pulse_is_ephemeral_and_independent_of_model_budget(self):
        self.assertEqual(await self.request(), {"ok": True, "result": True})
        self.telegram.send_typing.assert_awaited_once_with(OWNER)
        with self.bridge.journal.connect() as db:
            for table in ("effects", "updates", "read_audit"):
                self.assertEqual(db.execute("SELECT count(*) FROM " + table).fetchone()[0], 0)

    async def test_rejects_foreign_chat_types_and_extra_payload_fields(self):
        for value in (18, -17, "17", True, None):
            with self.subTest(value=value):
                self.assertFalse((await self.request(chat_id=value))["ok"])
        for field in ({"action": "upload_document"}, {"effect_id": "x"}, {"attempt": "0"}, {"path": "/secret"}):
            self.assertFalse((await self.request(**field))["ok"])
        self.telegram.send_typing.assert_not_awaited()

    async def test_bridge_enforces_cadence_before_await_even_for_parallel_requests(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def waiting(chat):
            entered.set()
            await release.wait()
            return True

        self.telegram.send_typing.side_effect = waiting
        first = asyncio.create_task(self.request())
        await entered.wait()
        try:
            second = await self.request()
            self.assertFalse(second["ok"])
            self.assertGreaterEqual(second["error"]["retry_after"], 1)
            self.telegram.send_typing.assert_awaited_once()
        finally:
            release.set()
            await first
        self.bridge._typing_next = time.monotonic() - 1
        self.assertTrue((await self.request())["ok"])
        self.assertEqual(self.telegram.send_typing.await_count, 2)

    async def test_remote_rate_limit_cooldown_is_not_bypassed(self):
        self.telegram.send_typing.side_effect = TelegramRetryAfter(30)
        before = time.monotonic()
        result = await self.request()
        self.assertEqual(result["error"]["retry_after"], 30)
        self.assertGreaterEqual(self.bridge._typing_next, before + 30)
        self.assertFalse((await self.request())["ok"])
        self.telegram.send_typing.assert_awaited_once()

    async def test_failed_request_still_consumes_cooldown_without_effect_receipt(self):
        self.telegram.send_typing.side_effect = TelegramError("unavailable")
        self.assertFalse((await self.request())["ok"])
        self.assertIn("retry_after", (await self.request())["error"])
        self.telegram.send_typing.assert_awaited_once()
        with self.bridge.journal.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM effects").fetchone()[0], 0)

    async def test_bridge_timeout_cancels_operation_without_uncertain_receipt(self):
        cancelled = asyncio.Event()

        async def hanging(chat):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.telegram.send_typing.side_effect = hanging
        with patch("marka.bridge.TYPING_TIMEOUT", 0.001):
            result = await self.request()
        self.assertFalse(result["ok"])
        self.assertFalse(result["error"].get("uncertain"))
        self.assertTrue(cancelled.is_set())

    async def test_client_wire_has_only_owner_chat_and_short_deadline(self):
        rpc = AsyncMock(return_value=True)
        with patch("marka.bridge_client._rpc", rpc):
            self.assertIs(await BridgeTelegramClient("unused.sock").send_typing(OWNER), True)
        rpc.assert_awaited_once_with("unused.sock", {"op": "telegram.typing", "chat_id": OWNER}, timeout=4)

    async def test_client_failure_is_not_uncertain_delivery_and_generic_api_stays_closed(self):
        client = BridgeTelegramClient("unused.sock")
        with patch("marka.bridge_client._rpc", AsyncMock(side_effect=BridgeError("secret"))):
            with self.assertRaises(TelegramError) as raised:
                await client.send_typing(OWNER)
        self.assertFalse(raised.exception.uncertain)
        self.assertNotIn("secret", str(raised.exception))
        with self.assertRaises(TelegramError):
            await client.call("sendChatAction", {"chat_id": OWNER, "action": "typing"})
        with patch("marka.bridge_client._rpc", AsyncMock(return_value=1)):
            with self.assertRaises(TelegramError):
                await client.send_typing(OWNER)


class TypingWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = Settings(Path(temporary.name) / "state")
        settings.prepare()
        self.client = type("FakeTelegram", (), {"send_typing": AsyncMock(return_value=True)})()
        self.app = Application(settings, provider=object(), client=self.client)
        self.app.store.set_meta("owner_id", OWNER)
        self.entered, self.release, self.pulsed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def start_worker(self, *, chat=OWNER, result_state="completed"):
        self.job_id = self.app.queue.enqueue("synthetic work", chat)

        async def job_work(job):
            self.entered.set()
            await self.release.wait()
            self.app.queue.finish(job["id"], result_state, result="synthetic done", lease=job["lease"])
            self.app.stopping.set()

        self.app.run_job = job_work
        worker = asyncio.create_task(self.app.worker())
        self.addAsyncCleanup(self.stop_worker, worker)
        await asyncio.wait_for(self.entered.wait(), 2)
        return worker

    async def stop_worker(self, worker):
        self.app.stopping.set()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    async def test_pulses_during_work_then_stops_without_extra_delivery_rows(self):
        times = []

        async def pulse(chat):
            self.assertEqual(chat, OWNER)
            times.append(time.monotonic())
            if len(times) >= 3:
                self.pulsed.set()
            return True

        self.client.send_typing.side_effect = pulse
        with patch("marka.app.TYPING_INTERVAL", 0.02):
            worker = await self.start_worker()
            await asyncio.wait_for(self.pulsed.wait(), 2)
            self.release.set()
            await asyncio.wait_for(worker, 2)
            count = len(times)
            await asyncio.sleep(0.06)
            self.assertEqual(len(times), count)
        self.assertTrue(all(right - left >= 0.018 for left, right in zip(times, times[1:])))
        self.assertEqual(self.app.queue.get(self.job_id)["state"], "completed")
        with self.app.queue.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM deliveries").fetchone()[0], 1)

    async def test_foreign_or_unpaired_job_gets_no_typing(self):
        for owner, chat in ((OWNER, 18), (None, OWNER), (True, 1)):
            self.app.store.set_meta("owner_id", owner)
            operation = asyncio.create_task(asyncio.Event().wait())
            try:
                await self.app.typing({"chat_id": chat}, operation)
            finally:
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
        self.client.send_typing.assert_not_awaited()

    async def test_transient_failures_are_bounded_and_do_not_block_job(self):
        self.client.send_typing.side_effect = TelegramError("network unavailable")
        with patch("marka.app.TYPING_INTERVAL", 0.01):
            worker = await self.start_worker()
            await asyncio.sleep(0.08)
            self.assertEqual(self.client.send_typing.await_count, 3)
            self.assertFalse(worker.done())
            self.release.set()
            await asyncio.wait_for(worker, 2)
        self.assertEqual(self.app.queue.get(self.job_id)["state"], "completed")

    async def test_permanent_failure_or_unexpected_transport_error_stops_only_typing(self):
        self.client.send_typing.side_effect = TelegramError("forbidden", permanent=True)
        with patch("marka.app.TYPING_INTERVAL", 0.01):
            worker = await self.start_worker()
            await asyncio.sleep(0.06)
            self.assertEqual(self.client.send_typing.await_count, 1)
            self.release.set()
            await asyncio.wait_for(worker, 2)
        self.assertEqual(self.app.queue.get(self.job_id)["state"], "completed")

    async def test_retry_after_wait_does_not_delay_job_completion(self):
        self.client.send_typing.side_effect = TelegramRetryAfter(30)
        worker = await self.start_worker()
        await asyncio.sleep(0.02)
        self.release.set()
        await asyncio.wait_for(worker, 0.5)
        self.client.send_typing.assert_awaited_once()

    async def test_job_cancellation_cleans_up_inflight_typing(self):
        cancelled = asyncio.Event()

        async def hung(chat):
            self.pulsed.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.client.send_typing.side_effect = hung
        worker = await self.start_worker()
        await asyncio.wait_for(self.pulsed.wait(), 2)
        self.app.current.cancel()
        await asyncio.wait_for(cancelled.wait(), 0.5)
        self.assertFalse(worker.done())
        self.assertEqual(self.client.send_typing.await_count, 1)

    async def test_shutdown_cleans_up_typing_and_current_operation(self):
        async def pulse(chat):
            self.pulsed.set()
            return True

        self.client.send_typing.side_effect = pulse
        worker = await self.start_worker()
        await asyncio.wait_for(self.pulsed.wait(), 2)
        current = self.app.current
        await self.stop_worker(worker)
        self.assertTrue(current.done())
        self.assertIsNone(self.app.current)
        count = self.client.send_typing.await_count
        await asyncio.sleep(0.02)
        self.assertEqual(self.client.send_typing.await_count, count)

    async def test_job_exception_also_stops_typing(self):
        entered = asyncio.Event()

        async def pulse(chat):
            entered.set()
            return True

        async def broken(job):
            await entered.wait()
            raise RuntimeError("synthetic job failure")

        self.client.send_typing.side_effect = pulse
        self.app.queue.enqueue("synthetic failure", OWNER)
        self.app.run_job = broken
        with self.assertRaisesRegex(RuntimeError, "synthetic job failure"):
            await asyncio.wait_for(self.app.worker(), 2)
        self.assertIsNone(self.app.current)
        count = self.client.send_typing.await_count
        await asyncio.sleep(0.02)
        self.assertEqual(self.client.send_typing.await_count, count)
