"""Synthetic legacy data must not expose credentials through model context."""

from __future__ import annotations

import copy
import asyncio
import json
from pathlib import Path
import re
import tempfile
import unittest

from marka.config import Settings
from marka.engine import CONSULT_SCHEMA, Engine
from marka.queue import Queue
from marka.redact import redact
from marka.store import Store


# Synthetic, never sourced from a credential store or a live connection.
TOKEN = "1234567890:" + "SyntheticCanary_" + "x" * 19
MASK = "[REDACTED_TELEGRAM_TOKEN]"


class TelegramBoundaryTests(unittest.TestCase):
    def test_letters_and_literal_escaped_newlines_do_not_bypass_redaction(self):
        self.assertEqual(len(TOKEN.split(":")[1]), 35)
        old_pattern = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b")
        for prefix in ("a", "текст", "\\n", "\\r\\n", "_", " "):
            with self.subTest(prefix=prefix):
                if prefix != " ":
                    self.assertIsNone(old_pattern.search(prefix + TOKEN))
                self.assertEqual(redact(prefix + TOKEN), prefix + MASK)

    def test_trimmed_retrieval_prefixes_are_also_masked(self):
        for omitted_digits in (0, 1, 2, 4):
            with self.subTest(omitted_digits=omitted_digits):
                self.assertEqual(redact(TOKEN[omitted_digits:]), MASK)

    def test_numeric_prefix_limits_are_preserved(self):
        suffix = TOKEN.split(":")[1]
        for count in (6, 10, 12):
            self.assertEqual(redact("a" + "1" * count + ":" + suffix), "a" + MASK)
        for count in (5, 13, 20):
            candidate = "a" + "1" * count + ":" + suffix
            self.assertEqual(redact(candidate), candidate)
        short_suffix = "1234567890:" + "x" * 24
        self.assertEqual(redact(short_suffix), short_suffix)


class LegacyContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name) / "state")
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)
        self.engine = Engine(self.settings, self.store, self.queue, provider=None)

    def canonical_rows(self):
        with self.store._connect() as db:
            return {
                table: [tuple(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY 1")]
                for table in ("events", "memories", "memory_sources")
            }

    def seed_legacy_event_and_memory(self):
        # Direct fixture insertion models an old canonical row. The current
        # Store ingestion path correctly redacts it and cannot produce this.
        content = "legacytopic provenance\\n" + TOKEN
        with self.store._connect() as db:
            event_id = db.execute(
                "INSERT INTO events(role,content,session,created_at,meta) VALUES(?,?,?,?,?)",
                ("user", content, "main", "2026-01-01T00:00:00+00:00", "{}"),
            ).lastrowid
        memory_id = self.store.remember("legacytopic fact", sources=[event_id], status="accepted", actor="owner")
        with self.store._connect() as db:
            db.execute("UPDATE memories SET content=? WHERE id=?", ("legacytopic notea" + TOKEN, memory_id))
        return content

    def test_real_legacy_sqlite_history_and_retrieval_are_masked_without_rewriting_sources(self):
        legacy = self.seed_legacy_event_and_memory()
        self.assertIn(TOKEN, self.store.history()[0]["content"])
        episodes = self.store.recall_events("legacytopic", limit=4)
        self.assertTrue(any(TOKEN in item["match"]["excerpt"] for item in episodes))
        self.queue.enqueue("legacytopic", 17)
        job = self.queue.claim()
        before = self.canonical_rows()

        prompt = self.engine.prompt(job, [])
        context = json.loads(prompt.split("\nCONTEXT_DATA:\n", 1)[1])

        self.assertNotIn(TOKEN, prompt)
        self.assertNotIn(TOKEN.split(":")[1], prompt)
        self.assertIn(MASK, context["recent_dialogue"][0]["content"])
        self.assertTrue(any(MASK in item["content"] for item in context["relevant_memories"]))
        self.assertTrue(any(MASK in item["match"]["excerpt"] for item in context["related_experience"]))
        self.assertEqual(self.canonical_rows(), before)
        self.assertEqual(self.store.history()[0]["content"], legacy)

    def test_nested_owner_request_trace_and_recalled_excerpts_are_masked_without_input_mutation(self):
        self.queue.enqueue("legacytopic", 17)
        job = self.queue.claim()
        job["prompt"] = "legacytopic owner\\n" + TOKEN
        trace = [{"kind": "observation", "content": json.dumps({
            "result": {"match": {"excerpt": "a" + TOKEN}, "history": ["\\n" + TOKEN]},
        })}]
        self.engine.recalled = {"job": job["id"], "memories": [], "episodes": [{
            "match": {"excerpt": TOKEN[2:]}, "nested": [{"history": "prefix" + TOKEN}],
            "api_key": {"nested_value": "sensitive-structured-canary"},
        }]}
        before = copy.deepcopy((job, trace, self.engine.recalled))

        prompt = self.engine.prompt(job, trace)
        context = json.loads(prompt.split("\nCONTEXT_DATA:\n", 1)[1])
        observation = json.loads(context["current_work_log"][0]["content"])

        self.assertNotIn(TOKEN, prompt)
        self.assertNotIn(TOKEN.split(":")[1], prompt)
        self.assertIn(MASK, context["owner_request"])
        self.assertEqual(context["related_experience"][0]["match"]["excerpt"], MASK)
        self.assertIn(MASK, observation["result"]["match"]["excerpt"])
        self.assertIn(MASK, observation["result"]["history"][0])
        self.assertEqual(context["related_experience"][0]["api_key"], "[REDACTED]")
        self.assertNotIn("sensitive-structured-canary", prompt)
        self.assertEqual((job, trace, self.engine.recalled), before)

    def test_complete_and_consult_provider_boundary_masks_legacy_text(self):
        calls = []

        class CapturingProvider:
            async def complete(self, prompt, schema, **kwargs):
                calls.append((prompt, schema))
                return {"answer": "synthetic result", "uncertainty": "fixture"}

        self.engine.provider = CapturingProvider()
        self.seed_legacy_event_and_memory()
        before = self.canonical_rows()

        async def exercise():
            await self.engine.consult("question\\n" + TOKEN, "critic")
            # app.Reflection dispatches through complete(task=False), rather
            # than the normal Engine.prompt context builder.
            await self.engine.complete(json.dumps({"cases": [{
                "prompt": "legacy\\n" + TOKEN,
                "observations": [{"content": "a" + TOKEN}],
            }]}), CONSULT_SCHEMA, task=False)

        asyncio.run(exercise())
        self.assertEqual(len(calls), 2)
        for prompt, schema in calls:
            self.assertNotIn(TOKEN, prompt)
            self.assertNotIn(TOKEN.split(":")[1], prompt)
            self.assertIn(MASK, prompt)
            self.assertIs(schema, CONSULT_SCHEMA)
        consult_data = json.loads(calls[0][0].rsplit("\n", 1)[1])
        self.assertEqual(consult_data["question"], "question\\n" + MASK)
        reflection_data = json.loads(calls[1][0])
        self.assertEqual(reflection_data["cases"][0]["observations"][0]["content"], "a" + MASK)
        self.assertEqual(self.canonical_rows(), before)


if __name__ == "__main__":
    unittest.main()
