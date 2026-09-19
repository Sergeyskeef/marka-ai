"""Semantic cache correctness uses a fake encoder, never a model download."""
import hashlib
import json
import math
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from marka.semantic import DIMENSION, ORT_VERSION, SemanticIndex, hybrid, install_model
from marka.store import Store


class FakeEncoder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        result = []
        for text in texts:
            vector = [0.0] * DIMENSION
            text = text.lower()
            if "needle" in text or "игла" in text:
                vector[1] = 1.0
            elif "alpha" in text:
                vector[0] = 1.0
                if "beta" in text:
                    vector[2] = 0.75
            else:
                vector[3] = 1.0
            norm = math.hypot(*vector)
            result.append([value / norm for value in vector])
        return result


class SemanticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.store = Store(self.directory / "canonical.sqlite3")
        self.encoder = FakeEncoder()
        self.index = SemanticIndex(self.store, self.directory / "missing-model", encoder=self.encoder)

    def remember(self, content, *, accepted=True, key=None):
        event = self.store.event("user", content)
        memory = self.store.remember(content, sources=[event], actor="owner" if accepted else "model",
                                    status="accepted" if accepted else "candidate", key=key)
        return event, memory

    def test_missing_model_does_not_create_empty_index_or_call_network(self):
        index = SemanticIndex(self.store, self.directory / "not-installed")
        self.assertFalse(index.available())
        self.assertEqual(index.search("query"), [])
        self.assertEqual(index.update(), {"indexed": 0, "available": False})
        self.assertEqual(index.stats()["sources"], 0)
        self.assertFalse(index.index_path.exists())
        self.assertFalse(index.model_dir.exists())

    def test_cache_updates_only_changed_sources_and_reuses_on_restart(self):
        event = self.store.event("user", "alpha fact")
        self.assertEqual(self.index.update()["indexed"], 1)
        calls = len(self.encoder.calls)
        self.assertEqual(self.index.update()["indexed"], 0)
        self.assertEqual(len(self.encoder.calls), calls)
        reopened = SemanticIndex(self.store, self.directory / "missing-model", encoder=self.encoder)
        self.assertEqual(reopened.update()["indexed"], 0)
        self.assertEqual(reopened.search("alpha", kind="event")[0]["id"], event)
        with self.store._connect() as db:
            db.execute("UPDATE events SET content='needle fact' WHERE id=?", (event,))
        self.assertEqual(reopened.search("alpha", kind="event"), [])
        self.assertEqual(reopened.update()["indexed"], 1)
        self.assertEqual(reopened.search("игла", kind="event")[0]["id"], event)

    def test_index_read_failure_after_initialization_disables_only_current_instance(self):
        event = self.store.event("user", "alpha")
        self.index.update()
        with self.index._db() as db:
            db.execute("DROP TABLE vectors")
        with self.assertRaises(sqlite3.Error):
            self.index.search("alpha", kind="event")
        self.assertFalse(self.index.available())
        self.assertEqual(self.index.search("alpha", kind="event"), [])
        self.assertEqual(self.index.update(), {"indexed": 0, "available": False})
        self.assertTrue(self.index.index_path.is_file())
        self.assertEqual(self.store.get_event(event)["content"], "alpha")
        reopened = SemanticIndex(self.store, self.directory / "missing-model", encoder=self.encoder)
        self.assertTrue(reopened.available())

    def test_corrupt_index_maintenance_failure_does_not_repeat_or_delete_files(self):
        damaged = b"not a SQLite database"
        self.index.index_path.write_bytes(damaged)
        with self.assertRaises(sqlite3.Error):
            self.index.update()
        self.assertFalse(self.index.available())
        self.assertEqual(self.index.update(), {"indexed": 0, "available": False})
        self.assertEqual(self.index.index_path.read_bytes(), damaged)

    def test_candidates_never_index_as_accepted_and_status_changes_gate_cached_vectors(self):
        _, accepted = self.remember("alpha accepted")
        _, candidate = self.remember("alpha candidate", accepted=False)
        self.index.update(include_events=False)
        self.assertEqual([row["id"] for row in self.index.search("alpha")], [accepted])
        with self.store._connect() as db:
            db.execute("UPDATE memories SET status='candidate' WHERE id=?", (accepted,))
        self.assertEqual(self.index.search("alpha"), [])
        self.store.accept(candidate)
        self.index.update(include_events=False)
        self.assertEqual(self.index.search("alpha")[0]["id"], candidate)

    def test_forgetting_and_supersession_gate_both_memory_and_source_events(self):
        event, memory = self.remember("alpha old", key="current")
        self.index.update()
        self.assertEqual(self.index.search("alpha")[0]["id"], memory)
        new_event, new_memory = self.remember("needle new", key="current")
        self.assertEqual(self.index.search("alpha"), [])
        self.assertEqual(self.index.search("alpha", kind="event"), [])
        self.index.update()
        self.assertEqual(self.index.search("игла")[0]["id"], new_memory)
        self.assertEqual(self.index.search("игла", kind="event")[0]["id"], new_event)
        self.store.forget(new_memory)
        self.assertEqual(self.index.search("игла"), [])
        self.assertEqual(self.index.search("игла", kind="event"), [])

    def test_long_chunk_crowding_and_inactive_sources_do_not_hide_valid_hit(self):
        obsolete = self.store.event("user", "alpha " * 6000)
        active = self.store.event("user", "alpha beta valid result")
        self.index.update()
        hidden = self.store.remember("old alpha", sources=[obsolete])
        self.store.forget(hidden)
        self.assertEqual(self.index.search("alpha", kind="event", limit=1)[0]["id"], active)

    def test_chunk_offsets_and_full_source_hash_match_exact_pages(self):
        content = "alpha background. " * 500 + "needle is near the end."
        event = self.store.event("tool", content)
        self.index.update()
        result = self.index.search("игла", kind="event", limit=1)[0]
        self.assertEqual(result["id"], event)
        self.assertGreater(result["matched_offset"], 8000)
        self.assertIn("needle", result["content"])
        exact = self.store.get_event(event, offset=result["matched_offset"], limit=800)
        self.assertEqual(result["content"], exact["content"])
        self.assertEqual(result["content_hash"], self.store.get_event(event)["content_hash"])

    def test_pipeline_revision_invalidates_unchanged_source_cache(self):
        self.store.event("user", "alpha")
        self.index.update()
        with self.index._db() as db:
            db.execute("UPDATE indexed SET model='old-pipeline'")
            db.execute("UPDATE vectors SET model='old-pipeline'")
        reopened = SemanticIndex(self.store, self.directory / "missing-model", encoder=self.encoder)
        self.assertEqual(reopened.search("alpha", kind="event"), [])
        self.assertEqual(reopened.update()["indexed"], 1)
        self.assertEqual(len(reopened.search("alpha", kind="event")), 1)

    def test_short_encoder_batch_is_rejected_without_partial_committed_cache(self):
        event = self.store.event("user", "alpha " * 600)
        self.index.update()
        before = self.index.stats()
        with self.store._connect() as db:
            db.execute("UPDATE events SET content='needle changed' WHERE id=?", (event,))
        self.encoder.encode = lambda texts: []
        with self.assertRaisesRegex(ValueError, "count"):
            self.index.update()
        self.assertEqual(self.index.stats(), before)

    def test_invalid_vectors_and_zero_limit(self):
        self.store.event("user", "alpha")
        self.index.update()
        self.assertEqual(self.index.search("alpha", kind="event", limit=0), [])
        for vector in ([1.0], [float("nan")] * DIMENSION, [0.0] * DIMENSION):
            self.encoder.encode = lambda texts, v=vector: [v for _ in texts]
            with self.assertRaisesRegex(ValueError, "vector"):
                self.index.search("query", kind="event")

    def test_index_paths_do_not_collide_between_two_canonical_databases(self):
        other = Store(self.directory / "other.sqlite3")
        another = SemanticIndex(other, self.directory / "missing-model", encoder=self.encoder)
        self.assertNotEqual(self.index.index_path, another.index_path)

    def test_idle_queue_is_bounded_and_changes_during_encoding_are_not_lost(self):
        event = self.store.event("user", "alpha")
        self.index.update()
        idle = self.index.update(max_sources=4)
        self.assertEqual(idle["checked"], 0)
        with self.store._connect() as db:
            db.execute("UPDATE events SET content='alpha edited' WHERE id=?", (event,))
        encode = self.encoder.encode
        changed = []
        def racing_encode(texts):
            if not changed:
                with self.store._connect() as db:
                    db.execute("UPDATE events SET content='needle concurrent edit' WHERE id=?", (event,))
                changed.append(True)
            return encode(texts)
        self.encoder.encode = racing_encode
        first = self.index.update(max_sources=4)
        self.assertEqual(first["remaining"], 1)
        self.assertEqual(self.index.search("alpha", kind="event"), [])
        second = self.index.update(max_sources=4)
        self.assertEqual(second["remaining"], 0)
        self.assertEqual(self.index.search("игла", kind="event")[0]["id"], event)

    def test_fresh_derived_cache_requeues_canonical_snapshot(self):
        self.store.event("user", "alpha")
        self.index.update()
        self.assertEqual(self.index.update()["remaining"], 0)
        destination = self.directory / "restored" / "canonical.sqlite3"
        restored = Store(self.store.backup(destination))
        index = SemanticIndex(restored, self.directory / "missing-model", encoder=self.encoder)
        self.assertEqual(index.update()["indexed"], 1)
        self.assertEqual(len(index.search("alpha",kind="event")), 1)

    def test_hybrid_fusion_deduplicates_without_inflating_duplicate_score(self):
        lexical = [{"id":1,"content":"lexical-one"}, {"id":2,"content":"both"}]
        semantic = [{"id":2,"content":"semantic-two"}, {"id":3,"content":"semantic-three"}]
        result = hybrid(lexical, semantic)
        self.assertEqual([row["id"] for row in result], [2,1,3])
        self.assertEqual(result[0]["content"], "semantic-two")
        repeated = hybrid([lexical[0]] * 9, [])
        self.assertEqual(repeated[0]["hybrid_score"], round(1/31, 6))
        self.assertEqual(hybrid(lexical, semantic, limit=0), [])
        mixed = hybrid([{"id":1,"content":"fact"}], [{"id":1,"role":"user","session":"main","content":"event"}])
        self.assertEqual(len(mixed), 2)

    def test_weak_lexical_overlap_does_not_displace_semantic_evidence(self):
        lexical = [{"id": i, "content": "generic context", "match": {"coverage": 0.4}}
                   for i in range(2, 6)]
        semantic = [{"id": i, "content": f"semantic passage {i}", "semantic_score": 0.9 - i * 0.01}
                    for i in range(1, 6)]
        self.assertEqual([row["id"] for row in hybrid(lexical, semantic, 4)], [1, 2, 3, 4])
        # A complete lexical match still adds independent support, even when it
        # matched normalized forms rather than literal words.
        lexical[0]["match"]["coverage"] = 1.0
        self.assertEqual(hybrid(lexical, semantic, 1)[0]["id"], 2)
        exact_identifier = {"id": 20, "content": "port 5544", "match": {"coverage": 1.0}}
        self.assertEqual(hybrid([exact_identifier], semantic, 1)[0]["id"], 20)

    def test_fusion_preserves_selected_passage_and_its_unverified_origin(self):
        common = {"id": 1, "role": "assistant", "session": "archive", "content_hash": "same",
                  "meta": {"trust": "historical_unverified"}}
        lexical = dict(common, content="unrelated opening", offset=0, match={"coverage": 0.25})
        semantic = dict(common, content="responsive tail", offset=4000, matched_offset=4000,
                        semantic_score=0.8, origin={"external_id": "old-source"})
        result = hybrid([lexical], [semantic])[0]
        self.assertEqual(result["content"], "responsive tail")
        self.assertEqual(result["offset"], 4000)
        self.assertEqual(result["origin"], semantic["origin"])
        self.assertEqual(result["meta"]["trust"], "historical_unverified")
        self.assertNotIn("match", result)
        self.assertNotIn("hybrid_score", semantic)  # inputs are never mutated

    def test_conflicting_versions_roles_and_withdrawal_are_not_fused(self):
        lexical = {"id": 1, "content": "same source", "content_hash": "before",
                   "status": "accepted", "match": {"coverage": 1.0}}
        semantic = dict(lexical, semantic_score=0.9)
        for change in ({"content_hash": "after"}, {"status": "candidate"},
                       {"status": "forgotten"}, {"status": "superseded"}, {"inactive": True}):
            with self.subTest(change=change):
                self.assertEqual(hybrid([lexical], [dict(semantic, **change)]), [])
        event = dict(lexical, role="user", session="archive")
        self.assertEqual(hybrid([event], [dict(event, role="assistant", semantic_score=0.9)]), [])

    def test_missing_invalid_coverage_and_duplicate_rows_do_not_inflate_rank(self):
        semantic = [{"id": 1, "semantic_score": 0.9}, {"id": 2, "semantic_score": 0.8}]
        for score in (None, "invalid", float("nan"), float("inf"), 0):
            self.assertEqual(hybrid([{"id": 2, "score": score}], semantic)[0]["id"], 1)
        for coverage in (None, "invalid", float("nan"), float("inf"), -1):
            self.assertEqual(hybrid([{"id": 2, "match": {"coverage": coverage}}], semantic)[0]["id"], 1)
        rows = [{"id": 1, "score": 1}, {"id": 2, "score": 0.5}]
        self.assertEqual(hybrid([rows[0]] * 5 + [rows[1]], []), hybrid(rows, []))
        self.assertEqual([row["id"] for row in hybrid(rows, [])], [1, 2])

    def test_local_ort_derivative_install_reuse_and_corruption_repair(self):
        directory = self.directory / "model"
        directory.mkdir()
        assets = {}
        for name, data in (("model.onnx", b"pinned source"), ("tokenizer.json", b"tokenizer")):
            (directory / name).write_bytes(data)
            assets[name] = (name, len(data), hashlib.sha256(data).hexdigest())
        payload = b"derived model"
        conversions = []
        class Options:
            def add_session_config_entry(self, *args):
                pass
        def convert(source, *, sess_options, providers):
            conversions.append(source)
            Path(sess_options.optimized_model_filepath).write_bytes(payload)
            return object()
        ort = SimpleNamespace(__version__=ORT_VERSION, disable_telemetry_events=lambda: None,
                              SessionOptions=Options, GraphOptimizationLevel=SimpleNamespace(ORT_DISABLE_ALL=0),
                              InferenceSession=convert)
        with patch("marka.semantic.ASSETS", assets), patch("marka.semantic.RUNTIME_BYTES", len(payload)), \
                patch.dict("sys.modules", {"onnxruntime": ort}), \
                patch("marka.semantic.urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            first = install_model(directory)
            self.assertEqual(first["runtime"]["source_sha256"], assets["model.onnx"][2])
            self.assertEqual(first["runtime"]["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(len(conversions), 1)
            self.assertEqual(install_model(directory), first)
            self.assertEqual(len(conversions), 1)
            index = SemanticIndex(self.store, directory)
            self.assertTrue(index.available())
            (directory / "model.ort").write_bytes(b"x" * len(payload))
            with self.assertRaisesRegex(ValueError, "Derived model checksum"):
                index._encoder()
            install_model(directory)
            self.assertEqual(len(conversions), 2)
            self.assertEqual((directory / "model.ort").read_bytes(), payload)
            first["runtime"]["source_sha256"] = "0" * 64
            (directory / "manifest.json").write_text(json.dumps(first), "utf-8")
            self.assertFalse(index.available())
            self.assertFalse((directory / "model.ort.convert").exists())

    def test_runtime_manifest_is_bounded_and_rejects_wrong_versions(self):
        directory = self.directory / "model"
        directory.mkdir()
        (directory / "model.ort").write_bytes(b"data")
        index = SemanticIndex(self.store, directory)
        with patch("marka.semantic.RUNTIME_BYTES", 4):
            for content in ("[]", "null", "[]" * 10000, '{"runtime":[]}'):
                (directory / "manifest.json").write_text(content, "utf-8")
                self.assertFalse(index.available())


if __name__ == "__main__":
    unittest.main()
