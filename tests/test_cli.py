import json
from pathlib import Path
import tempfile
import unittest

from marka.cli import import_memory
from marka.config import Settings
from marka.store import Store


class PrivateImportTests(unittest.TestCase):
    def test_import_defaults_to_candidates_and_explicit_accept_has_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "state")
            settings.prepare()
            source = Path(directory) / "personal.json"
            source.write_text(json.dumps([{"content": "Keep responses concise", "kind": "preference"}]), "utf-8")
            self.assertEqual(import_memory(settings, source), 1)
            store = Store(settings.database)
            self.assertEqual(store.search("concise"), [])
            self.assertEqual(import_memory(settings, source, accept=True), 1)
            entry = store.search("concise")[0]
            self.assertEqual(entry["actor"], "owner")
            self.assertEqual(entry["source_snapshots"][0]["role"], "user")

    def test_invalid_later_record_does_not_partially_import(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "state")
            settings.prepare()
            source = Path(directory) / "personal.json"
            source.write_text(json.dumps([{"content": "First"}, {"content": "Second", "key": []}]), "utf-8")
            with self.assertRaises(ValueError):
                import_memory(settings, source)
            self.assertEqual(Store(settings.database).stats()["memories"], 0)

    def test_settings_persist_without_entering_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), token="test-only-value", model="explicit-model")
            settings.save()
            restored = Settings.load(directory)
            self.assertEqual(restored.model, "explicit-model")
            self.assertFalse((settings.workspace / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
