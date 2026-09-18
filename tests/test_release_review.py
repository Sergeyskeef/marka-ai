"""Release regressions found during independent integration review."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.cli import doctor, import_memory
from marka.config import Settings
from marka.store import Store
from marka.telegram import TelegramError


class ImportReviewTests(unittest.TestCase):
    def test_invalid_later_import_record_cannot_partially_import_earlier_rows(self):
        for invalid in [{"content": "   "}, {"content": "invalid bool level", "level": True},
                        {"content": "bad source", "source": ["not", "text"]},
                        {"content": "bad source", "source": "x" * 2001},
                        {"content": "invalid Unicode \ud800"}, {"content": "bad kind", "kind": []}]:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as folder:
                settings = Settings(Path(folder) / "state")
                settings.prepare()
                source = Path(folder) / "import.json"
                source.write_text(json.dumps([{"content": "valid first row"}, invalid]), encoding="utf-8")
                with self.assertRaises(ValueError):
                    import_memory(settings, source)
                store = Store(settings.database)
                self.assertEqual(store.stats()["events"], 0, "Validate all rows before persisting the first source event")
                self.assertEqual(store.stats()["memories"], 0)

    def test_import_preserves_bounded_owner_source_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder) / "state")
            settings.prepare()
            source = Path(folder) / "private-context.json"
            reference = "owner-message-id:" + "x" * 700
            source.write_text(json.dumps([{"content": "Verified owner preference", "source": reference}]), "utf-8")
            self.assertEqual(import_memory(settings, source, accept=True), 1)
            event = Store(settings.database).history("import")[0]
            self.assertEqual(event["meta"]["source"], reference[:512])
            self.assertEqual(event["meta"]["import_file"], source.name)
            self.assertTrue(event["meta"]["owner_reviewed"])


class DoctorReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_polling_transport_and_codex_report_ready(self):
        class Provider:
            async def status(self):
                return {"authenticated": True}

            async def complete(self, prompt, schema):
                return {"reply": "MARKA_OK"}

        class ReadyTelegram:
            def __init__(self, token):
                pass

            async def get_me(self):
                return {"id": 123, "username": "fake_bot"}

            async def call(self, method, payload):
                return {"url": ""}

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder), token="123456:" + "fake-token-for-test-only-12345")
            settings.prepare()
            output = io.StringIO()
            with patch("marka.cli.provider", return_value=Provider()), patch("marka.cli.TelegramClient", ReadyTelegram), redirect_stdout(output):
                result = await doctor(settings, live=True)
            self.assertTrue(result)
            self.assertTrue(json.loads(output.getvalue())["ready"])
            self.assertEqual(Store(settings.database).stats()["budget_used"], 1)

    async def test_missing_telegram_token_is_not_full_readiness(self):
        class Provider:
            async def status(self):
                return {"authenticated": True}

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder))
            settings.prepare()
            output = io.StringIO()
            with patch("marka.cli.provider", return_value=Provider()), redirect_stdout(output):
                result = await doctor(settings)
            self.assertFalse(result)
            self.assertFalse(json.loads(output.getvalue())["ready"])

    async def test_configured_telegram_failures_make_doctor_fail(self):
        class Provider:
            async def status(self):
                return {"authenticated": True}

        class BrokenTelegram:
            def __init__(self, token):
                pass

            async def get_me(self):
                raise TelegramError("Authentication failed", code=401, permanent=True)

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder), token="123456:" + "fake-token-for-test-only-12345")
            settings.prepare()
            with patch("marka.cli.provider", return_value=Provider()), patch("marka.cli.TelegramClient", BrokenTelegram), redirect_stdout(io.StringIO()):
                result = await doctor(settings)
            self.assertFalse(result, "Doctor must not report success when the configured Telegram transport cannot start")

    async def test_active_webhook_makes_polling_doctor_fail(self):
        class Provider:
            async def status(self):
                return {"authenticated": True}

        class WebhookTelegram:
            def __init__(self, token):
                pass

            async def get_me(self):
                return {"id": 123, "username": "fake_bot"}

            async def call(self, method, payload):
                return {"url": "https://example.invalid/active-hook"}

        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(Path(folder), token="123456:" + "fake-token-for-test-only-12345")
            settings.prepare()
            with patch("marka.cli.provider", return_value=Provider()), patch("marka.cli.TelegramClient", WebhookTelegram), redirect_stdout(io.StringIO()):
                result = await doctor(settings)
            self.assertFalse(result, "An active webhook prevents this polling gateway from starting")
