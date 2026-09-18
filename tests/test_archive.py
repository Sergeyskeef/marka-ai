import json
from pathlib import Path
import tempfile
import unittest

from marka.archive import import_archive
from marka.store import Store


class ArchiveTests(unittest.TestCase):
    def test_private_history_preserves_roles_sources_dedup_without_promoting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "state.db")
            source = root / "history.jsonl"
            source.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in [
                {"id": "u1", "role": "user", "text": "Хочу агента с памятью", "created_at": 1700000000, "meta": {"conversation_id": "original"}},
                {"id": "a1", "role": "assistant", "text": "Старая непроверенная идея", "created_at": 1700000001},
            ]), "utf-8")
            self.assertEqual(import_archive(store, source, "archive-test")["imported"], 2)
            self.assertEqual(import_archive(store, source, "archive-test")["skipped"], 2)
            self.assertEqual(store.stats()["memories"], 0)
            self.assertEqual(store.stats()["events"], 2)
            self.assertEqual(store.get_event(2)["role"], "assistant")

    def test_long_event_is_chunked_and_secret_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "state.db")
            path = root / "archive.jsonl"
            path.write_text(json.dumps({"id": "long", "role": "user", "content": "x"*31000 + " password=fake_value", "created_at": "2025-01-01T00:00:00+00:00"}), "utf-8")
            self.assertEqual(import_archive(store, path, "fixture")["imported"], 2)
            self.assertNotIn("fake_value", store.get_event(2)["content"])
            self.assertEqual(store.stats()["memories"], 0)
