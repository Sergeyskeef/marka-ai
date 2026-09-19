"""Independent receipts must survive bot crashes, retries and malicious candidates."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from marka.bridge import Bridge, Journal, Rejected, _safe_error
from marka.bridge_client import (MAX_FRAME, BridgeError, BridgeProvider, BridgeTelegramClient,
                                 bridge_transcribe, canonical, pack_bytes, read_frame, write_frame)
from marka.provider import ProviderError
from marka.telegram import MAX_DOCUMENT_BYTES, TelegramError, TelegramRetryAfter
from marka.voice import VoiceError
from image_fixtures import png


OWNER = 123456
SECRET = "this-secret-must-not-escape"


def update(identifier, text="hello", *, owner=OWNER, extra=None):
    value = {"update_id": identifier, "message": {"message_id": identifier,
             "from": {"id": owner, "is_bot": False}, "chat": {"id": owner, "type": "private"}, "text": text}}
    value["message"].update(extra or {})
    return value


def configuration(directory):
    root = Path(directory).resolve()
    return {"socket": str(root / "bridge.sock"), "journal": str(root / "journal.sqlite3"),
            "owner_id": OWNER, "token_file": str(root / "token"), "codex_home": str(root / "codex"),
            "voice_key_file": str(root / "speech.key"), "model": "test-model", "daily_calls": 200,
            "provider_timeout": 180, "initial_offset": 0}


class FakeTelegram:
    def __init__(self):
        self.sent = []
        self.calls = []
        self.incoming = []
        self.files = {}
        self.error = None

    async def get_me(self):
        return {"id": 99, "is_bot": True, "username": "test_bot"}

    async def call(self, method, payload):
        self.calls.append((method, payload))
        return {"url": "https://example.invalid/" + SECRET, "pending_update_count": 0}

    async def get_updates(self, offset, timeout=25):
        self.calls.append(("get_updates", offset))
        return [row for row in self.incoming if row["update_id"] >= offset][:100]

    async def download_file(self, file_id, **kwargs):
        self.calls.append(("download", file_id))
        return self.files[file_id]

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        if self.error:
            raise self.error
        return [len(self.sent)]

    async def send_document(self, chat_id, path, caption=""):
        self.sent.append((chat_id, path.name, path.read_bytes(), caption))
        return len(self.sent)


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.error = None
        self.entered = asyncio.Event()
        self.wait = False
        self.cancelled = False

    async def status(self):
        return {"authenticated": True, "auth_method": "chatgpt", "version": "0.144.1", "secret": SECRET}

    async def complete(self, prompt, schema, *, images=()):
        self.calls.append((prompt, schema, images))
        self.entered.set()
        if self.wait:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self.error:
            raise self.error
        return {"answer": "done"}


def provider_request(effect="model:job:1", **overrides):
    return {"op": "provider.complete", "prompt": "Hello", "schema": {"type": "object"},
            "images": [], "effect_id": effect, "attempt": "0", **overrides}


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = configuration(self.temporary.name)
        self.telegram = FakeTelegram()
        self.provider = FakeProvider()
        self.bridge = Bridge(self.config, telegram=self.telegram, provider=self.provider)

    async def test_owner_journal_precedes_remote_ack_and_survives_restart(self):
        self.telegram.incoming = [update(10), update(11, owner=55), update(12, "/rescue@test_bot"), update(13, "/ROLLBACK")]
        await self.bridge.poll_once()
        self.assertEqual(self.telegram.calls, [("get_updates", 0)])
        self.assertEqual(self.bridge.journal.offset, 14)
        resumed = Journal(self.config["journal"], OWNER, initial_offset=999)
        self.assertEqual(resumed.offset, 14)
        self.assertEqual([row["update_id"] for row in resumed.updates(0)], [10])
        with resumed.connect() as db:
            self.assertEqual([(row[0], row[1]) for row in db.execute("SELECT update_id,control FROM updates ORDER BY update_id")],
                             [(10, ""), (12, "rescue"), (13, "rollback")])
        await self.bridge.poll_once()
        self.assertEqual(self.telegram.calls[-1], ("get_updates", 14))

    async def test_forwards_edited_group_and_bot_updates_never_authorize(self):
        values = [update(1, extra={"forward_origin": {}}), update(2, extra={"via_bot": {}}),
                  update(3, extra={"from": {"id": OWNER, "is_bot": True}}),
                  update(4, extra={"chat": {"id": OWNER, "type": "group"}})]
        edited = update(5)
        edited["edited_message"] = edited.pop("message")
        self.bridge.journal.ingest(values + [edited])
        self.assertEqual(self.bridge.journal.updates(0), [])
        self.assertEqual(self.bridge.journal.offset, 6)

    async def test_ingest_failure_does_not_advance_offset(self):
        self.bridge.journal.ingest([update(1)])
        with self.assertRaises(Rejected):
            self.bridge.journal.ingest([update(2), update(1, "changed")])
        self.assertEqual(self.bridge.journal.offset, 2)
        self.assertEqual(len(self.bridge.journal.updates(0)), 1)

    async def test_completed_effect_is_replayed_and_payload_change_rejected(self):
        request = provider_request()
        first = await self.bridge.dispatch(request)
        second = await self.bridge.dispatch(request)
        self.assertEqual(first, second)
        self.assertEqual(len(self.provider.calls), 1)
        restart = Bridge(self.config, telegram=self.telegram, provider=self.provider)
        self.assertEqual(await restart.dispatch(request), first)
        self.assertEqual(await restart.dispatch(provider_request(attempt="different-lease")), first)
        self.assertEqual(len(self.provider.calls), 1)
        changed = await restart.dispatch(provider_request(prompt="changed"))
        self.assertEqual(changed["error"]["kind"], "conflict")

    async def test_pending_restart_stays_uncertain_and_explicit_attempt_can_retry(self):
        self.provider.error = RuntimeError(SECRET)
        first = await self.bridge.dispatch(provider_request())
        self.assertEqual(first["error"]["kind"], "uncertain")
        self.assertNotIn(SECRET, json.dumps(first))
        self.provider.error = None
        resumed = Bridge(self.config, telegram=self.telegram, provider=self.provider)
        replay = await resumed.dispatch(provider_request())
        self.assertEqual(replay["error"]["kind"], "uncertain")
        self.assertEqual(len(self.provider.calls), 1)
        unknown = await resumed.dispatch(provider_request(attempt="new-lease"))
        self.assertEqual(unknown["error"]["kind"], "uncertain")
        unproven = await resumed.dispatch(provider_request(attempt="owner-342"))
        self.assertEqual(unproven["error"]["kind"], "uncertain")
        resumed.journal.ingest([update(342, "/resume@test_bot original-job")])
        result = await resumed.dispatch(provider_request(attempt="owner-342"))
        self.assertTrue(result["ok"])
        self.assertEqual(len(self.provider.calls), 2)

    async def test_inflight_restart_and_daily_budget(self):
        self.bridge.journal.begin("provider", "job:pending", "0", "hash", 200)
        resumed = Bridge(self.config, telegram=self.telegram, provider=self.provider)
        with resumed.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM effects").fetchone()[0], "pending")
        resumed.journal.recover_pending()
        with resumed.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM effects").fetchone()[0], "uncertain")
        resumed.daily_calls = 1
        result = await resumed.dispatch(provider_request())
        self.assertEqual(result["error"]["kind"], "budget")
        self.assertEqual(self.provider.calls, [])

    async def test_model_and_voice_daily_counters_are_separate(self):
        self.bridge.daily_calls = 1
        self.bridge.journal.begin("voice", "telegram:1", "0", "hash", 1)
        self.assertTrue((await self.bridge.dispatch(provider_request()))["ok"])
        second = await self.bridge.dispatch(provider_request(effect="model:job:2"))
        self.assertEqual(second["error"]["kind"], "budget")

    async def test_bridge_constructor_does_not_recover_live_pending_receipts(self):
        self.bridge.journal.begin("provider", "job:active", "0", "hash", 200)
        duplicate = Bridge(self.config, telegram=self.telegram, provider=self.provider)
        with duplicate.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM effects").fetchone()[0], "pending")

    async def test_zero_one_two_images_keep_exact_bytes_and_reject_three_or_paths(self):
        data = png()
        for count in range(3):
            response = await self.bridge.dispatch(provider_request(effect=f"image:{count}", images=[pack_bytes(data)] * count))
            self.assertTrue(response["ok"], response)
            self.assertEqual([picture.data for picture in self.provider.calls[-1][2]], [data] * count)
        before = len(self.provider.calls)
        for values in ([pack_bytes(data)] * 3, ["/codex/auth.json"], [pack_bytes(b"broken PNG")]):
            self.assertFalse((await self.bridge.dispatch(provider_request(effect="invalid-image", images=values)))["ok"])
        self.assertEqual(len(self.provider.calls), before)

    async def test_cancelled_provider_is_terminated_and_receipt_not_retried(self):
        self.provider.wait = True
        task = asyncio.create_task(self.bridge.dispatch(provider_request()))
        await self.provider.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.provider.cancelled)
        result = await self.bridge.dispatch(provider_request())
        self.assertEqual(result["error"]["kind"], "uncertain")
        self.assertEqual(len(self.provider.calls), 1)

    async def test_nonowner_send_unknown_methods_and_paths_denied(self):
        requests = [
            {"op": "telegram.send_message", "chat_id": 77, "text": "bad", "effect_id": "test", "attempt": "0"},
            {"op": "telegram.call", "method": "deleteMessage", "payload": {}},
            {"op": "provider.complete", **{key: value for key, value in provider_request().items() if key != "op"}, "path": "/codex/auth.json"},
            {"op": "telegram.send_document", "chat_id": OWNER, "path": "/codex/auth.json"},
        ]
        for request in requests:
            self.assertFalse((await self.bridge.dispatch(request))["ok"])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.telegram.sent, [])

    async def test_download_requires_original_owner_file_and_matching_type(self):
        self.telegram.files["file_A"] = b"hello"
        self.bridge.journal.ingest([update(1, extra={"document": {"file_id": "file_A", "file_unique_id": "uniq",
                                                          "file_name": "a.txt", "file_size": 5}})])
        request = {"op": "telegram.download", "file_id": "file_A", "max_bytes": 100,
                   "expected_size": 5, "image": False, "voice": False}
        self.assertEqual((await self.bridge.dispatch(request))["result"], {"data": pack_bytes(b"hello")})
        self.assertFalse((await self.bridge.dispatch(request | {"file_id": "unknown"}))["ok"])
        self.assertFalse((await self.bridge.dispatch(request | {"image": True}))["ok"])
        self.assertEqual(self.telegram.calls, [("download", "file_A")])

    async def test_twenty_mib_document_has_bounded_frame_and_single_receipt(self):
        # SICA deliberately executes this suite under the runner's 16 MiB
        # file ceiling. The protected bridge has its own larger tmpfs; its
        # real 20 MiB route is exercised by normal Linux and bridge drills.
        if os.name != "nt":
            import resource
            ceiling = resource.getrlimit(resource.RLIMIT_FSIZE)[0]
            if 0 <= ceiling < MAX_DOCUMENT_BYTES:
                self.skipTest("Runner file ceiling is below the protected bridge document limit")
        data = b"x" * MAX_DOCUMENT_BYTES
        request = {"op": "telegram.send_document", "chat_id": OWNER, "caption": "test",
                   "filename": "../token.txt", "data": pack_bytes(data), "effect_id": "delivery:1", "attempt": "0"}
        self.assertLess(len(canonical(request)), MAX_FRAME)
        self.assertTrue((await self.bridge.dispatch(request))["ok"])
        self.assertTrue((await self.bridge.dispatch(request))["ok"])
        self.assertEqual(len(self.telegram.sent), 1)
        self.assertEqual(self.telegram.sent[0][2], data)
        self.assertNotIn("/", self.telegram.sent[0][1])

    async def test_partial_send_is_uncertain_and_keeps_known_message_ids(self):
        error = TelegramRetryAfter(5)
        error.sent_message_ids = [42]
        self.telegram.error = error
        request = {"op": "telegram.send_message", "chat_id": OWNER, "text": "long", "effect_id": "delivery:2", "attempt": "0"}
        result = await self.bridge.dispatch(request)
        self.assertTrue(result["error"]["uncertain"])
        self.assertEqual(result["error"]["sent_message_ids"], [42])
        replay = await self.bridge.dispatch(request)
        self.assertEqual(replay["error"]["sent_message_ids"], [42])
        self.assertEqual(len(self.telegram.sent), 1)

    async def test_definite_rate_limit_without_partial_send_can_retry_after_delay(self):
        self.telegram.error = TelegramRetryAfter(5)
        request = {"op": "telegram.send_message", "chat_id": OWNER, "text": "hello", "effect_id": "delivery:rate", "attempt": "0"}
        first = await self.bridge.dispatch(request)
        self.assertEqual(first["error"]["retry_after"], 5)
        self.telegram.error = None
        self.assertFalse((await self.bridge.dispatch(request))["ok"])
        self.assertEqual(len(self.telegram.sent), 1)
        with self.bridge.journal.connect() as db:
            db.execute("UPDATE effects SET updated=updated-6 WHERE effect_id='delivery:rate'")
        self.assertTrue((await self.bridge.dispatch(request))["ok"])
        self.assertTrue((await self.bridge.dispatch(request))["ok"])
        self.assertEqual(len(self.telegram.sent), 2)

    async def test_auth_status_and_errors_never_include_provider_extra_or_webhook_secret(self):
        result = await self.bridge.dispatch({"op": "provider.status"})
        self.assertTrue(result["result"]["authenticated"])
        self.assertIsNone(result["result"]["model_resolved"])
        self.assertNotIn(SECRET, json.dumps(result))
        result = await self.bridge.dispatch({"op": "telegram.webhook"})
        self.assertEqual(result["result"]["url"], "configured")
        self.assertNotIn(SECRET, json.dumps(result))

    async def test_voice_requires_journal_source_and_original_download_hash(self):
        audio = b"OggS" + b"OpusHead" + b"x" * 80
        self.telegram.files["voice_A"] = audio
        self.bridge.journal.ingest([update(5, extra={"voice": {"file_id": "voice_A", "file_unique_id": "uniq", "duration": 2, "file_size": len(audio)}})])
        calls = []

        async def speech(key, value, **kwargs):
            calls.append(value)
            return {"text": "hello", "sha256": hashlib.sha256(value).hexdigest(), "duration_seconds": 2.0,
                    "engine": "openai", "model": "gpt-4o-transcribe", "language": "", "trust": "unverified_transcription"}
        self.bridge.speech = speech
        request = {"op": "voice.transcribe", "audio": pack_bytes(audio), "source": "telegram:5",
                   "attempt": "0", "duration": 2, "timeout": 125}
        self.assertFalse((await self.bridge.dispatch(request))["ok"])
        download = {"op": "telegram.download", "file_id": "voice_A", "max_bytes": 2097152,
                    "expected_size": len(audio), "image": False, "voice": True}
        self.assertTrue((await self.bridge.dispatch(download))["ok"])
        self.assertTrue((await self.bridge.dispatch(request))["ok"])
        self.assertTrue((await self.bridge.dispatch(request))["ok"])
        self.assertTrue((await self.bridge.dispatch(request | {"attempt": "random-restored-lease"}))["ok"])
        self.assertEqual(calls, [audio])
        self.assertFalse((await self.bridge.dispatch(request | {"audio": pack_bytes(audio + b"x")}))["ok"])


class FramingTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_lengths_truncation_duplicates_nan_and_nonobjects(self):
        for payload in (b"{}", b'{"op":1,"op":2}', b'{"x":NaN}', b'[]', b'\xff'):
            reader = asyncio.StreamReader()
            reader.feed_data(struct.pack("!I", len(payload)) + payload)
            reader.feed_eof()
            if payload == b"{}":
                self.assertEqual(await read_frame(reader), {})
            else:
                with self.assertRaises(BridgeError):
                    await read_frame(reader)
        for length in (0, MAX_FRAME + 1, 0xffffffff):
            reader = asyncio.StreamReader()
            reader.feed_data(struct.pack("!I", length))
            with self.assertRaises(BridgeError):
                await read_frame(reader)
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack("!I", 10) + b"{}")
        reader.feed_eof()
        with self.assertRaises(asyncio.IncompleteReadError):
            await read_frame(reader)

    async def test_clients_preserve_errors_and_retry_identity(self):
        requests = []

        async def rpc(socket, request, **kwargs):
            requests.append(request)
            return {"__bridge_error__": {"kind": "uncertain", "uncertain": True, "sent_message_ids": [55], "raw": SECRET}}
        with patch("marka.bridge_client._rpc", side_effect=rpc):
            provider = BridgeProvider("/unused")
            with self.assertRaises(ProviderError) as exc:
                await provider.complete("hello", {"type": "object"}, effect_id="job:1", attempt="owner-7")
            self.assertNotIn(SECRET, str(exc.exception))
            self.assertEqual(requests[-1]["attempt"], "owner-7")
            client = BridgeTelegramClient("/unused")
            with self.assertRaises(TelegramError) as exc:
                await client.send_message(OWNER, "hi", effect_id="delivery:1")
            self.assertTrue(exc.exception.uncertain)
            self.assertEqual(exc.exception.sent_message_ids, [55])
            self.assertNotIn(SECRET, str(exc.exception))
            with self.assertRaises(VoiceError):
                await bridge_transcribe("/unused", b"OggSOpusHead" + b"x" * 80, source="telegram:1", attempt="0", duration=2)
            with self.assertRaises(TelegramError):
                await client.call("sendMessage", {})

    async def test_document_client_uses_supplied_snapshot_without_reopening_path(self):
        requests = []

        async def rpc(socket, request, **kwargs):
            requests.append(request)
            return 7
        with patch("marka.bridge_client._rpc", side_effect=rpc):
            client = BridgeTelegramClient("/unused")
            result = await client.send_document(OWNER, Path("does-not-exist.txt"), content=b"snapshot", effect_id="doc:1")
        self.assertEqual(result, 7)
        self.assertEqual(requests[0]["data"], pack_bytes(b"snapshot"))
        self.assertNotIn("path", requests[0])


class MemoryWriter:
    def __init__(self, peer=None):
        self.data = bytearray()
        self.closed = asyncio.Event()
        self.peer = peer

    def get_extra_info(self, name):
        return self.peer if name == "socket" else None

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass

    def close(self):
        self.closed.set()

    async def wait_closed(self):
        await self.closed.wait()


class ServerTransportTests(unittest.IsolatedAsyncioTestCase):
    # Use the real framed stream handler without requiring Unix sockets on Windows.
    # Avoid inheriting the entire functional suite a second time.
    setUp = BridgeTests.setUp
    async def test_handler_response_roundtrip_and_disconnect_cancellation(self):
        reader, writer = asyncio.StreamReader(), MemoryWriter()
        encoded = canonical(provider_request())
        reader.feed_data(struct.pack("!I", len(encoded)) + encoded)
        await self.bridge.handle(reader, writer)
        response = asyncio.StreamReader()
        response.feed_data(bytes(writer.data))
        self.assertEqual(await read_frame(response), {"ok": True, "result": {"answer": "done"}})
        self.provider.wait = True
        self.provider.entered.clear()
        reader, writer = asyncio.StreamReader(), MemoryWriter()
        encoded = canonical(provider_request(effect="cancel:next"))
        reader.feed_data(struct.pack("!I", len(encoded)) + encoded)
        task = asyncio.create_task(self.bridge.handle(reader, writer))
        await self.provider.entered.wait()
        reader.feed_eof()
        await task
        self.assertTrue(self.provider.cancelled)
        repeated = await self.bridge.dispatch(provider_request(effect="cancel:next"))
        self.assertEqual(repeated["error"]["kind"], "uncertain")

    async def test_extra_frame_bytes_cancel_instead_of_dispatching_second_operation(self):
        self.provider.wait = True
        reader, writer = asyncio.StreamReader(), MemoryWriter()
        encoded = canonical(provider_request())
        reader.feed_data(struct.pack("!I", len(encoded)) + encoded + b"unexpected")
        await self.bridge.handle(reader, writer)
        self.assertLessEqual(len(self.provider.calls), 1)
        result = await self.bridge.dispatch(provider_request())
        self.assertEqual(result["error"]["kind"], "uncertain")

    async def test_invalid_frame_produces_no_raw_exception_or_remote_calls(self):
        reader, writer = asyncio.StreamReader(), MemoryWriter()
        reader.feed_data(struct.pack("!I", MAX_FRAME + 1))
        await self.bridge.handle(reader, writer)
        self.assertEqual(writer.data, b"")
        self.assertEqual(self.provider.calls, [])

    async def test_excess_reconnections_are_closed_before_frame_read(self):
        self.bridge._connections = 8
        writer = MemoryWriter()
        await asyncio.wait_for(self.bridge.handle(asyncio.StreamReader(), writer), 1)
        self.assertTrue(writer.closed.is_set())
        self.assertEqual(writer.data, b"")
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.bridge._connections, 8)


if __name__ == "__main__":
    unittest.main()
