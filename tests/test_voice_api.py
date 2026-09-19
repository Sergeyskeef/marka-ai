import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.error
import urllib.request

from marka.voice import transcribe, VoiceError
from marka.voice_api import APIError, ENDPOINT, MAX_RESPONSE, MODEL, NoRedirect, ogg_duration, read_key, request_audio
from voice_fixtures import OGG, page


class Response(io.BytesIO):
    status = 200


class VoiceAPITests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "openai-stt.key"
        self.key = "sk-synthetic-test-key-not-a-secret"
        self.path.write_text(self.key)
        self.path.chmod(0o600)

    def test_exact_endpoint_multipart_and_file_key_only(self):
        opener = MagicMock()
        opener.open.return_value = Response(b'{"text":"Test transcription"}')
        with patch.dict(os.environ, {"OPENAI_API_KEY": "wrong-environment-key", "OPENAI_BASE_URL": "https://invalid.test"}):
            result = request_audio(self.path, OGG, opener=opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + self.key)
        self.assertIn(OGG, request.data)
        self.assertIn(MODEL.encode(), request.data)
        self.assertIn(b'filename="voice.ogg"', request.data)
        self.assertNotIn(self.key.encode(), request.data)
        self.assertEqual(result, {"text": "Test transcription", "engine": "openai", "model": MODEL, "duration_seconds": 0.02})

    def test_redirect_is_denied_before_any_followup(self):
        with self.assertRaises(APIError):
            NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://other.test")
        with patch("marka.voice_api.urllib.request.build_opener") as build:
            build.return_value.open.return_value = Response(b'{"text":"ok"}')
            request_audio(self.path, OGG)
        self.assertTrue(any(isinstance(handler, NoRedirect) for handler in build.call_args.args))
        proxy = next(handler for handler in build.call_args.args if isinstance(handler, urllib.request.ProxyHandler))
        self.assertEqual(proxy.proxies, {})

    def test_http_errors_never_return_raw_response_or_credentials(self):
        for code, safe in ((400, "invalid_audio"), (401, "authentication_failed"), (403, "access_denied"),
                           (429, "rate_limit"), (500, "service_unavailable")):
            opener = MagicMock()
            body = io.BytesIO((self.key + " private user transcript").encode())
            opener.open.side_effect = urllib.error.HTTPError(ENDPOINT, code, self.key, {}, body)
            with self.assertRaisesRegex(APIError, "^" + safe + "$"):
                request_audio(self.path, OGG, opener=opener)
            self.assertTrue(body.closed)

    def test_response_size_shape_and_network_errors_are_bounded(self):
        for body in (b"x" * (MAX_RESPONSE + 1), b"not json", b'[]', b'{"text":null}'):
            opener = MagicMock()
            opener.open.return_value = Response(body)
            with self.assertRaisesRegex(APIError, "invalid_response"):
                request_audio(self.path, OGG, opener=opener)
        opener = MagicMock()
        opener.open.side_effect = urllib.error.URLError(self.key)
        with self.assertRaisesRegex(APIError, "^network_error$"):
            request_audio(self.path, OGG, opener=opener)

    def test_complete_crc_stream_and_duration_limit_before_any_api_call(self):
        self.assertEqual(ogg_duration(OGG), 0.02)
        for invalid in (OGG[:-1], OGG + b"x", OGG[:-1] + b"x", OGG + OGG):
            with self.assertRaises(APIError):
                ogg_duration(invalid)
        head = OGG[:OGG.rfind(b"OggS")]
        packets = [page(bytes.fromhex("f8fffe"), index + 2, 0, granule=(index + 1) * 960) for index in range(2999)]
        maximum = head + b"".join(packets) + page(bytes.fromhex("f8fffe"), 3001, 4, granule=3000 * 960)
        self.assertEqual(ogg_duration(maximum), 60)
        excessive = head + b"".join(packets) + page(bytes.fromhex("f8fffe"), 3001, 0, granule=3000 * 960) + page(bytes.fromhex("f8fffe"), 3002, 4, granule=3001 * 960)
        opener = MagicMock()
        with self.assertRaisesRegex(APIError, "too_long"):
            request_audio(self.path, excessive, opener=opener)
        opener.open.assert_not_called()
        with self.assertRaisesRegex(APIError, "invalid_audio"):
            ogg_duration(head + page(bytes.fromhex("f8fffe"), 2, 0, granule=960) + page(bytes.fromhex("f8fffe"), 3, 4, granule=1))

    def test_missing_malformed_large_and_linked_key_files_are_rejected(self):
        for value in ("", "short", "key\nInjected-Header: x", "a" * 1025):
            self.path.write_text(value)
            with self.assertRaisesRegex(APIError, "key_unavailable"):
                read_key(self.path)
        self.path.unlink()
        with self.assertRaisesRegex(APIError, "key_unavailable"):
            read_key(self.path)
        target = self.path.with_name("other.key")
        target.write_text(self.key)
        try:
            self.path.symlink_to(target)
        except OSError:
            return
        with self.assertRaisesRegex(APIError, "key_unavailable"):
            read_key(self.path)

    @unittest.skipUnless(__import__('sys').platform == 'linux', 'POSIX owner permissions')
    def test_key_must_be_owner_only(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(APIError, "key_unavailable"):
            read_key(self.path)


class VoiceProcessTests(unittest.IsolatedAsyncioTestCase):
    def process(self, payload=None):
        process = MagicMock(returncode=0)
        process.stdin.drain = AsyncMock()
        process.stdout.readline = AsyncMock(return_value=json.dumps(payload or {"text":"hello", "engine":"openai", "model":MODEL, "duration_seconds":1}).encode()+b"\n")
        process.wait = AsyncMock()
        return process

    async def test_child_gets_key_path_and_audio_without_inheriting_secrets(self):
        process = self.process()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-parent-key", "HTTPS_PROXY": "https://invalid.test"}), \
                patch("marka.voice.asyncio.create_subprocess_exec", return_value=process) as spawn:
            result = await transcribe(Path('/state/openai-stt.key'), OGG, duration=1)
        args, kwargs = spawn.call_args
        self.assertEqual(args[-2:], ("--key-file", str(Path("/state/openai-stt.key"))))
        self.assertFalse({"OPENAI_API_KEY", "HTTPS_PROXY", "CODEX_HOME"} & set(kwargs["env"]))
        process.stdin.write.assert_called_once_with(OGG)
        self.assertEqual(result["trust"], "unverified_transcription")

    async def test_cancel_kills_http_process_and_reaps_it(self):
        process = self.process()
        process.returncode = None
        started = asyncio.Event()
        async def slow():
            started.set()
            await asyncio.Future()
        process.stdout.readline = slow
        with patch("marka.voice.asyncio.create_subprocess_exec", return_value=process):
            task = asyncio.create_task(transcribe(Path('/state/openai-stt.key'), OGG, duration=1))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_api_error_is_safe_user_message_and_not_accepted_text(self):
        with patch("marka.voice.asyncio.create_subprocess_exec", return_value=self.process({"error":"rate_limit"})):
            with self.assertRaisesRegex(VoiceError, "квоту и баланс API"):
                await transcribe(Path('/state/openai-stt.key'), OGG, duration=1)
