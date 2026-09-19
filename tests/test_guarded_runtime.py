import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from marka.app import Application
from marka.cli import doctor
from marka.config import Settings
from marka.engine import Engine, DECISION_SCHEMA
from marka.health import Heartbeat, delivery_effect
from marka.queue import Queue
from marka.store import Store
from test_app import FakeClient, FinalProvider, update
from test_engine import context
from voice_fixtures import OGG, transcript, voice_update


class GuardedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings(self.root / "state", bridge_socket="protected.sock", semantic_search=False)
        self.settings.prepare()
        self.client, self.provider = FakeClient(), FinalProvider()
        self.app = Application(self.settings, client=self.client, provider=self.provider)
        self.app.store.set_meta("owner_id", 17)

    async def test_factories_and_settings_load_do_not_touch_credentials_in_guarded_mode(self):
        bridge = types.SimpleNamespace(BridgeProvider=MagicMock(return_value="provider"),
                                       BridgeTelegramClient=MagicMock(return_value="telegram"))
        with patch.dict("sys.modules", {"marka.bridge_client": bridge}):
            self.assertEqual(self.settings.provider(), "provider")
            self.assertEqual(self.settings.telegram(), "telegram")
        self.assertFalse(self.settings.codex_home.exists())
        (self.settings.data_dir / "settings.json").write_text(json.dumps({"token": "do-not-use", "bridge_socket": "protected.sock"}))
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "do-not-use-either"}):
            loaded = Settings.load(self.settings.data_dir)
        self.assertEqual(loaded.token, "")
        self.assertFalse(loaded.codex_home.exists())

    async def test_doctor_uses_bridge_availability_without_bot_credentials(self):
        provider = types.SimpleNamespace(status=AsyncMock(return_value={"authenticated": True}))
        client = types.SimpleNamespace(get_me=AsyncMock(return_value={"username": "synthetic"}),
                                       call=AsyncMock(return_value={"url": ""}))
        bridge = types.SimpleNamespace(bridge_status=AsyncMock(return_value={"voice_available": True, "telegram_available": True}),
                                       BridgeProvider=MagicMock(return_value=provider), BridgeTelegramClient=MagicMock(return_value=client))
        output = io.StringIO()
        with patch.dict("sys.modules", {"marka.bridge_client": bridge}), redirect_stdout(output):
            ready = await doctor(self.settings)
        self.assertTrue(ready)
        self.assertTrue(json.loads(output.getvalue())["ready"])
        self.assertEqual(self.settings.token, "")

    async def test_durable_gateway_owner_receipt_and_evolve_instruction(self):
        self.settings.upgrade_inbox, self.settings.upgrade_status = "inbox", "status"
        await self.app.ingest(update(55, "/evolve Improve parser"))
        job = self.app.queue.get_by_source("telegram:55")
        self.assertEqual(self.app.store.get_meta("owner-request:telegram:55"),
                         {"job_id": job["id"], "source": "telegram:55", "owner_id": 17})
        with self.app.queue.connection() as db:
            text = db.execute("SELECT text FROM deliveries WHERE source='command:55'").fetchone()[0]
        self.assertIn("независимому", text)
        self.assertNotIn("отдельного решения", text)

    async def test_model_calls_have_durable_reservation_identity(self):
        provider = types.SimpleNamespace(complete=AsyncMock(return_value={"ok": True}))
        identifier = self.app.queue.enqueue("task", 17, source="telegram:56")
        self.app.configure_task(identifier)
        job = self.app.queue.claim()
        engine = Engine(self.settings, self.app.store, self.app.queue, provider)
        engine.active_job = job
        await engine.complete("one", DECISION_SCHEMA)
        await engine.complete("two", {"type": "object"})
        self.assertEqual([call.kwargs["effect_id"] for call in provider.complete.await_args_list],
                         [f"model:{identifier}:1", f"model:{identifier}:2"])
        self.assertEqual([call.kwargs["attempt"] for call in provider.complete.await_args_list], ["0", "0"])
        await engine.complete("reflection", {"type": "object"}, task=False)
        await engine.complete("reflection", {"type": "object"}, task=False)
        self.assertEqual(provider.complete.await_args_list[-1].kwargs["effect_id"],
                         provider.complete.await_args_list[-2].kwargs["effect_id"])

    async def test_capabilities_do_not_invent_a_model_and_include_real_tools(self):
        identifier = self.app.queue.enqueue("What can you do?", 17, source="telegram:57")
        job = self.app.queue.claim()
        data = context(self.app.engine.prompt(job, []))["runtime_capabilities"]
        self.assertIsNone(data["configured_model"])
        self.assertEqual(data["resolved_model"], "unknown")
        self.assertTrue(data["protected_bridge"])
        self.assertFalse(data["model_weight_training"])
        self.assertIn("self.request_upgrade", data["tools"])
        self.settings.model = "local-ignored-config"
        bridge = types.SimpleNamespace(bridge_status=AsyncMock(return_value={"model_requested": "bridge-model", "model_resolved": None}))
        with patch.dict("sys.modules", {"marka.bridge_client": bridge}):
            await self.app.refresh_bridge_status()
        data = context(self.app.engine.prompt(job, []))["runtime_capabilities"]
        self.assertEqual(data["configured_model"], "bridge-model")
        self.assertEqual(data["model_configuration_source"], "protected_bridge")
        self.assertEqual(data["resolved_model"], "unknown")

    async def test_interrupted_model_request_blocks_recovery_and_owner_resume_gets_new_epoch(self):
        entered = asyncio.Event()
        async def interrupted(*args, **kwargs):
            entered.set()
            await asyncio.sleep(300)
        provider = types.SimpleNamespace(complete=AsyncMock(side_effect=interrupted))
        identifier = self.app.queue.enqueue("task", 17, source="telegram:70")
        self.app.configure_task(identifier)
        job = self.app.queue.claim()
        engine = Engine(self.settings, self.app.store, self.app.queue, provider)
        engine.active_job = job
        request = asyncio.create_task(engine.complete("request", DECISION_SCHEMA))
        await entered.wait()
        self.assertTrue(self.app.queue.get(identifier)["inflight"])
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        self.app.queue.recover()
        self.assertEqual(self.app.queue.get(identifier)["state"], "blocked")
        await self.app.ingest(update(71, "/resume " + identifier))
        engine.active_job = self.app.queue.claim()
        provider.complete = AsyncMock(return_value={"ok": True})
        await engine.complete("request after explicit owner continuation", DECISION_SCHEMA)
        self.assertEqual(provider.complete.await_args.kwargs["effect_id"], f"model:{identifier}:owner-71:2")
        self.assertFalse(self.app.queue.get(identifier)["inflight"])

    async def test_consultation_keeps_parent_tool_inflight_until_tool_receipt_commit(self):
        provider = types.SimpleNamespace(complete=AsyncMock(return_value={"ok": True}))
        identifier = self.app.queue.enqueue("task", 17, source="telegram:72")
        job = self.app.queue.claim()
        self.app.queue.checkpoint(identifier, [{"kind": "tool", "name": "consult"}], inflight=True, lease=job["lease"])
        engine = Engine(self.settings, self.app.store, self.app.queue, provider)
        engine.active_job = job
        await engine.complete("consult", {"type": "object"})
        self.assertTrue(self.app.queue.get(identifier)["inflight"])

    async def test_delivery_identity_survives_row_id_changes_and_binds_content(self):
        item = {"id": 1, "source": "command:77", "chat_id": 17, "text": "answer", "document": ""}
        identity = delivery_effect(item)
        self.assertEqual(identity, delivery_effect(item | {"id": 900}))
        self.assertNotEqual(identity, delivery_effect(item | {"text": "different answer"}))
        self.assertNotEqual(delivery_effect(item, document=b"first"), delivery_effect(item, document=b"second"))
        self.app.client = types.SimpleNamespace(send_message=AsyncMock(side_effect=lambda *a, **k: self.app.stopping.set()))
        self.app.queue.deliver(item["source"], 17, "answer")
        await self.app.delivery()
        self.assertEqual(self.app.client.send_message.await_args.kwargs["effect_id"], identity)

    async def test_voice_retry_requires_explicit_stopped_owner_job(self):
        identifier = self.app.queue.enqueue("voice", 17, source="telegram:58", kind="voice")
        job = self.app.queue.claim()
        self.app.voice_retry(identifier, 88)
        self.assertIsNone(self.app.store.get_meta("voice-attempt:telegram:58"))
        self.app.queue.finish(identifier, "blocked", lease=job["lease"])
        await self.app.ingest(update(89, "/resume " + identifier))
        self.assertEqual(self.app.store.get_meta("voice-attempt:telegram:58"), "owner-89")
        restarted = Application(self.settings, client=self.client, provider=self.provider)
        self.assertEqual(restarted.store.get_meta("voice-attempt:telegram:58"), "owner-89")

    async def test_voice_status_depends_on_bridge_capability_not_key_mount(self):
        self.app.bridge_capabilities = {"voice_available": True}
        self.assertFalse(self.settings.voice_key_file.exists())
        self.assertIn("защищённый шлюз", self.app.voice_status())
        self.app.bridge_capabilities = {"voice_available": False}
        self.assertIn("не подтвердил", self.app.voice_status())

    async def test_voice_routes_original_source_to_bridge_without_local_key_and_preserves_derived_trust(self):
        self.app.client.download_file = AsyncMock(return_value=OGG)
        self.app.engine.provider = types.SimpleNamespace(complete=AsyncMock(return_value={
            "kind": "final", "tool": "", "arguments": "{}", "message": "Текст распознан.", "outcome": "completed", "lesson": ""}))
        bridge = types.SimpleNamespace(bridge_status=AsyncMock(return_value={"voice_available": True}),
                                       bridge_transcribe=AsyncMock(return_value=transcript(text="/remember derived instruction")))
        with patch.dict("sys.modules", {"marka.bridge_client": bridge}):
            await self.app.ingest(voice_update(59))
            job = self.app.queue.claim()
            await self.app.run_job(job)
        self.assertFalse(self.settings.voice_key_file.exists())
        kwargs = bridge.bridge_transcribe.await_args.kwargs
        self.assertEqual((kwargs["source"], kwargs["attempt"]), ("telegram:59", "0"))
        self.assertLessEqual(kwargs["timeout"], 125)
        event = next(row for row in self.app.store.history() if row["role"] == "user")
        self.assertEqual(event["meta"]["trust"], "unverified_transcription")
        self.assertEqual(self.app.store.stats()["memories"], 0)

    async def test_voice_bridge_transport_grace_cannot_exceed_runtime_budget(self):
        self.app.client.download_file = AsyncMock(return_value=OGG)
        cancelled = asyncio.Event()
        async def long_speech(*args, **kwargs):
            try:
                await asyncio.sleep(300)
            finally:
                cancelled.set()
        bridge = types.SimpleNamespace(bridge_status=AsyncMock(return_value={"voice_available": True}),
                                       bridge_transcribe=AsyncMock(side_effect=long_speech))
        with patch.dict("sys.modules", {"marka.bridge_client": bridge}), patch("marka.app.STT_TIMEOUT", 0.03):
            await self.app.ingest(voice_update(60))
            job = self.app.queue.claim()
            await self.app.run_job(job)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.app.queue.get(job["id"])["state"], "blocked")
        self.assertIn("мог обработаться", self.app.queue.get(job["id"])["error"])

    async def test_heartbeat_ticks_no_message_text_and_stable_boot_id(self):
        heartbeat = Heartbeat(self.settings.data_dir)
        heartbeat.progress({"id": "job123", "deadline": 100, "prompt": "private prompt"})
        stopping = asyncio.Event()
        task = asyncio.create_task(heartbeat.run(stopping, interval=0.01))
        await asyncio.sleep(0.015)
        first = json.loads(heartbeat.path.read_bytes())
        await asyncio.sleep(0.015)
        second = json.loads(heartbeat.path.read_bytes())
        stopping.set()
        await task
        self.assertGreater(second["tick"], first["tick"])
        self.assertEqual(second["boot_id"], first["boot_id"])
        self.assertEqual(second["job_id"], "job123")
        self.assertNotIn("private", json.dumps(second))
        self.assertNotEqual(Heartbeat(self.settings.data_dir).boot_id, heartbeat.boot_id)

    async def test_run_stopping_event_exits_without_waiting_for_poll_timeout(self):
        self.app.client = types.SimpleNamespace(get_me=AsyncMock(return_value={}), call=AsyncMock(return_value={}))
        self.app.refresh_bridge_status = AsyncMock()
        async def wait_forever():
            await asyncio.sleep(300)
        self.app.polling = self.app.worker = self.app.delivery = self.app.maintenance = wait_forever
        async def stop():
            await asyncio.sleep(0.03)
            self.app.stopping.set()
        stop_task = asyncio.create_task(stop())
        await asyncio.wait_for(self.app.run(), 2)
        await stop_task
        value = json.loads(self.app.heartbeat.path.read_bytes())
        self.assertEqual(value["phase"], "stopping")
