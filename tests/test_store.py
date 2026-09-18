"""Storage invariants: evidence, corrections, isolation, durability and budgets."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import sqlite3

import tempfile
from pathlib import Path
import unittest

from marka.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.store = Store(self.directory / "mark.sqlite3")


    def test_candidates_need_owner_and_real_source(self):
        store = self.store
        event = store.event("user", "Сергей предпочитает краткие ответы")
        candidate = store.remember("Краткие ответы", kind="preference", sources=[event])
        assert store.search("ответы") == []
        assert store.search("ответы", include_candidates=True)[0]["id"] == candidate
        with self.assertRaisesRegex(ValueError, "owner"):
            store.remember("Модель согласилась сама", status="accepted", sources=[event])
        with self.assertRaisesRegex(ValueError, "source"):
            store.remember("Неподтвержденный факт", sources=[99999])
        assert store.stats()["memories"] == 1
        accepted = store.accept(candidate)
        assert accepted["status"] == "accepted"
        assert store.search("ответы")[0]["id"] == candidate


    def test_source_hash_snapshots_and_redaction(self):
        store = self.store
        event = store.event("user", "Original direct evidence", meta={"source": "owner"})
        memory = store.remember("Derived fact", sources=[event, event])
        result = store.list_memories()[0]
        assert result["id"] == memory
        assert result["sources"] == [event]
        snapshot = result["source_snapshots"][0]
        assert snapshot["content_hash"] == hashlib.sha256(b"Original direct evidence").hexdigest()
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("UPDATE events SET content='later edit' WHERE id=?", (event,))
        assert store.list_memories()[0]["source_snapshots"][0]["content"] == "Original direct evidence"


    def test_correction_supersedes_only_after_acceptance_and_never_resurrects(self):
        store = self.store
        first = store.event("user", "Город: Москва")
        old = store.remember("Живу: Москва", sources=[first], key="owner.city", actor="owner", status="accepted")
        second = store.event("user", "Переехал, теперь город: Казань")
        new = store.remember("Живу: Казань", sources=[second], key="owner.city")
        assert store.search("Живу")[0]["id"] == old
        store.accept(new)
        assert [item["id"] for item in store.search("Живу")] == [new]
        assert store.list_memories("superseded")[0]["superseded_by"] == new
        assert store.forget(new)
        assert not store.forget(new)
        assert store.search("Живу", include_candidates=True) == []
        with self.assertRaisesRegex(ValueError, "active candidate"):
            store.accept(old)
        with self.assertRaisesRegex(ValueError, "active candidate"):
            store.accept(new)


    def test_layers_unicode_fts_and_immutable_identity(self):
        store = self.store
        event = store.event("user", "Сначала проверяй существующую систему")
        ids = [store.remember("Проверяй систему", level=level, kind="lesson", sources=[event],
                              status="accepted", actor="owner") for level in range(3)]
        assert [item["id"] for item in store.search("систему")] == list(reversed(ids))
        assert len(store.search("систему", limit=1)) == 1
        assert len(store.search("")) == 3
        assert store.search('" OR * (') == []
        with self.assertRaisesRegex(ValueError, "immutable"):
            store.remember("Перепиши личность", level=3, sources=[event], actor="owner")


    def test_history_session_order_metadata_and_reopen(self):
        store = self.store
        store.event("user", "first", session="a", meta={"telegram_id": 123})
        store.event("user", "private other chat", session="b")
        store.event("assistant", "second", session="a")
        store.set_meta("offset", {"id": 15})
        reopened = Store(store.path)
        assert [item["content"] for item in reopened.history("a")] == ["first", "second"]
        assert reopened.history("a")[0]["meta"] == {"telegram_id": 123}
        assert reopened.history("a", 1)[0]["content"] == "second"
        assert reopened.get_meta("offset") == {"id": 15}
        assert reopened.get_meta("missing", "fallback") == "fallback"


    def test_budget_is_atomic_persistent_and_daily(self):
        store = self.store
        with ThreadPoolExecutor(max_workers=8) as pool:
            claimed = list(pool.map(lambda _: store.claim_budget(7, "2026-09-18"), range(30)))
        assert sum(claimed) == 7
        reopened = Store(store.path)
        assert reopened.budget_used("2026-09-18") == 7
        assert not reopened.claim_budget(7, "2026-09-18")
        assert reopened.claim_budget(7, "2026-09-19")
        assert reopened.budget_used("2026-09-19") == 1
        assert not reopened.claim_budget(0, "2026-09-19")


    def test_concurrent_corrections_keep_one_current_value(self):
        store = self.store
        event = store.event("user", "verified source")
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(lambda n: store.remember(f"Version {n}", sources=[event],
                            key="version", status="accepted", actor="owner"), range(12)))
        current = store.list_memories("accepted")
        assert len(current) == 1
        assert current[0]["id"] in ids
        assert store.stats()["by_status"]["superseded"] == 11


    def test_prune_preserves_active_evidence_backup_is_consistent(self):
        store, tmp_path = self.store, self.directory
        kept = store.event("user", "Keep source")
        store.event("assistant", "Old unreferenced conversation")
        memory = store.remember("Remember source", sources=[kept], actor="owner", status="accepted")
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("UPDATE events SET created_at='2001-01-01T00:00:00+00:00'")
        assert store.prune(90) == 1
        assert store.history()[0]["id"] == kept
        destination = store.backup(tmp_path / "backup.sqlite3")
        backup = Store(destination)
        assert backup.search("source")[0]["id"] == memory
        assert backup.stats() == store.stats()
        store.forget(memory)
        assert store.prune(90) == 1
        assert store.list_memories("forgotten")[0]["source_snapshots"][0]["content"] == "Keep source"
        with self.assertRaises(ValueError):
            store.backup(store.path)

    def test_episode_recall_survives_restart_and_attaches_observed_failure(self):
        requested = self.store.event("user", "Проверь загрузку Wildberries", meta={"job": "job-42"})
        failed = self.store.event("system", "TimeoutError: поставщик не ответил", session="work:job-42",
                                  meta={"outcome": "failed"})
        reopened = Store(self.store.path)
        episodes = reopened.recall_events("Wildberries", limit=4)
        self.assertEqual([item["id"] for item in episodes], [requested, failed])
        self.assertEqual(episodes[1]["meta"]["outcome"], "failed")
        self.assertTrue(all(item["trust"] == "observed_episode_not_accepted_knowledge" for item in episodes))
        self.assertEqual(reopened.search("Wildberries"), [])

    def test_episode_recall_excludes_forgotten_and_superseded_sources(self):
        original = self.store.event("user", "Адрес сервиса: old.example")
        previous = self.store.remember("Адрес: old.example", sources=[original], key="endpoint",
                                       actor="owner", status="accepted")
        updated = self.store.event("user", "Адрес сервиса: new.example")
        latest = self.store.remember("Адрес: new.example", sources=[updated], key="endpoint",
                                     actor="owner", status="accepted")
        self.assertEqual(self.store.list_memories("superseded")[0]["id"], previous)
        self.assertEqual([item["id"] for item in self.store.recall_events("Адрес")], [updated])
        self.store.forget(latest)
        self.assertEqual(self.store.recall_events("Адрес"), [])

    def test_episode_bounds_pruning_and_fts_rebuild(self):
        event = self.store.event("tool", "large observation " + "a" * 2500, session="work:1")
        result = self.store.recall_events("observation", limit=1)[0]
        self.assertEqual(result["id"], event)
        self.assertEqual(len(result["content"]), 2000)
        self.assertTrue(result["truncated"])
        self.assertEqual(self.store.recall_events("observation", limit=0), [])
        with self.store._connect() as db:
            db.execute("DROP TABLE events_fts")
        rebuilt = Store(self.store.path)
        self.assertEqual(rebuilt.recall_events("observation")[0]["id"], event)
        with rebuilt._connect() as db:
            db.execute("UPDATE events SET created_at='2000-01-01T00:00:00+00:00'")
        self.assertEqual(rebuilt.prune(90), 1)
        self.assertEqual(rebuilt.recall_events("observation"), [])
        replacement = rebuilt.event("user", "new unique event")
        self.assertGreater(replacement, event)
        self.assertEqual(rebuilt.recall_events("observation"), [])
        self.assertEqual(rebuilt.recall_events("unique")[0]["id"], replacement)

    def test_persisted_content_limits_are_explicit(self):
        with self.assertRaisesRegex(ValueError, "40000"):
            self.store.event("user", "x" * 40001)
        source = self.store.event("user", "source")
        with self.assertRaisesRegex(ValueError, "6000"):
            self.store.remember("x" * 6001, sources=[source])
