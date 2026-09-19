"""Managed credential references support useful checks without exposing secrets."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch
import urllib.error
import urllib.request

from marka.bridge import Bridge
from marka.bridge_client import BridgeError, connections_check, connections_list
from marka.connections import CHECK_TTL, MAX_RESPONSE, MODEL_ENDPOINT, Connections, check_speech_key
from marka.telegram import TelegramError
from marka.voice_api import APIError, NoRedirect
import test_bridge as fixtures


CANARY = "sk-proj-SYNTHETIC_CANARY_NEVER_RETURN_123456"


class Response:
    status = 200

    def __init__(self, raw):
        self.raw = raw
        self.maximum = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def read(self, maximum):
        self.maximum = maximum
        return self.raw[:maximum]


class SpeechKeyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.key = Path(temporary.name) / "speech.key"
        self.key.write_text(CANARY)
        self.key.chmod(0o600)

    def test_fixed_metadata_get_uses_key_but_does_not_return_it_or_private_metadata(self):
        response = Response(json.dumps({"id": "gpt-4o-transcribe", "object": "model", "owned_by": CANARY,
                                        "permissions": [{"private_id": CANARY}]}).encode())
        opener = Mock()
        opener.open.return_value = response
        value = check_speech_key(self.key, opener=opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, MODEL_ENDPOINT)
        self.assertEqual(request.method, "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + CANARY)
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 12})
        self.assertEqual(response.maximum, MAX_RESPONSE + 1)
        self.assertTrue(response.closed)
        self.assertTrue(value["ok"])
        self.assertTrue(value["network_request"])
        self.assertFalse(value["details"]["transcription_verified"])
        self.assertFalse(value["details"]["billing_verified"])
        self.assertNotIn(CANARY, json.dumps(value))
        self.assertNotIn(str(self.key), json.dumps(value))

    def test_default_opener_blocks_redirects_and_environment_proxies(self):
        response = Response(b'{"id":"gpt-4o-transcribe","object":"model"}')
        opener = Mock()
        opener.open.return_value = response
        with patch("marka.connections.urllib.request.build_opener", return_value=opener) as build:
            self.assertTrue(check_speech_key(self.key)["ok"])
        handlers = build.call_args.args
        self.assertIsInstance(handlers[0], urllib.request.ProxyHandler)
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], NoRedirect)
        with self.assertRaisesRegex(APIError, "redirect_denied"):
            handlers[1].redirect_request(None, None, 302, "redirect", {}, "https://private.invalid")

    def test_http_errors_discard_bodies_headers_and_urls(self):
        class Unreadable(io.BytesIO):
            def read(self, *args):
                raise AssertionError("An error body must not be read")
        for code, kind in ((401, "authentication_failed"), (403, "access_denied"),
                           (404, "model_unavailable"), (429, "rate_limit"), (500, "service_unavailable")):
            body = Unreadable(CANARY.encode())
            error = urllib.error.HTTPError("https://private.invalid/" + CANARY, code, CANARY, {"x-private": CANARY}, body)
            opener = Mock()
            opener.open.side_effect = error
            value = check_speech_key(self.key, opener=opener)
            self.assertFalse(value["ok"])
            self.assertEqual(value["error"], kind)
            self.assertTrue(body.closed)
            self.assertNotIn(CANARY, json.dumps(value))

    def test_bounded_invalid_and_wrong_model_responses_fail(self):
        for raw in (b"x" * (MAX_RESPONSE + 1), b"{", b"[]", b"\xff",
                    b'{"id":"another-model","object":"model"}', b'{"id":"gpt-4o-transcribe","object":"other"}'):
            opener = Mock()
            opener.open.return_value = Response(raw)
            self.assertEqual(check_speech_key(self.key, opener=opener)["error"], "invalid_response")

    def test_missing_or_malformed_key_does_not_start_network(self):
        opener = Mock()
        self.assertEqual(check_speech_key(self.key.with_name("absent"), opener=opener)["error"], "key_unavailable")
        self.key.write_text("short")
        self.assertFalse(check_speech_key(self.key, opener=opener)["network_request"])
        self.key.write_text("x" * 19 + "\nInjected: header")
        self.assertEqual(check_speech_key(self.key, opener=opener)["error"], "key_unavailable")
        opener.open.assert_not_called()

    def test_symlink_key_does_not_start_network(self):
        link = self.key.with_name("linked.key")
        try:
            link.symlink_to(self.key)
        except OSError:
            self.skipTest("Creating links requires platform permission")
        opener = Mock()
        self.assertEqual(check_speech_key(link, opener=opener)["error"], "key_unavailable")
        opener.open.assert_not_called()

    def test_network_exceptions_and_redirects_return_only_known_error_classes(self):
        for exc, kind in ((urllib.error.URLError(CANARY), "network_error"),
                          (APIError("redirect_denied"), "redirect_denied"),
                          (RuntimeError(CANARY), "service_unavailable")):
            opener = Mock()
            opener.open.side_effect = exc
            value = check_speech_key(self.key, opener=opener)
            self.assertEqual(value["error"], kind)
            self.assertNotIn(CANARY, json.dumps(value))


class RegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.key = self.directory / "speech.key"
        self.key.write_text(CANARY)
        self.key.chmod(0o600)
        self.provider = fixtures.FakeProvider()
        self.provider.status = AsyncMock(return_value={"authenticated": True, "auth_method": "chatgpt",
                                                       "version": "0.144.1", "secret": CANARY, "account_id": CANARY})
        self.telegram = fixtures.FakeTelegram()
        self.telegram.get_me = AsyncMock(return_value={"id": 123456, "is_bot": True, "username": "test_bot",
                                                       "first_name": CANARY, "owner_id": 87654321})
        self.registry = Connections(provider=self.provider, telegram=self.telegram, speech_key_file=self.key)

    async def test_list_is_reference_only_and_does_not_authenticate_or_read_values(self):
        with patch("marka.connections.read_key", side_effect=AssertionError("Do not read key for registry")):
            result = self.registry.list()
        self.assertEqual([row["id"] for row in result["connections"]], ["codex", "telegram", "openai_speech"])
        self.assertTrue(all(row["available"] is None and row["verification_scope"] == "not_checked" for row in result["connections"]))
        self.assertTrue(all(row["allowed_actions"] and row["configured"] for row in result["connections"]))
        self.assertRegex(result["request_id"], r"^[0-9a-f]{32}$")
        self.provider.status.assert_not_called()
        self.telegram.get_me.assert_not_called()
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertNotIn(str(self.key), json.dumps(result))

    async def test_codex_local_status_does_not_claim_a_model_roundtrip_or_return_private_fields(self):
        result = await self.registry.check("codex")
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification_scope"], "local_login")
        self.assertFalse(result["network_request"])
        self.assertFalse(result["inference_performed"])
        self.assertFalse(result["secret_values_exposed"])
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertEqual(self.provider.calls, [])
        self.assertTrue(self.registry.list()["connections"][0]["available"])

    async def test_telegram_only_exposes_sanitized_bot_username_and_no_ids(self):
        result = await self.registry.check("telegram")
        self.assertTrue(result["ok"])
        self.assertEqual(result["details"], {"is_bot": True, "username": "test_bot"})
        self.assertEqual(result["verification_scope"], "bot_identity")
        for private in (CANARY, "123456", "87654321"):
            self.assertNotIn(private, json.dumps(result))
        self.assertEqual(self.telegram.sent, [])

    async def test_speech_check_reports_its_narrow_scope_without_transcribing(self):
        with patch("marka.connections.check_speech_key", return_value={"ok": True, "error": None,
                   "network_request": True, "details": {"model": "gpt-4o-transcribe", "model_visible": True,
                   "transcription_verified": False, "billing_verified": False}}) as checker:
            result = await self.registry.check("openai_speech")
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification_scope"], "model_metadata")
        self.assertFalse(result["details"]["transcription_verified"])
        checker.assert_called_once_with(self.key)
        self.assertEqual(self.provider.calls, [])

    async def test_success_and_failure_cache_expire_and_results_are_detached(self):
        first = await self.registry.check("codex")
        first["details"]["auth_method"] = "tampered"
        second = await self.registry.check("codex")
        self.assertTrue(second["cached"])
        self.assertEqual(second["details"]["auth_method"], "chatgpt")
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(self.provider.status.call_count, 1)
        stamp, value = self.registry._cache["codex"]
        self.registry._cache["codex"] = (stamp - CHECK_TTL - 1, value)
        self.provider.status.side_effect = RuntimeError(CANARY)
        failed = await self.registry.check("codex")
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error"], "service_unavailable")
        self.assertTrue((await self.registry.check("codex"))["cached"])
        self.assertEqual(self.provider.status.call_count, 2)
        self.assertNotIn(CANARY, json.dumps(failed))

    async def test_parallel_and_cancelled_callers_share_one_check(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def status():
            entered.set()
            await release.wait()
            return {"authenticated": True, "auth_method": "chatgpt", "version": "0.144.1"}

        self.provider.status.side_effect = status
        first = asyncio.create_task(self.registry.check("codex"))
        await entered.wait()
        second = asyncio.create_task(self.registry.check("codex"))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertTrue((await second)["ok"])
        self.assertTrue((await self.registry.check("codex"))["cached"])
        self.assertEqual(self.provider.status.call_count, 1)

    async def test_timeout_errors_and_unknown_connections_are_bounded_and_redacted(self):
        async def wait_forever():
            await asyncio.Event().wait()
        self.provider.status.side_effect = wait_forever
        with patch("marka.connections.CHECK_TIMEOUT", 0.03):
            result = await self.registry.check("codex")
        self.assertEqual(result["error"], "check_timeout")
        self.telegram.get_me.side_effect = TelegramError(CANARY, code=401)
        result = await self.registry.check("telegram")
        self.assertEqual(result["error"], "authentication_failed")
        self.assertNotIn(CANARY, json.dumps(result))
        for connection in ("../auth.json", "https://private.invalid", [], {}, None):
            with self.assertRaises(ValueError):
                await self.registry.check(connection)


class BridgeConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.provider = fixtures.FakeProvider()
        self.telegram = fixtures.FakeTelegram()
        self.bridge = Bridge(fixtures.configuration(temporary.name), provider=self.provider, telegram=self.telegram)

    async def test_fixed_requests_are_audited_without_changing_inference_budget(self):
        listed = await self.bridge.dispatch({"op": "connections.list"})
        self.assertTrue(listed["ok"])
        checked = await self.bridge.dispatch({"op": "connections.check", "connection": "codex"})
        self.assertTrue(checked["result"]["ok"])
        await self.bridge.dispatch({"op": "connections.check", "connection": "codex"})
        with self.bridge.journal.connect() as db:
            audit = [tuple(row) for row in db.execute("SELECT section,ok FROM read_audit ORDER BY id")]
            effects = db.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
        self.assertEqual(audit, [("connection:list", 1), ("connection:codex", 1), ("connection:codex", 1)])
        self.assertEqual(effects, 0)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.telegram.sent, [])

    async def test_paths_methods_headers_urls_and_new_connections_are_rejected(self):
        request = {"op": "connections.check", "connection": "codex"}
        for invalid in ({"connection": "custom"}, {"connection": []}, {"path": "/codex/auth.json"},
                        {"url": "https://private.invalid"}, {"headers": {}}, {"method": "POST"}, {"force": True}):
            result = await self.bridge.dispatch(request | invalid)
            self.assertEqual(result["error"]["kind"], "invalid")
        with self.bridge.journal.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM read_audit").fetchone()[0], 0)

    async def test_clients_transmit_only_fixed_fields_and_never_return_raw_errors(self):
        with patch("marka.bridge_client._rpc", new=AsyncMock(return_value={"ok": True})) as rpc:
            self.assertEqual(await connections_list("/bridge.sock"), {"ok": True})
            self.assertEqual(rpc.call_args.args[1], {"op": "connections.list"})
            await connections_check("/bridge.sock", "telegram")
            self.assertEqual(rpc.call_args.args[1], {"op": "connections.check", "connection": "telegram"})
        with patch("marka.bridge_client._rpc", new=AsyncMock(return_value={"__bridge_error__": {"kind": "unavailable", "secret": CANARY}})):
            with self.assertRaises(BridgeError) as caught:
                await connections_check("/bridge.sock", "codex")
        self.assertNotIn(CANARY, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
