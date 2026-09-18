"""Archive and retrieval behavior, including additive upgrade/backup invariants."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
import tempfile
from pathlib import Path
import unittest

from marka import retrieval
from marka.store import Store


class TestRetrieval(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)
        self.store = Store(self.path / "memory.sqlite3")

    def remember(self, text, **kwargs):
        source = self.store.event("user", text)
        return self.store.remember(text, sources=[source], actor="owner", status="accepted", **kwargs)

    def test_russian_inflections_yo_unicode_and_aliases(self):
        memory = self.remember("Перед ошибками проверяй настройки серверов и отчётность Telegram")
        for query in ("ошибка сервера", "настройками сервера", "отчетность", "телеграм", "ТГ"):
            with self.subTest(query=query):
                hits = self.store.search(query)
                self.assertEqual(hits[0]["id"], memory)
                self.assertEqual(hits[0]["match"]["retrieval"], "lexical_normalized_alias")
        wb = self.remember("Поставка Wildberries подтверждена")
        self.assertEqual(self.store.search("вайдберриз"), [])  # no invented spell correction
        self.assertEqual(self.store.search("WB")[0]["id"], wb)
        self.assertEqual(self.store.search('" OR * NEAR( )'), [])
        self.assertEqual(retrieval.normalize("ОТЧЁТ"), "отчет")

    def test_specific_fact_outranks_generic_high_level_lesson(self):
        precise = self.remember("Сервер PostgreSQL слушает порт 5544", level=1)
        generic = self.remember("Перед работой проверь сервер и подумай о безопасности", kind="lesson", level=2)
        hits = self.store.search("PostgreSQL порт сервера")
        self.assertEqual(hits[0]["id"], precise)
        self.assertEqual(hits[1]["id"], generic)
        self.assertGreater(hits[0]["score"], hits[1]["score"])

    def test_long_source_returns_matching_tail_and_exact_pages(self):
        text = ("Предыдущая строка без нужного ответа. " * 700) + "\nРедкаяошибка: починить индекс ЖУРАВЛЬ.\nКонец."
        identifier = self.store.event("tool", text)
        hit = self.store.recall_events("ЖУРАВЛЬ", limit=1)[0]
        self.assertIn("ЖУРАВЛЬ", hit["content"])
        self.assertGreater(hit["offset"], 20000)
        self.assertEqual(hit["content"], text[hit["offset"]:hit["offset"] + 2000])
        self.assertEqual(hit["content_hash"], hashlib.sha256(text.encode()).hexdigest())
        pages = []
        offset = 0
        while offset is not None:
            page = self.store.get_event(identifier, offset=offset, limit=997)
            pages.append(page["content"])
            self.assertEqual(page["total_chars"], len(text))
            offset = page["next_offset"]
        self.assertEqual("".join(pages), text)

    def test_default_retention_keeps_full_archive_and_history_masks_tombstones(self):
        event = self.store.event("user", "Старый город: Москва")
        memory = self.store.remember("Москва", sources=[event], actor="owner", status="accepted", key="city")
        with self.store._connect() as db:
            db.execute("UPDATE events SET created_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(self.store.prune(), 0)
        self.assertEqual(self.store.prune(0), 0)
        newer = self.store.event("user", "Новый город: Казань")
        self.store.remember("Казань", sources=[newer], actor="owner", status="accepted", key="city")
        self.assertEqual([row["id"] for row in self.store.history()], [newer])
        self.assertIsNone(self.store.get_event(event))
        self.assertIsNone(self.store.get_memory(memory))
        self.assertTrue(self.store.get_event(event, include_inactive=True)["inactive"])
        self.assertEqual(self.store.get_memory(memory, include_inactive=True)["status"], "superseded")
        with self.assertRaises(ValueError):
            self.store.prune(-1)

    def test_exact_snapshot_paging_survives_source_edit_and_explicit_prune(self):
        source = self.store.event("user", "Источники должны оставаться точными. " * 250)
        memory = self.store.remember("Короткое обобщение", sources=[source])
        before = self.store.get_memory(memory, source_id=source)
        self.assertEqual(before["record_type"], "source_snapshot")
        self.assertEqual(before["next_offset"], 4000)
        with self.store._connect() as db:
            db.execute("UPDATE events SET content='Modified source',created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (source,))
        self.store.forget(memory)
        self.assertEqual(self.store.prune(1), 1)
        self.assertIsNone(self.store.get_memory(memory, source_id=source))
        after = self.store.get_memory(memory, source_id=source, include_inactive=True)
        self.assertEqual(after["content"], before["content"])
        self.assertEqual(after["content_hash"], before["content_hash"])
        self.assertIsNone(self.store.get_event(source, include_inactive=True))
        self.assertEqual(self.store.recall_events("Modified"), [])

    def test_candidate_cursor_does_not_skip_after_new_insert(self):
        event = self.store.event("user", "evidence")
        ids = [self.store.remember(f"Candidate {i}", sources=[event]) for i in range(7)]
        first = self.store.memory_page(limit=3)
        self.store.remember("New concurrent candidate", sources=[event])
        second = self.store.memory_page(limit=3, before_id=first["next_cursor"])
        third = self.store.memory_page(limit=3, before_id=second["next_cursor"])
        self.assertEqual([item["id"] for page in (first,second,third) for item in page["items"]], list(reversed(ids)))
        self.assertIsNone(third["next_cursor"])
        self.assertEqual(self.store.memory_page(limit=0), {"items": [], "next_cursor": None})

    def test_import_dedup_originals_low_trust_atomic_conflict_and_origin_immutability(self):
        original = self.store.event("user", "Current source must retain its ID")
        records = [dict(external_id=str(original), role="assistant", content="Historical interpretation of Graphiti",
                        created_at="2023-06-04T12:00:00Z", meta={"job": "not-a-runtime-job"})]
        self.assertEqual(self.store.import_events(records, "chatgpt-export"), {"imported": 1, "skipped": 0})
        self.assertEqual(self.store.import_events(records, "chatgpt-export"), {"imported": 0, "skipped": 1})
        hit = self.store.recall_events("Graphiti")[0]
        self.assertNotEqual(hit["id"], original)
        self.assertEqual(hit["trust"], "historical_unverified")
        self.assertNotIn("job", hit["meta"])
        self.assertEqual(self.store.get_event(hit["id"])["origin"]["external_id"], str(original))
        self.assertEqual(self.store.search("Graphiti"), [])
        self.assertEqual(self.store.history()[0]["id"], original)
        changed = {**records[0], "content": "Different historical claim"}
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.store.import_events([{**records[0], "external_id": "new-one"}, changed], "chatgpt-export")
        self.assertEqual(self.store.stats()["events"], 2)
        with self.store._connect() as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                db.execute("UPDATE event_origins SET original_role='user'")
        self.assertEqual(self.store.prune(30), 1)
        self.assertEqual(self.store.import_events(records, "chatgpt-export"), {"imported": 0, "skipped": 1})

    def test_import_validation_rolls_back_batch_and_numeric_timestamp(self):
        good = dict(id=123,role="user",content="old message",timestamp=1000000000)
        for bad in ({**good,"id":None}, {**good,"timestamp":float("nan")}, {**good,"content":"x"*40001}):
            with self.assertRaises(ValueError):
                self.store.import_events([good,bad], "archive")
            self.assertEqual(self.store.stats()["events"], 0)
        self.store.import_events([good], "archive")
        with self.store._connect() as db:
            self.assertEqual(db.execute("SELECT created_at FROM events").fetchone()[0], "2001-09-09T01:46:40.000000+00:00")

    def test_projection_updates_from_sql_and_concurrent_queries(self):
        event = self.store.event("user", "Сервис Graphiti работает", session="a")
        self.assertEqual(self.store.recall_events("Graphiti")[0]["id"], event)
        with self.store._connect() as db:
            db.execute("UPDATE events SET content='Теперь SQLite работает' WHERE id=?", (event,))
        self.assertEqual(self.store.recall_events("Graphiti"), [])
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(lambda _: self.store.recall_events("SQLite"), range(12)))
        self.assertTrue(all(row[0]["id"] == event for row in rows))
        projection = self.store.entity_links("SQLite")[0]
        self.assertEqual(projection["sources"][0]["id"], event)
        self.assertIn("not_asserted_fact", projection["trust"])

    def test_related_co_mentions_preserve_provenance_and_forgetting(self):
        first = self.store.event("user", "Проверь Graphiti", session="project:a")
        second = self.store.event("tool", "Graphiti: доступен", session="project:b")
        rows = self.store.related_events(first)
        self.assertEqual(rows[0]["id"], second)
        self.assertEqual(rows[0]["relationship"], "literal_entity_co_mention")
        self.assertEqual(rows[0]["related_to"], first)
        self.assertIn("content_hash", rows[0])
        memory = self.store.remember("Graphiti доступен", sources=[second])
        self.store.forget(memory)
        self.assertEqual(self.store.related_events(first), [])
        self.assertEqual([p["id"] for entity in self.store.entity_links("Graphiti") for p in entity["sources"]], [first])

    def test_migration_and_consistent_backup_preserve_ids_snapshots_and_new_indexes(self):
        source = self.store.event("user", "Исходный источник и настройки серверов")
        memory = self.store.remember("Настройки серверов", sources=[source], actor="owner", status="accepted")
        original_hash = self.store.get_memory(memory, source_id=source)["content_hash"]
        # Represent the old canonical schema by removing only new projections.
        with self.store._connect() as db:
            triggers = db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'retrieval_%'").fetchall()
            for trigger in triggers:
                db.execute('DROP TRIGGER "' + trigger[0] + '"')
            for table in ("retrieval_fts","retrieval_chunks","retrieval_mentions","retrieval_dirty"):
                db.execute('DROP TABLE ' + table)
            db.execute("DELETE FROM meta WHERE key='_retrieval_version'")
        upgraded = Store(self.store.path)
        self.assertEqual(upgraded.search("настройка сервера")[0]["id"], memory)
        self.assertEqual(upgraded.get_memory(memory, source_id=source)["content_hash"], original_hash)
        archived = Store(upgraded.backup(self.path / "snapshot.sqlite3"))
        self.assertEqual(archived.search("настройка сервера")[0]["id"], memory)
        self.assertEqual(archived.get_event(source)["content_hash"], upgraded.get_event(source)["content_hash"])
        self.assertEqual(archived.stats(), upgraded.stats())
        self.assertEqual(archived.get_memory(memory, source_id=source)["content_hash"], original_hash)

    def test_page_bounds_and_missing_ids(self):
        for args in ({"offset":-1},{"limit":0},{"limit":8001},{"offset":True}):
            with self.assertRaises(ValueError):
                self.store.get_event(999, **args)
        self.assertIsNone(self.store.get_event(999))
        self.assertIsNone(self.store.get_memory(999))
        memory = self.remember("Короткий факт")
        self.assertIsNone(self.store.get_memory(memory, source_id=999))
        page = self.store.get_memory(memory, offset=999)
        self.assertEqual(page["content"], "")
        self.assertIsNone(page["next_offset"])

    def test_derived_index_can_be_rebuilt_without_canonical_changes(self):
        memory = self.remember("Проверка настроек серверов")
        self.assertEqual(self.store.search("настройка")[0]["id"], memory)
        before = self.store.get_memory(memory)
        with self.store._connect() as db:
            db.execute("DROP TABLE retrieval_fts")
        rebuilt = Store(self.store.path)
        self.assertEqual(rebuilt.search("настройка")[0]["id"], memory)
        with rebuilt._connect() as db:
            db.execute("DROP TABLE retrieval_chunks")
        rebuilt = Store(self.store.path)
        self.assertEqual(rebuilt.search("настройка")[0]["id"], memory)
        self.assertEqual(rebuilt.get_memory(memory), before)


if __name__ == "__main__":
    unittest.main()
