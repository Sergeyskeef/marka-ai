"""Image inspection crosses the real engine budget and provider image boundary."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from marka.config import Settings
from marka.engine import CONSULT_SCHEMA, Engine
from marka.image_inspect import prepare_image
from marka.media import MAX_IMAGE_BYTES, MAX_OUTPUT_IMAGE_BYTES, image_inputs
from marka.queue import Queue
from marka.store import Store
from image_fixtures import png


def tool():
    return {"kind": "tool", "tool": "image.inspect", "arguments": json.dumps(
        {"path": "card.png", "question": "What is visible?"}),
        "message": "", "outcome": "completed", "lesson": ""}


def final():
    return {"kind": "final", "tool": "", "arguments": "{}", "message": "A red image.",
            "outcome": "completed", "lesson": ""}


class Provider:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def complete(self, prompt, schema, **kwargs):
        if "images" in kwargs:
            image_inputs(kwargs["images"])
        self.calls.append((prompt, schema, kwargs))
        if not self.answers:
            raise AssertionError("Unexpected provider call")
        return self.answers.pop(0)


class ImagePreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "card.png"

    def test_small_original_reaches_provider_unchanged_without_binary_receipt(self):
        data = png()
        self.path.write_bytes(data)
        prepared = prepare_image(self.path)
        self.assertEqual(prepared.image.data, data)
        self.assertFalse(prepared.receipt()["analysis_image"]["derived"])
        self.assertEqual(prepared.source.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(self.path.read_bytes(), data)
        serialized = json.dumps(prepared.receipt())
        self.assertNotIn("base64", serialized)
        self.assertNotIn("data", prepared.receipt()["source"])

    def test_large_png_gets_bounded_analysis_view_without_rewriting_original(self):
        output = io.BytesIO()
        with Image.new("RGBA", (1086, 1448), (220, 20, 20, 128)) as picture:
            picture.save(output, format="PNG", compress_level=0)
        data = output.getvalue()
        self.assertGreater(len(data), MAX_IMAGE_BYTES)
        self.assertLess(len(data), MAX_OUTPUT_IMAGE_BYTES)
        self.path.write_bytes(data)
        before = self.path.stat()
        prepared = prepare_image(self.path)
        self.assertLessEqual(len(prepared.image.data), MAX_IMAGE_BYTES)
        self.assertEqual(prepared.source.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(image_inputs([prepared.image]), (prepared.image,))
        self.assertTrue(prepared.receipt()["analysis_image"]["derived"])
        self.assertTrue(prepared.receipt()["analysis_image"]["lossy"])
        self.assertEqual(prepared.receipt()["analysis_image"]["alpha_background"], "white")
        self.assertEqual(self.path.read_bytes(), data)
        self.assertEqual(self.path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_oversize_file_and_pixel_bomb_rejected_before_pillow(self):
        for data in (b"x" * (MAX_OUTPUT_IMAGE_BYTES + 1), png(3000, 3000, raw=b"x")):
            self.path.write_bytes(data)
            with patch("marka.media.Image.open", side_effect=AssertionError("Unsafe decode")):
                with self.assertRaises(ValueError):
                    prepare_image(self.path)

    def test_corrupt_image_and_hardlink_are_rejected(self):
        self.path.write_bytes(png()[:-1])
        with self.assertRaises(ValueError):
            prepare_image(self.path)
        self.path.write_bytes(png())
        linked = self.path.with_name("alias.png")
        try:
            os.link(self.path, linked)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ValueError, "hard links"):
            prepare_image(self.path)


class ImageInspectionEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = Settings(Path(temporary.name), semantic_search=False, max_steps=6)
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)
        (self.settings.workspace / "card.png").write_bytes(png())

    def claimed(self, calls=10):
        identifier = self.queue.enqueue("Inspect the existing card image", 17)
        self.queue.configure_task(identifier, max_steps=6, max_model_calls=calls)
        return self.queue.claim()

    async def test_real_tool_loop_transports_image_charges_budget_and_keeps_receipt(self):
        provider = Provider(tool(), {"answer": "A red image", "uncertainty": "No text"}, final())
        engine = Engine(self.settings, self.store, self.queue, provider)
        job = self.claimed()
        await engine.run(job)
        self.assertEqual(self.queue.get(job["id"])["state"], "completed")
        self.assertEqual(self.store.budget_used(), 3)
        self.assertEqual(self.queue.progress(job["id"])["budget"]["used"], {"steps": 2, "model_calls": 3})
        self.assertIs(provider.calls[1][1], CONSULT_SCHEMA)
        self.assertEqual(provider.calls[1][2]["images"][0].data, png())
        self.assertNotIn("images", provider.calls[0][2])
        self.assertNotIn("images", provider.calls[2][2])
        observations = self.store.history("work:" + job["id"])
        result = json.loads(observations[0]["content"])["result"]
        self.assertEqual(result["source"]["path"], "card.png")
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(png()).hexdigest())
        self.assertNotIn("base64", observations[0]["content"])
        self.assertEqual((self.settings.workspace / "card.png").read_bytes(), png())

    async def test_task_limit_prevents_nested_image_call(self):
        provider = Provider(tool())
        engine = Engine(self.settings, self.store, self.queue, provider)
        job = self.claimed(calls=1)
        await engine.run(job)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(self.store.budget_used(), 1)
        self.assertEqual(self.queue.get(job["id"])["state"], "blocked")

    async def test_daily_limit_prevents_nested_image_call(self):
        self.settings.daily_calls = 1
        provider = Provider(tool())
        engine = Engine(self.settings, self.store, self.queue, provider)
        job = self.claimed()
        await engine.run(job)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(self.store.budget_used(), 1)
        self.assertEqual(self.queue.get(job["id"])["state"], "blocked")

    async def test_invalid_path_question_or_image_never_calls_provider(self):
        provider = Provider()
        engine = Engine(self.settings, self.store, self.queue, provider)
        (self.settings.workspace / "invalid.png").write_bytes(b"not an image")
        for path, question in (("../private.png", "Read"), ("card.png", ""), ("invalid.png", "Read")):
            with self.subTest(path=path, question=question), self.assertRaises(ValueError):
                await engine.inspect_image(path, question)
        self.assertEqual(provider.calls, [])
        self.assertEqual(self.store.budget_used(), 0)

    async def test_cancelled_task_cannot_make_an_image_model_call(self):
        provider = Provider()
        engine = Engine(self.settings, self.store, self.queue, provider)
        job = self.claimed()
        engine.active_job = job
        self.queue.cancel(job["id"])
        import asyncio
        with self.assertRaises(asyncio.CancelledError):
            await engine.inspect_image("card.png", "Read")
        self.assertEqual(provider.calls, [])
        self.assertEqual(self.store.budget_used(), 0)

    async def test_image_call_does_not_consume_persistent_consult_allowance_on_resume(self):
        self.settings.max_steps = 1
        first = Provider(tool(), {"answer": "Red", "uncertainty": "None"})
        job = self.claimed(calls=20)
        await Engine(self.settings, self.store, self.queue, first).run(job)
        self.assertEqual(self.queue.get(job["id"])["state"], "queued")
        self.assertEqual(self.store.get_meta("consultations:" + job["id"]), 0)

        def consultation(question):
            return {**tool(), "tool": "consult", "arguments": json.dumps(
                {"question": question, "role": "critic"})}

        self.settings.max_steps = 2
        second = Provider(consultation("First check"), {"answer": "One", "uncertainty": "None"},
                          consultation("Second check"), {"answer": "Two", "uncertainty": "None"})
        await Engine(self.settings, self.store, self.queue, second).run(self.queue.claim())
        self.assertEqual(self.queue.get(job["id"])["state"], "queued")
        self.assertEqual(len(second.calls), 4)
        self.assertEqual(self.store.get_meta("consultations:" + job["id"]), 2)

        third = Provider(consultation("Third is denied"), {**final(), "outcome": "blocked"})
        await Engine(self.settings, self.store, self.queue, third).run(self.queue.claim())
        self.assertEqual(len(third.calls), 2)
        self.assertTrue(all(schema is not CONSULT_SCHEMA for _, schema, _ in third.calls))
        observations = self.store.history("work:" + job["id"])
        self.assertIn("Maximum two consultations", observations[-1]["content"])
        self.assertEqual(self.store.get_meta("consultations:" + job["id"]), 2)

    async def test_legacy_resume_keeps_already_consumed_consult_allowance(self):
        job = self.claimed()
        for _ in range(2):
            self.assertTrue(self.queue.reserve_call(job["id"], job["lease"], step=False)["allowed"])
        consult = {**tool(), "tool": "consult", "arguments": json.dumps(
            {"question": "Legacy third call", "role": "critic"})}
        provider = Provider(consult, {**final(), "outcome": "blocked"})
        await Engine(self.settings, self.store, self.queue, provider).run(job)
        self.assertEqual(self.store.get_meta("consultations:" + job["id"]), 2)
        self.assertEqual(len(provider.calls), 2)
        self.assertTrue(all(schema is not CONSULT_SCHEMA for _, schema, _ in provider.calls))
