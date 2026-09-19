"""Freshness never grants authority or destroys the evidence it describes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from marka.memory_context import MemoryContext
from marka.store import Store


NOW = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)


class TestMemoryContext(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "memory.sqlite3")
        self.context = MemoryContext(self.store)
        self.source = self.store.event("user", "Server has five gigabytes free")
        self.memory = self.store.remember("Server disk has five gigabytes free", sources=[self.source])

    def owner_command(self, memory=None, *, role="user", imported=False):
        target = memory or self.memory
        event = self.store.event(role, f'/annotate {target} {{"label":"decision"}}',
                                 meta={"command": "/annotate", "telegram_update": 551, "imported": imported})
        self.store.set_meta("command-source:551", {"source_id": event, "job_id": None})
        return event

    def test_model_decision_and_verification_remain_proposals(self):
        before = self.store.get_memory(self.memory)
        result = self.context.annotate(self.memory, label="decision", last_verified="2026-09-19T10:00:00Z", now=NOW)
        self.assertEqual(result["annotation_status"], "proposed")
        self.assertEqual(result["verification_state"], "model_proposal_not_verification")
        self.assertEqual(self.store.get_memory(self.memory), before)
        self.assertEqual(self.store.search("Server"), [])

    def test_owner_annotation_still_cannot_accept_a_candidate(self):
        source = self.owner_command()
        result = self.context.annotate(self.memory, label="decision", actor="owner", owner_event_id=source,
                                       last_verified="2026-09-19T10:00:00Z", now=NOW)
        self.assertEqual(result["annotation_status"], "owner_confirmed")
        self.assertEqual(result["verification_state"], "unverified")
        self.assertEqual(self.store.get_memory(self.memory)["status"], "candidate")
        self.store.accept(self.memory)
        enriched = self.context.enrich(self.store.get_memory(self.memory), now=NOW)
        self.assertEqual(enriched["memory_context"]["verification_state"], "owner_reported_verification")

    def test_expired_memory_retains_content_sources_and_search_visibility(self):
        self.store.accept(self.memory)
        self.context.annotate(self.memory, label="dated_observation", valid_until="2026-09-19T12:00:00Z", now=NOW)
        original = self.store.search("Server")
        enriched = self.context.enrich_many(original, now=NOW)
        self.assertEqual(len(enriched), 1)
        self.assertTrue(enriched[0]["memory_context"]["needs_recheck"])
        self.assertIn("validity_expired", enriched[0]["memory_context"]["reasons"])
        for key, value in original[0].items():
            self.assertEqual(enriched[0][key], value)
        self.assertNotIn("memory_context", original[0])

    def test_model_cannot_refresh_owner_confirmed_expiry(self):
        self.store.accept(self.memory)
        self.context.annotate(self.memory, label="dated_observation", actor="owner",
                              owner_event_id=self.owner_command(), valid_until="2026-09-18T12:00:00Z", now=NOW)
        self.context.annotate(self.memory, label="fact", last_verified="2026-09-19T11:00:00Z",
                              valid_until="2027-09-18T12:00:00Z", now=NOW)
        result = self.context.enrich(self.store.get_memory(self.memory), now=NOW)["memory_context"]
        self.assertEqual(result["annotation_status"], "owner_confirmed")
        self.assertEqual(result["label"], "dated_observation")
        self.assertTrue(result["needs_recheck"])
        self.assertEqual(result["proposed_annotation"]["annotation_status"], "proposed")

    def test_dates_use_explicit_utc_and_validate_order_and_future_verification(self):
        for value in ("2026-09-19", "2026-09-19T10:00:00", "2026-09-19T10:00:00+03:00",
                      "2026-02-30T10:00:00Z", "1969-01-01T00:00:00Z", True, 1, "x" * 1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.context.annotate(self.memory, label="fact", review_after=value, now=NOW)
        with self.assertRaisesRegex(ValueError, "future"):
            self.context.annotate(self.memory, label="fact", last_verified="2026-09-19T12:00:01Z", now=NOW)
        with self.assertRaisesRegex(ValueError, "after valid_from"):
            self.context.annotate(self.memory, label="fact", valid_from="2026-09-19T11:00:00Z",
                                  valid_until="2026-09-19T10:00:00Z", now=NOW)
        with self.assertRaisesRegex(ValueError, "precede"):
            self.context.annotate(self.memory, label="fact", last_verified="2026-09-19T11:00:00Z",
                                  review_after="2026-09-19T10:00:00Z", now=NOW)
        value = self.context.annotate(self.memory, label="fact", last_verified="2026-09-19T10:00:00+00:00", now=NOW)
        self.assertEqual(value["last_verified"], "2026-09-19T10:00:00.000000Z")

    def test_future_window_and_due_review_are_marked_not_filtered(self):
        value = self.context.annotate(self.memory, label="hypothesis", valid_from="2026-10-01T00:00:00Z",
                                      review_after="2026-09-19T12:00:00Z", now=NOW)
        self.assertTrue(value["needs_recheck"])
        self.assertEqual(value["reasons"], ["not_yet_valid", "review_due"])

    def test_clock_rollback_does_not_claim_future_verification_is_current(self):
        self.store.accept(self.memory)
        self.context.annotate(self.memory, label="fact", actor="owner", owner_event_id=self.owner_command(),
                              last_verified="2026-09-19T11:00:00Z", now=NOW)
        earlier = datetime(2026, 9, 19, 10, tzinfo=timezone.utc)
        value = self.context.enrich(self.store.get_memory(self.memory), now=earlier)["memory_context"]
        self.assertTrue(value["needs_recheck"])
        self.assertEqual(value["verification_state"], "unverified")
        self.assertIn("verification_in_future", value["reasons"])

    def test_owner_confirmation_requires_current_bound_user_command(self):
        for role, imported in (("assistant", False), ("user", True)):
            source = self.owner_command(role=role, imported=imported)
            with self.assertRaises(ValueError):
                self.context.annotate(self.memory, label="decision", actor="owner", owner_event_id=source, now=NOW)
        source = self.owner_command()
        self.store.set_meta("command-source:551", {"source_id": source + 1})
        with self.assertRaises(ValueError):
            self.context.annotate(self.memory, label="decision", actor="owner", owner_event_id=source, now=NOW)
        with self.assertRaises(ValueError):
            self.context.annotate(self.memory, label="decision", owner_event_id=source, now=NOW)
        wrong = self.owner_command(memory=self.memory + 1)
        with self.assertRaises(ValueError):
            self.context.annotate(self.memory, label="decision", actor="owner", owner_event_id=wrong, now=NOW)

    def test_owner_decision_requires_user_evidence_not_only_model_statement(self):
        source = self.store.event("assistant", "I assume the owner decided this")
        memory = self.store.remember("Decision", sources=[source])
        with self.assertRaisesRegex(ValueError, "user evidence"):
            self.context.annotate(memory, label="decision", actor="owner", owner_event_id=self.owner_command(memory), now=NOW)

    def test_sources_are_real_and_immutable_memory_snapshot_has_priority(self):
        with self.store._connect() as db:
            db.execute("UPDATE events SET content='later edit' WHERE id=?", (self.source,))
        value = self.context.annotate(self.memory, label="dated_observation", now=NOW)
        self.assertEqual(value["sources"][0]["content_hash"], hashlib.sha256(b"Server has five gigabytes free").hexdigest())
        for ids in ([99999], [True], [], list(range(1, 18))):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.context.annotate(self.memory, label="fact", source_ids=ids, now=NOW)
        recent = self.store.event("tool", "A fresh read reports 4.5 GB")
        value = self.context.annotate(self.memory, label="dated_observation", source_ids=[recent], now=NOW)
        self.assertEqual(value["sources"][0]["role"], "tool")
        self.assertEqual(self.store.get_memory(self.memory)["sources"], [self.source])

    def test_keyed_supersession_and_forgotten_memory_are_not_resurrected(self):
        older = self.store.remember("Old server fact", sources=[self.source], key="disk", actor="owner", status="accepted")
        self.context.annotate(older, label="dated_observation", now=NOW)
        newer = self.store.remember("New server fact", sources=[self.source], key="disk", actor="owner", status="accepted")
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.context.annotate(older, label="fact", now=NOW)
        self.assertEqual([row["id"] for row in self.context.enrich_many(self.store.search("server"), now=NOW)], [newer])
        audit = self.context.enrich(self.store.get_memory(older, include_inactive=True), now=NOW)
        self.assertEqual(audit["status"], "superseded")
        self.assertEqual(audit["superseded_by"], newer)
        self.store.forget(newer)
        self.assertEqual(self.context.enrich_many(self.store.search("server"), now=NOW), [])

    def test_persistence_and_backup_without_schema_changes(self):
        with self.store._connect() as db:
            schema_before = [tuple(row) for row in db.execute("SELECT name,sql FROM sqlite_master ORDER BY name")]
        self.context.annotate(self.memory, label="hypothesis", review_after="2026-10-01T00:00:00Z", now=NOW)
        backup = Store(self.store.backup(self.store.path.parent / "backup.sqlite3"))
        result = MemoryContext(backup).enrich(backup.get_memory(self.memory), now=NOW)
        self.assertEqual(result["memory_context"]["label"], "hypothesis")
        with self.store._connect() as db:
            self.assertEqual([tuple(row) for row in db.execute("SELECT name,sql FROM sqlite_master ORDER BY name")], schema_before)

    def test_unannotated_memory_and_colliding_event_ids_keep_original_meaning(self):
        original = self.store.get_memory(self.memory)
        result = self.context.enrich(original, now=NOW)
        self.assertEqual(result["memory_context"]["annotation_status"], "unannotated")
        self.assertEqual(result["memory_context"]["temporal_status"], "unspecified")
        event = self.store.get_event(self.source)
        self.assertEqual(self.context.enrich(event, now=NOW), event)
        self.assertIsNone(self.context.enrich(None))

    def test_invalid_saved_metadata_marks_recheck_without_hiding_source(self):
        for corrupted in ({"version": 99}, {"version": 1, "proposed": {"annotation_status": "owner_confirmed"}}, []):
            self.store.set_meta(f"memory-context:v1:{self.memory}", corrupted)
            result = self.context.enrich(self.store.get_memory(self.memory), now=NOW)
            self.assertTrue(result["memory_context"]["needs_recheck"])
            self.assertEqual(result["content"], "Server disk has five gigabytes free")
            self.assertEqual(result["sources"], [self.source])


if __name__ == "__main__":
    unittest.main()
