"""Operator model settings must survive transport without opening RPC overrides."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from marka.bridge import Bridge
from marka.bridge_client import BridgeError, BridgeProvider, server_read
from marka.config import Settings
from marka.provider import CodexProvider, REASONING_EFFORTS
import test_bridge as bridge_fixtures


class ModelSettingsTests(unittest.TestCase):
    def test_existing_positional_constructor_keeps_timeout_and_unset_effort(self):
        provider = CodexProvider("codex", Path("."), "gpt-5.6-sol", 42)
        self.assertEqual(provider.timeout, 42)
        self.assertIsNone(provider.reasoning_effort)
        args = provider._arguments("codex", Path("."))
        self.assertFalse(any(item.startswith("model_reasoning_effort=") for item in args))

    def test_each_valid_effort_is_one_quoted_config_value_and_none_is_explicit(self):
        for effort in REASONING_EFFORTS:
            with self.subTest(effort=effort):
                provider = CodexProvider(model="gpt-5.6-sol", reasoning_effort=effort)
                args = provider._arguments("codex", Path("."))
                overrides = [args[i + 1] for i, value in enumerate(args) if value == "-c"]
                self.assertIn("model_reasoning_effort=" + json.dumps(effort), overrides)
                self.assertEqual(args[args.index("--model") + 1], "gpt-5.6-sol")
                self.assertEqual(args[-1], "-")

    def test_invalid_settings_never_reach_cli_or_echo_input(self):
        values = ("", " HIGH", "high\nweb_search=true", "high\"", "private-secret", True, 12, [], {})
        for value in values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Invalid Codex reasoning effort setting") as caught:
                    CodexProvider(reasoning_effort=value)
                self.assertNotIn("private-secret", str(caught.exception))
        for model in ("", "--config", "model name", "gpt\nsecret", "a" * 101, False, [], {}):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValueError, "Invalid Codex model setting"):
                    CodexProvider(model=model)

    def test_settings_roundtrip_and_environment_reach_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(Path(temporary), model="gpt-5.6-sol", reasoning_effort="high")
            settings.save()
            with patch.dict(os.environ, {"MARKA_MODEL": "gpt-5.6-sol", "MARKA_REASONING_EFFORT": "medium"}):
                loaded = Settings.load(temporary)
            self.assertEqual(loaded.reasoning_effort, "medium")
            self.assertEqual(loaded.provider().reasoning_effort, "medium")
            self.assertEqual(json.loads((Path(temporary) / "settings.json").read_text())["reasoning_effort"], "high")
            with patch.dict(os.environ, {"MARKA_REASONING_EFFORT": "high\ninvalid"}):
                with self.assertRaises(ValueError):
                    Settings.load(temporary)

    def test_invalid_saved_setting_fails_before_creating_private_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state"
            with self.assertRaises(ValueError):
                Settings(path, reasoning_effort="invalid").save()
            self.assertFalse(path.exists())


class ModelTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_uses_explicit_model_effort_and_preserves_isolation(self):
        provider = CodexProvider(model="gpt-5.6-sol", reasoning_effort="high")
        calls = []

        async def run(args, **kwargs):
            calls.append(args)
            if args == ["codex", "login", "status"]:
                return 0, b"", b"Logged in using ChatGPT"
            (kwargs["cwd"] / "response.json").write_text('{"answer":"ok"}')
            return 0, b'{"type":"turn.completed"}\n', b""

        with patch.object(provider, "_check_cli", new=AsyncMock(return_value="codex")), \
                patch.object(provider, "_run", side_effect=run):
            self.assertEqual(await provider.complete("Hello", {"type": "object"}), {"answer": "ok"})
        args = calls[-1]
        self.assertEqual(args[args.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', args)
        for value in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "read-only", "--output-schema"):
            self.assertIn(value, args)
        self.assertIn('web_search="disabled"', args)
        self.assertIn("tools.view_image=false", args)

    async def test_provider_status_distinguishes_requested_from_unobserved_resolved(self):
        provider = CodexProvider(model="gpt-5.6-sol", reasoning_effort="high")
        with patch.object(provider, "_check_cli", new=AsyncMock(return_value="codex")), \
                patch.object(provider, "_run", new=AsyncMock(return_value=(0, b"", b"Logged in using ChatGPT"))) as run:
            status = await provider.status()
        self.assertEqual(status["model_requested"], "gpt-5.6-sol")
        self.assertEqual(status["reasoning_effort_requested"], "high")
        self.assertIsNone(status["model_resolved"])
        self.assertIsNone(status["reasoning_effort_resolved"])
        self.assertTrue(status["authenticated"])
        self.assertEqual(run.call_args.args[0], ["codex", "login", "status"])
        self.assertEqual(run.call_count, 1, "Status must not start inference")

    async def test_bridge_old_config_and_explicit_settings_are_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = bridge_fixtures.configuration(temporary)
            fake = bridge_fixtures.FakeProvider()
            legacy = Bridge(config, telegram=bridge_fixtures.FakeTelegram(), provider=fake)
            self.assertIsNone((await legacy.dispatch({"op": "provider.status"}))["result"]["reasoning_effort_requested"])
            config["reasoning_effort"] = "high"
            bridge = Bridge(config, telegram=bridge_fixtures.FakeTelegram(), provider=fake)
            config["reasoning_effort"] = "low"
            for op in ("provider.status", "status"):
                result = (await bridge.dispatch({"op": op}))["result"]
                self.assertEqual(result["reasoning_effort_requested"], "high")
                self.assertIsNone(result["model_resolved"])
                self.assertIsNone(result["reasoning_effort_resolved"])
                self.assertNotIn(bridge_fixtures.SECRET, json.dumps(result))

    async def test_bridge_constructs_provider_with_operator_owned_effort(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = bridge_fixtures.configuration(temporary) | {"reasoning_effort": "high"}
            with patch("marka.bridge.CodexProvider") as constructor:
                Bridge(config, telegram=bridge_fixtures.FakeTelegram())
            self.assertEqual(constructor.call_args.kwargs["reasoning_effort"], "high")
            self.assertEqual(constructor.call_args.kwargs["model"], config["model"])

    async def test_bridge_rejects_config_injection_and_request_level_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = bridge_fixtures.configuration(temporary)
            fake = bridge_fixtures.FakeProvider()
            for invalid in ({"reasoning_effort": "high\nsecret"}, {"reasoning_effort": {}}, {"model_provider": "other"}):
                with self.assertRaises(BridgeError):
                    Bridge(config | invalid, telegram=bridge_fixtures.FakeTelegram(), provider=fake)
            self.assertFalse(Path(config["journal"]).exists(), "Invalid settings must not create a journal")
            bridge = Bridge(config | {"reasoning_effort": "high"}, telegram=bridge_fixtures.FakeTelegram(), provider=fake)
            for override in ({"model": "gpt-5.6-sol"}, {"reasoning_effort": "ultra"}, {"profile": "deep"}):
                result = await bridge.dispatch(bridge_fixtures.provider_request(**override))
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["kind"], "invalid")
            self.assertEqual(fake.calls, [])
            with bridge.journal.connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM effects").fetchone()[0], 0)

    async def test_bridge_client_preserves_settings_metadata_without_new_rpc_fields(self):
        status = {"authenticated": True, "model_requested": "gpt-5.6-sol", "model_resolved": None,
                  "reasoning_effort_requested": "high", "reasoning_effort_resolved": None}
        with patch("marka.bridge_client._rpc", new=AsyncMock(return_value=status)) as rpc:
            result = await BridgeProvider("/runtime/bridge.sock").status()
        self.assertEqual(result, status)
        self.assertEqual(rpc.call_args.args[1], {"op": "provider.status"})


class ServerSnapshotBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.config = bridge_fixtures.configuration(self.directory)
        self.config["server_snapshot_dir"] = str(self.directory)
        self.bridge = Bridge(self.config, telegram=bridge_fixtures.FakeTelegram(),
                             provider=bridge_fixtures.FakeProvider())
        self.request = {"op": "server.read", "section": "status", "offset": 0, "expected_sha256": ""}
        self.read = Mock(return_value={"section": "status", "content": "sanitized", "read_only": True})
        helper = SimpleNamespace(SECTIONS=frozenset({"status", "config", "events", "guardian_source", "observer_source"}),
                                 read_snapshot=self.read)
        patcher = patch.dict(sys.modules, {"marka.server_read": helper})
        patcher.start()
        self.addCleanup(patcher.stop)

    def audit(self):
        with self.bridge.journal.connect() as db:
            return [tuple(row) for row in db.execute("SELECT section,ok FROM read_audit ORDER BY id")]

    async def test_only_fixed_sections_reach_reader_and_reads_are_independently_audited(self):
        self.assertTrue((await self.bridge.dispatch({"op": "status"}))["result"]["server_read_available"])
        result = await self.bridge.dispatch(self.request)
        self.assertEqual(result, {"ok": True, "result": self.read.return_value})
        self.read.assert_called_once_with(str(self.directory), "status", offset=0, expected_sha256="")
        self.assertEqual(self.audit(), [("status", 1)])
        self.assertEqual(self.bridge.provider.calls, [])

    async def test_reader_failures_are_redacted_and_audited(self):
        for exc, kind in ((ValueError("private-path-and-secret"), "invalid"),
                          (OSError("private-path-and-secret"), "unavailable")):
            self.read.side_effect = exc
            result = await self.bridge.dispatch(self.request)
            self.assertEqual(result["error"]["kind"], kind)
            self.assertNotIn("private", json.dumps(result))
        self.assertEqual(self.audit(), [("status", 0), ("status", 0)])

    async def test_invalid_read_requests_fail_before_helper_and_audit(self):
        for override in ({"section": "../auth.json"}, {"section": []}, {"offset": True},
                         {"offset": -1}, {"offset": 1024 * 1024 + 1}, {"expected_sha256": "invalid"},
                         {"expected_sha256": 0}, {"path": "/codex/auth.json"}):
            result = await self.bridge.dispatch(self.request | override)
            self.assertEqual(result["error"]["kind"], "invalid")
        self.read.assert_not_called()
        self.assertEqual(self.audit(), [])

    async def test_read_audit_retains_latest_two_thousand_without_output(self):
        with self.bridge.journal.connect() as db:
            db.executemany("INSERT INTO read_audit(created,section,ok) VALUES(?,?,?)",
                           [(0, "status", 1)] * 2000)
        await self.bridge.dispatch(self.request | {"section": "guardian_source"})
        rows = self.audit()
        self.assertEqual(len(rows), 2000)
        self.assertEqual(rows[-1], ("guardian_source", 1))
        with self.bridge.journal.connect() as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(read_audit)")]
        self.assertEqual(columns, ["id", "created", "section", "ok"])

    async def test_client_only_transmits_fixed_rpc_fields_and_redacts_errors(self):
        with patch("marka.bridge_client._rpc", new=AsyncMock(return_value={"read_only": True})) as rpc:
            self.assertEqual(await server_read("/bridge.sock", "guardian_source", offset=10,
                                               expected_sha256="a" * 64), {"read_only": True})
        self.assertEqual(rpc.call_args.args[1], {"op": "server.read", "section": "guardian_source",
                                               "offset": 10, "expected_sha256": "a" * 64})
        with patch("marka.bridge_client._rpc", new=AsyncMock(return_value={"__bridge_error__": {
                "kind": "unavailable", "private": "do-not-echo"}})):
            with self.assertRaises(BridgeError) as caught:
                await server_read("/bridge.sock", "config")
        self.assertNotIn("do-not-echo", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
