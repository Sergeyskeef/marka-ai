"""Owner image previews keep original bytes, bounded decoding and durable receipts."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

from image_fixtures import png, chunk
from marka.app import Application
from marka.bridge import Bridge
from marka.bridge_client import BridgeTelegramClient, BridgeError, pack_bytes
from marka.config import Settings
from marka.health import delivery_effect
from marka.media import MAX_IMAGE_BYTES, validate_image
from marka.queue import Queue
from marka.telegram import TelegramClient, TelegramError, TelegramRetryAfter, validate_photo
import test_bridge
import test_telegram


class PhotoTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_photo_uses_validated_png_multipart_without_rewriting_original(self):
        fake = test_telegram.FakeHTTP(test_telegram.response({"message_id": 9}))
        client = TelegramClient(test_telegram.TOKEN, transport=fake)
        original = png()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "01.png"
            path.write_bytes(original)
            self.assertEqual(await client.send_photo(17, path, "Card 1"), 9)
            request = fake.requests[0][0]
            self.assertTrue(request.full_url.endswith("/sendPhoto"))
            self.assertIn(b'name="photo"; filename="01.png"', request.data)
            self.assertIn(b"Content-Type: image/png", request.data)
            self.assertIn(original, request.data)
            self.assertEqual(path.read_bytes(), original)

    async def test_invalid_photo_never_reaches_network_and_ambiguous_receipt_is_uncertain(self):
        fake = test_telegram.FakeHTTP(test_telegram.response({}))
        client = TelegramClient(test_telegram.TOKEN, transport=fake)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "01.png"
            for data in (png()[:-3], png(width=21, height=1), b"not an image"):
                path.write_bytes(data)
                with self.assertRaises(TelegramError) as caught:
                    await client.send_photo(17, path)
                self.assertTrue(caught.exception.permanent)
            self.assertFalse(fake.requests)
            path.write_bytes(png())
            with self.assertRaises(TelegramError) as caught:
                await client.send_photo(17, path)
            self.assertTrue(caught.exception.uncertain)
            self.assertEqual(len(fake.requests), 1)

    async def test_direct_transport_uses_supplied_snapshot_without_reopening_file(self):
        fake = test_telegram.FakeHTTP(test_telegram.response({"message_id": 10}), test_telegram.response({"message_id": 11}))
        client = TelegramClient(test_telegram.TOKEN, transport=fake)
        self.assertEqual(await client.send_photo(17, "missing.png", content=png()), 10)
        self.assertEqual(await client.send_document(17, "missing.png", content=png()), 11)
        self.assertTrue(all(png() in request[0].data for request in fake.requests))

    def test_outbound_size_does_not_expand_model_image_input_budget(self):
        original = png()
        # Valid ancillary metadata creates a large image without large pixels.
        data = original[:-12] + chunk(b"tEXt", b"Comment\0" + b"a" * MAX_IMAGE_BYTES) + original[-12:]
        self.assertGreater(len(data), MAX_IMAGE_BYTES)
        self.assertEqual(validate_photo(data).data, data)
        with self.assertRaises(ValueError):
            validate_image(data)


class PhotoBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = test_bridge.configuration(self.temporary.name)
        self.telegram = test_bridge.FakeTelegram()
        self.telegram.send_photo = AsyncMock(return_value=71)
        self.bridge = Bridge(self.config, telegram=self.telegram, provider=test_bridge.FakeProvider())
        self.request = {"op": "telegram.send_photo", "chat_id": test_bridge.OWNER, "caption": "Card 1",
                        "filename": "01.png", "data": pack_bytes(png()), "effect_id": "photo:1", "attempt": "0"}

    async def test_only_owner_validated_bytes_and_durable_replay_after_bridge_restart(self):
        for changes in ({"chat_id": 999}, {"path": "/secret.png"}, {"data": pack_bytes(b"corrupt")}):
            result = await self.bridge.dispatch(self.request | changes)
            self.assertFalse(result["ok"])
        self.telegram.send_photo.assert_not_awaited()
        first = await self.bridge.dispatch(self.request)
        self.assertTrue(first["ok"])
        restarted = Bridge(self.config, telegram=self.telegram, provider=test_bridge.FakeProvider())
        self.assertEqual(await restarted.dispatch(self.request), first)
        self.telegram.send_photo.assert_awaited_once()
        changed = await restarted.dispatch(self.request | {"caption": "Changed"})
        self.assertFalse(changed["ok"])

    async def test_uncertain_send_and_cancellation_never_blindly_replay(self):
        for error, suffix in ((TelegramError("timed out", uncertain=True), "timeout"),
                              (asyncio.CancelledError(), "cancel")):
            request = self.request | {"effect_id": "photo:" + suffix}
            self.telegram.send_photo.side_effect = error
            if isinstance(error, asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await self.bridge.dispatch(request)
            else:
                self.assertFalse((await self.bridge.dispatch(request))["ok"])
            before = self.telegram.send_photo.await_count
            replay = await self.bridge.dispatch(request)
            self.assertTrue(replay["error"]["uncertain"])
            self.assertEqual(self.telegram.send_photo.await_count, before)

    async def test_definite_rate_limit_retries_once_then_keeps_receipt(self):
        self.telegram.send_photo.side_effect = TelegramRetryAfter(1)
        self.assertFalse((await self.bridge.dispatch(self.request))["ok"])
        with self.bridge.journal.connect() as db:
            db.execute("UPDATE effects SET updated=updated-2 WHERE effect_id='photo:1'")
        self.telegram.send_photo.side_effect = None
        self.assertTrue((await self.bridge.dispatch(self.request))["ok"])
        self.assertTrue((await self.bridge.dispatch(self.request))["ok"])
        self.assertEqual(self.telegram.send_photo.await_count, 2)

    async def test_bridge_client_uses_content_snapshot_and_marks_connection_loss_uncertain(self):
        client = BridgeTelegramClient("/unused")
        with patch("marka.bridge_client._rpc", new_callable=AsyncMock, return_value=7) as rpc:
            self.assertEqual(await client.send_photo(test_bridge.OWNER, "missing.png", content=png(), effect_id="photo:1"), 7)
            request = rpc.await_args.args[1]
            self.assertEqual(request["op"], "telegram.send_photo")
            self.assertEqual(request["data"], pack_bytes(png()))
            self.assertNotIn("path", request)
        with patch("marka.bridge_client._rpc", new_callable=AsyncMock, side_effect=BridgeError()):
            with self.assertRaises(TelegramError) as caught:
                await client.send_photo(test_bridge.OWNER, "missing.png", content=png())
            self.assertTrue(caught.exception.uncertain)


class ArtifactDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name) / "state", bridge_socket="/unused")
        self.settings.prepare()
        self.client = types.SimpleNamespace(send_photo=AsyncMock(), send_document=AsyncMock(), send_message=AsyncMock())
        self.app = Application(self.settings, provider=test_bridge.FakeProvider(), client=self.client)
        self.app.store.set_meta("owner_id", 17)
        self.identifier = self.app.queue.enqueue("Show my cards", 17)
        self.job = self.app.queue.claim()
        self.original = png()
        self.path = self.app.engine.tools.workspace.path("01.png")
        self.path.write_bytes(self.original)

    async def send(self, mode="auto", *, step=1):
        return await self.app.engine.tools.call("workspace.send", {"path": "01.png", "mode": mode, "chat_id": 999}, self.job, [], step)

    async def run_delivery(self):
        original = self.app.queue.delivery_result
        def finished(*args, **kwargs):
            original(*args, **kwargs)
            self.app.stopping.set()
        with patch.object(self.app.queue, "delivery_result", side_effect=finished):
            await self.app.delivery()

    async def test_auto_preview_and_explicit_original_both_target_owner_and_keep_bytes(self):
        self.assertEqual((await self.send())["mode"], "photo")
        await self.run_delivery()
        self.client.send_photo.assert_awaited_once()
        self.assertEqual(self.client.send_photo.await_args.args[0], 17)
        self.assertEqual(self.client.send_photo.await_args.kwargs["content"], self.original)
        self.app.stopping.clear()
        self.assertTrue((await self.send("document", step=2))["original_bytes"])
        await self.run_delivery()
        self.assertEqual(self.client.send_document.await_args.kwargs["content"], self.original)
        self.assertNotEqual(self.client.send_photo.await_args.kwargs["effect_id"],
                            self.client.send_document.await_args.kwargs["effect_id"])

    async def test_unsupported_preview_falls_back_to_original_and_explicit_photo_is_actionable(self):
        self.path.write_bytes(png(width=21, height=1))
        result = await self.send()
        self.assertEqual(result["mode"], "document")
        with self.assertRaisesRegex(ValueError, "mode=document"):
            await self.send("photo", step=2)

    async def test_modified_queued_original_is_never_sent(self):
        await self.send()
        self.path.write_bytes(png(colour=(0, 20, 30)))
        await self.run_delivery()
        self.client.send_photo.assert_not_awaited()
        self.assertEqual(self.app.queue.delivery_issues()[0]["state"], "failed")

    async def test_cancel_prevents_pending_and_late_artifact_delivery(self):
        await self.send()
        self.app.queue.cancel(self.identifier)
        self.assertIsNone(self.app.queue.next_delivery())
        with self.assertRaisesRegex(ValueError, "cancelled"):
            await self.send(step=2)
        self.assertIsNone(self.app.queue.next_delivery())

    async def test_photo_uncertainty_persists_across_queue_recovery(self):
        await self.send()
        self.client.send_photo.side_effect = TelegramError("timeout", uncertain=True)
        await self.run_delivery()
        restarted = Queue(self.settings.database)
        restarted.recover()
        self.assertIsNone(restarted.next_delivery())
        self.assertEqual(restarted.delivery_issues()[0]["state"], "uncertain")

    async def test_cancel_during_definite_rate_limit_does_not_resurrect_photo(self):
        await self.send()
        async def cancelled_request(*args, **kwargs):
            self.app.queue.cancel(self.identifier)
            raise TelegramRetryAfter(1)
        self.client.send_photo.side_effect = cancelled_request
        await self.run_delivery()
        self.assertEqual(self.app.queue.delivery_issues()[0]["state"], "failed")
        self.assertIn("cancelled", self.app.queue.delivery_issues()[0]["error"])
        self.assertIsNone(self.app.queue.next_delivery())
        self.client.send_photo.assert_awaited_once()

    async def test_claim_rejects_stale_pending_cancelled_artifact_but_keeps_service_reply(self):
        await self.send()
        delivery = self.app.queue.next_delivery()
        self.app.queue.cancel(self.identifier)
        # Simulate a pending row written by an older runtime after cancellation.
        with self.app.queue.connection() as db:
            db.execute("UPDATE deliveries SET state='pending',due=0 WHERE id=?", (delivery["id"],))
        self.app.queue.deliver("command:cancel-confirmation", 17, "Cancelled")
        claimed = self.app.queue.next_delivery()
        self.assertEqual(claimed["source"], "command:cancel-confirmation")
        self.assertEqual(self.app.queue.delivery_issues()[0]["state"], "failed")
        self.app.queue.delivery_result(claimed["id"], "pending", delay=0)
        self.assertEqual(self.app.queue.next_delivery()["id"], claimed["id"])

    async def test_cancel_keeps_inflight_uncertainty_and_success_receipt(self):
        for state in ("uncertain", "sent"):
            with self.subTest(result=state):
                identifier = self.app.queue.enqueue("New owner artifact", 17)
                self.app.queue.deliver(f"artifact:{identifier}:1", 17, "", "01.png", media_kind="photo", job_id=identifier)
                delivery = self.app.queue.next_delivery()
                self.app.queue.cancel(identifier)
                self.app.queue.delivery_result(delivery["id"], state)
                with self.app.queue.connection() as db:
                    self.assertEqual(db.execute("SELECT state FROM deliveries WHERE id=?", (delivery["id"],)).fetchone()[0], state)
                self.assertIsNone(self.app.queue.next_delivery())


class DeliveryMigrationTests(unittest.TestCase):
    def test_existing_documents_migrate_without_changing_payload_or_effect_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.db"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE deliveries(id INTEGER PRIMARY KEY,source TEXT UNIQUE NOT NULL,chat_id INTEGER NOT NULL,"
                           "text TEXT NOT NULL,document TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'pending',"
                           "due REAL NOT NULL,error TEXT NOT NULL DEFAULT '')")
                db.execute("INSERT INTO deliveries(source,chat_id,text,document,due) VALUES('old',17,'original','report.pdf',0)")
            row = Queue(path).next_delivery()
            self.assertEqual((row["media_kind"], row["document_sha256"], row["document"]), ("document", "", "report.pdf"))
            legacy = {key: value for key, value in row.items() if key not in {"media_kind", "document_sha256"}}
            self.assertEqual(delivery_effect(row, document=b"original"), delivery_effect(legacy, document=b"original"))
            self.assertNotEqual(delivery_effect(row, document=b"original"), delivery_effect(row | {"media_kind": "photo"}, document=b"original"))
