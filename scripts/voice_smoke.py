"""One real OpenAI STT request, followed by durable restart/dedupe checks.

Use synthetic speech containing Russian markers 42 and красный. Never use
personal audio or print credentials. Requires the explicitly provisioned key.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from marka.app import Application
from marka.config import Settings


async def check(key_file, source):
    audio = source.read_bytes()
    class QASettings(Settings):
        @property
        def voice_key_file(self):
            return key_file
    class Client:
        downloads = 0
        async def download_file(self, *args, **kwargs):
            self.downloads += 1
            return audio
    class Provider:
        calls = 0
        async def complete(self, prompt, schema):
            self.calls += 1
            assert ("42" in prompt or "сорок два" in prompt.casefold()) and "красный" in prompt.casefold()
            assert "НЕ дословная" in prompt
            return {"kind": "final", "tool": "", "arguments": "{}", "message": "Synthetic voice accepted",
                    "outcome": "completed", "lesson": ""}
    with tempfile.TemporaryDirectory() as temporary:
        settings = QASettings(Path(temporary), semantic_search=False)
        settings.prepare()
        client, provider = Client(), Provider()
        app = Application(settings, client=client, provider=provider)
        app.store.set_meta("owner_id", 17)
        update = {"update_id": 1, "message": {"message_id": 1, "from": {"id": 17, "is_bot": False},
                  "chat": {"id": 17, "type": "private"}, "voice": {"file_id": "synthetic", "file_unique_id": "synthetic",
                  "mime_type": "audio/ogg", "file_size": len(audio), "duration": 8}}}
        await app.ingest(update)
        app = Application(settings, client=client, provider=provider)
        await app.ingest(update)
        assert client.downloads == 1 and len(app.queue.list()) == 1
        job = app.queue.claim()
        started = time.monotonic()
        with patch.object(app.engine, "run", side_effect=RuntimeError("synthetic restart after receipt")):
            try:
                await app.run_job(job)
                raise AssertionError("voice did not reach committed transcript: " + app.queue.get(job["id"])["error"])
            except RuntimeError as exc:
                assert str(exc) == "synthetic restart after receipt"
        elapsed = time.monotonic() - started
        result = app.voices.for_job(job)["transcript"]
        words = result["text"].casefold()
        assert ("сорок два" in words or "42" in words) and "красный" in words, result["text"]
        assert result["sha256"] == hashlib.sha256(audio).hexdigest()
        assert result["engine"] == "openai" and result["model"] == "gpt-4o-transcribe"
        assert result["trust"] == "unverified_transcription"
        app = Application(settings, client=client, provider=provider)
        app.queue.recover()
        with patch("marka.app.transcribe", side_effect=AssertionError("duplicate paid API request")):
            await app.run_job(app.queue.claim())
        assert app.queue.get(job["id"])["state"] == "completed"
        assert provider.calls == 1 and not app.store.list_memories("accepted")
        event = next(row for row in app.store.history() if row["role"] == "user")
        assert event["meta"]["exact_owner_quote"] is False
        assert app.store.get_event(event["id"])["trust"] == "unverified_transcription"
        return {"ok": True, "checks": ["real_openai_russian_speech", "input_hash", "derived_trust",
                "gateway_restart", "deduplicated_download", "atomic_transcript_receipt", "restart_without_second_api_call",
                "queue_to_agent", "no_accepted_facts", "source_trust"], "transcript": result["text"],
                "sha256": result["sha256"], "audio_seconds": result["duration_seconds"],
                "recognition_seconds": round(elapsed, 3), "model": result["model"], "api_calls": 1,
                "provider": "openai", "mime": "audio/ogg",
                "telegram_network": False, "external_stt": True, "real_person_audio": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.key_file, args.fixture)), ensure_ascii=False))
