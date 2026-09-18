from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.queue import Queue
from marka.evaluation import verify_completion
from marka.store import Store


class TestQueue(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "queue.sqlite3"
        self.queue = Queue(self.path)

    def test_duplicate_updates_return_existing_job_and_offset_never_rewinds(self):
        identifier = self.queue.enqueue("first", 10, source="telegram:123")
        with self.queue.connection() as db:
            db.execute("UPDATE jobs SET id='legacy-id',root_id='legacy-id' WHERE id=?", (identifier,))
        self.assertEqual(self.queue.enqueue("changed input", 10, source="telegram:123"), "legacy-id")
        self.assertEqual(self.queue.get("legacy-id")["prompt"], "first")
        self.queue.advance(123)
        self.queue.advance(122)
        self.assertEqual(Queue(self.path).offset(), 124)
        self.assertEqual(len(self.queue.list()), 1)

    def test_concurrent_claim_and_source_dedup(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            identifiers = list(pool.map(lambda _: self.queue.enqueue("task", 10, source="same"), range(12)))
        self.assertEqual(len(set(identifiers)), 1)
        with ThreadPoolExecutor(max_workers=6) as pool:
            claims = list(pool.map(lambda _: self.queue.claim(), range(12)))
        self.assertEqual(sum(item is not None for item in claims), 1)

    def test_restart_requeues_model_but_blocks_ambiguous_tools(self):
        model = self.queue.enqueue("model interrupted", 10)
        self.queue.claim()
        self.queue.checkpoint(model, [{"role": "user", "content": "request"}])
        tool = self.queue.enqueue("tool interrupted", 10)
        self.queue.claim()
        self.queue.checkpoint(tool, [{"tool": "write", "args": {"text": "password=synthetic"}}], inflight=True)
        restarted = Queue(self.path)
        restarted.recover()
        self.assertEqual(restarted.get(model)["state"], "queued")
        self.assertEqual(restarted.get(tool)["state"], "blocked")
        self.assertEqual(restarted.get(tool)["trace"][0]["args"]["text"], "password=[REDACTED]")
        self.assertTrue(restarted.resume(tool))
        self.assertFalse(restarted.get(tool)["inflight"])

    def test_outbox_dedup_and_delivery_uncertainty(self):
        self.queue.deliver("job:reply", 10, "answer")
        self.queue.deliver("job:reply", 10, "another answer")
        delivery = self.queue.next_delivery()
        self.assertEqual(delivery["text"], "answer")
        self.assertIsNone(self.queue.next_delivery())
        restarted = Queue(self.path)
        restarted.recover()
        self.assertEqual(restarted.delivery_issues()[0]["state"], "uncertain")
        restarted.delivery_result(delivery["id"], "pending")
        self.assertIsNone(restarted.next_delivery())
        restarted.deliver("explicit-new-message", 10, "another authorized message")
        new = restarted.next_delivery()
        restarted.delivery_result(new["id"], "pending", delay=0, error="known rate limit")
        self.assertEqual(restarted.next_delivery()["id"], new["id"])
        restarted.delivery_result(new["id"], "sent")
        self.assertIsNone(restarted.next_delivery())

    def test_recurring_successor_and_completion_are_one_transaction(self):
        root = self.queue.enqueue("repeat", 10, interval_seconds=300, runs=3)
        self.queue.claim()
        with patch.object(self.queue, "_insert_job", side_effect=RuntimeError("disk failed")):
            with self.assertRaisesRegex(RuntimeError, "disk failed"):
                self.queue.finish(root, "completed", result="done")
        self.assertEqual(Queue(self.path).get(root)["state"], "running")
        self.assertEqual(len(self.queue.list()), 1)
        self.assertIsNone(self.queue.next_delivery())
        self.queue.finish(root, "completed", result="done")
        self.queue.finish(root, "completed", result="duplicate completion")
        self.assertEqual(len(self.queue.list()), 2)
        final = self.queue.next_delivery()
        self.assertEqual(final["text"], "done")
        self.queue.delivery_result(final["id"], "sent")
        self.assertIsNone(self.queue.next_delivery())
        child = next(job for job in self.queue.list() if job["id"] != root)
        self.assertEqual(self.queue.get(child["id"])["root_id"], root)
        self.assertEqual(self.queue.get(child["id"])["runs_left"], 2)
        self.assertIsNone(self.queue.claim())
        with self.queue.connection() as db:
            db.execute("UPDATE jobs SET due=0 WHERE id=?", (child["id"],))
        self.assertEqual(self.queue.claim()["id"], child["id"])
        self.queue.finish(child["id"], "completed")
        active = [job for job in self.queue.list() if job["state"] == "queued"]
        self.assertEqual(len(active), 1)
        self.assertEqual(self.queue.get(active[0]["id"])["runs_left"], 1)
        self.assertEqual(self.queue.cancel(root), [active[0]["id"]])
        self.assertEqual(self.queue.get(active[0]["id"])["state"], "cancelled")

    def test_cancel_finish_race_does_not_create_active_successor(self):
        for count in range(8):
            root = self.queue.enqueue(f"schedule {count}", 10, interval_seconds=300, runs=2)
            self.assertEqual(self.queue.claim()["id"], root)
            with ThreadPoolExecutor(max_workers=2) as pool:
                finish = pool.submit(self.queue.finish, root, "completed")
                cancel = pool.submit(self.queue.cancel, root)
                finish.result()
                cancel.result()
            with self.queue.connection() as db:
                active = db.execute("SELECT count(*) FROM jobs WHERE root_id=? AND state IN ('queued','running')", (root,)).fetchone()[0]
            self.assertEqual(active, 0)

    def test_cancelled_job_cannot_be_checkpointed_or_finished(self):
        job = self.queue.enqueue("work", 10)
        self.queue.claim()
        self.queue.cancel(job)
        self.queue.checkpoint(job, [{"unwanted": "late write"}], inflight=True)
        self.queue.finish(job, "completed", "late result")
        row = self.queue.get(job)
        self.assertEqual(row["state"], "cancelled")
        self.assertEqual(row["trace"], [])
        self.assertEqual(row["result"], "")
        self.assertIsNone(self.queue.next_delivery())

    def test_resumed_job_can_deliver_new_result_after_failure(self):
        job = self.queue.enqueue("retry explicitly", 10)
        self.queue.claim()
        self.queue.finish(job, "blocked", error="Tool interrupted")
        first = self.queue.next_delivery()
        self.assertIn(f"/resume {job}", first["text"])
        self.queue.delivery_result(first["id"], "sent")
        self.assertTrue(self.queue.resume(job))
        self.queue.claim()
        self.queue.finish(job, "completed", result="verified final")
        second = self.queue.next_delivery()
        self.assertNotEqual(first["source"], second["source"])
        self.assertEqual(second["text"], "verified final")

    def test_legacy_schedule_schema_migrates_roots_without_losing_jobs(self):
        root = self.queue.enqueue("parent", 10, source="original", interval_seconds=300, runs=3)
        self.queue.claim()
        self.queue.finish(root, "completed")
        child = next(job["id"] for job in self.queue.list() if job["id"] != root)
        with self.queue.connection() as db:
            db.execute("DROP INDEX jobs_root")
            db.execute("ALTER TABLE jobs DROP COLUMN root_id")
        upgraded = Queue(self.path)
        self.assertEqual(upgraded.get(child)["root_id"], root)
        self.assertEqual(upgraded.cancel(root), [child])

    def test_invalid_schedule_is_rejected(self):
        for kwargs in ({"due": float("nan")}, {"interval_seconds": -1},
                       {"interval_seconds": 30}, {"runs": 2}, {"runs": 0}):
            with self.assertRaises(ValueError):
                self.queue.enqueue("task", 10, **kwargs)

    def test_old_worker_cannot_overwrite_reclaimed_job(self):
        identifier = self.queue.enqueue("Stop, correct and resume", 10)
        old = self.queue.claim()
        self.queue.cancel(identifier)
        self.assertTrue(self.queue.resume(identifier))
        current = self.queue.claim()
        self.assertNotEqual(old["lease"], current["lease"])
        self.assertFalse(self.queue.checkpoint(identifier, [{"late": True}], lease=old["lease"]))
        self.assertFalse(self.queue.finish(identifier, "completed", "stale result", lease=old["lease"]))
        self.assertFalse(self.queue.requeue(identifier, old["lease"], [], "stale progress"))
        self.assertFalse(self.queue.reserve_call(identifier, old["lease"])["allowed"])
        self.assertEqual(self.queue.get(identifier)["state"], "running")
        self.assertIsNone(self.queue.next_delivery())
        self.assertTrue(self.queue.finish(identifier, "completed", "new result", lease=current["lease"]))
        self.assertEqual(self.queue.next_delivery()["text"], "new result")

    def test_more_than_twelve_steps_continue_without_final_or_budget_reset(self):
        identifier = self.queue.enqueue("Build a long report in three slices", 10)
        self.queue.configure_task(identifier, max_steps=26, max_model_calls=30, max_seconds=900)
        for batch in range(3):
            job = self.queue.claim()
            for step in range(8):
                result = self.queue.reserve_call(identifier, job["lease"])
                self.assertTrue(result["allowed"])
                self.assertEqual(result["step_number"], batch * 8 + step + 1)
            self.assertTrue(self.queue.requeue(identifier, job["lease"], [{"batch": batch}], "Continue report"))
            self.assertIsNone(self.queue.next_delivery())
        restarted = Queue(self.path)
        self.assertEqual(restarted.progress(identifier)["budget"]["used"], {"steps": 24, "model_calls": 24})
        self.assertEqual(restarted.progress(identifier)["budget"]["continuations"], 3)
        job = restarted.claim()
        restarted.reserve_call(identifier, job["lease"], step=False)
        self.assertEqual(restarted.progress(identifier)["budget"]["used"], {"steps": 24, "model_calls": 25})

    def test_task_reservation_is_atomic_and_consultation_uses_call_budget(self):
        identifier = self.queue.enqueue("Bound concurrent calls", 10)
        self.queue.configure_task(identifier, max_steps=10, max_model_calls=3, max_seconds=900)
        job = self.queue.claim()
        self.assertTrue(self.queue.reserve_call(identifier, job["lease"], step=False)["allowed"])
        with ThreadPoolExecutor(max_workers=5) as pool:
            reservations = list(pool.map(lambda _: self.queue.reserve_call(identifier, job["lease"]), range(8)))
        self.assertEqual(sum(item["allowed"] for item in reservations), 2)
        self.assertEqual(self.queue.progress(identifier)["budget"]["used"], {"steps": 2, "model_calls": 3})
        self.assertEqual(self.queue.reserve_call(identifier, job["lease"])["reason"], "model_call_limit")
        self.assertFalse(self.queue.requeue(identifier, job["lease"], []))

    def test_deadline_starts_on_claim_and_owner_extension_does_not_clear_usage(self):
        with patch("marka.queue.time.time", return_value=100):
            identifier = self.queue.enqueue("Task with pause", 10)
            self.queue.configure_task(identifier, max_steps=2, max_model_calls=2, max_seconds=30)
        with patch("marka.queue.time.time", return_value=500):
            job = self.queue.claim()
            self.assertEqual(job["deadline"], 530)
            self.queue.reserve_call(identifier, job["lease"])
            self.queue.cancel(identifier)
        with patch("marka.queue.time.time", return_value=600):
            self.queue.resume(identifier)
            second = self.queue.claim()
            self.assertEqual(self.queue.reserve_call(identifier, second["lease"])["reason"], "time_limit")
            self.queue.configure_task(identifier, max_steps=99, max_model_calls=99, max_seconds=900)
            self.assertEqual(self.queue.get(identifier)["deadline"], 530)
            extended = self.queue.extend_budget(identifier, extra_seconds=20, extra_steps=1, extra_model_calls=1)
            self.assertEqual(extended["deadline"], 620)
            self.assertEqual(extended["used"], {"steps": 1, "model_calls": 1})
            self.assertTrue(self.queue.reserve_call(identifier, second["lease"])["allowed"])

    def test_recovery_fences_old_worker_and_preserves_total_budget(self):
        identifier = self.queue.enqueue("Restart during a call", 10)
        self.queue.configure_task(identifier, max_steps=2, max_model_calls=2)
        old = self.queue.claim()
        self.queue.reserve_call(identifier, old["lease"])
        self.queue.recover()
        current = self.queue.claim()
        self.assertFalse(self.queue.finish(identifier, "completed", lease=old["lease"]))
        self.assertTrue(self.queue.reserve_call(identifier, current["lease"])["allowed"])
        self.assertFalse(self.queue.reserve_call(identifier, current["lease"])["allowed"])

    def test_structured_progress_survives_restart_and_observations_are_immutable(self):
        identifier = self.queue.enqueue("Prepare checked artifact", 10)
        job = self.queue.claim()
        self.assertTrue(self.queue.save_plan(identifier, [{"title": "Build", "status": "completed", "evidence": "step 1"}], lease=job["lease"], summary="Built report"))
        self.assertTrue(self.queue.record_step(identifier, lease=job["lease"], number=1, name="workspace.write",
                                             arguments={"content": "password=synthetic"}, outcome={"ok": True}, event_id=7))
        self.assertFalse(self.queue.record_step(identifier, lease=job["lease"], number=1, name="workspace.write", outcome={"ok": False}))
        receipt = {"path": "reports/out.txt", "sha256": "f" * 64, "bytes": 12}
        self.queue.record_artifact(identifier, receipt, lease=job["lease"], step=1)
        self.queue.finish(identifier, "completed", "Report ready", lease=job["lease"], verification={"status": "observed"})
        progress = Queue(self.path).progress(identifier)
        self.assertEqual(progress["plan"][0]["status"], "completed")
        self.assertEqual(progress["steps"][0]["outcome"], {"ok": True})
        self.assertEqual(progress["artifacts"][0]["sha256"], "f" * 64)
        self.assertEqual(progress["verification"], {"status": "observed"})
        with self.queue.connection() as db:
            arguments = db.execute("SELECT arguments FROM task_steps WHERE job_id=?", (identifier,)).fetchone()[0]
        self.assertNotIn("synthetic", arguments)

    def test_large_code_observation_is_bounded_without_losing_the_task(self):
        identifier = self.queue.enqueue("Inspect large source", 10)
        job = self.queue.claim()
        self.assertTrue(self.queue.record_step(identifier, lease=job["lease"], number=1, name="self.inspect",
                                             arguments={"content": "я" * 120000}, outcome={"result": "я" * 120000}))
        observed = self.queue.progress(identifier)["steps"][0]["outcome"]
        self.assertTrue(observed["truncated"])
        self.assertEqual(len(observed["sha256"]), 64)

    def test_plan_and_receipts_reject_nested_or_unsafe_values(self):
        identifier = self.queue.enqueue("Plan boundaries", 10)
        job = self.queue.claim()
        for plan in (["step"] * 13, [{"title": "x", "children": []}], [{"title": {"nested": "value"}}]):
            with self.assertRaises(ValueError):
                self.queue.save_plan(identifier, plan, lease=job["lease"])
        with self.assertRaises(ValueError):
            self.queue.record_artifact(identifier, {"path": "../auth.json", "sha256": "f" * 64, "bytes": 12}, lease=job["lease"])
        self.queue.checkpoint(identifier, [], lease=job["lease"], inflight=True)
        self.assertFalse(self.queue.requeue(identifier, job["lease"], [], "ambiguous action"))

    def test_owner_budget_extension_is_atomic_and_idempotent_across_crash(self):
        identifier = self.queue.enqueue("Continue with explicit owner budget", 10)
        self.queue.configure_task(identifier, max_steps=4, max_model_calls=4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.queue.extend_budget(identifier, extra_steps=3,
                          extra_model_calls=3, source="telegram:extend:123"), range(8)))
        restarted = Queue(self.path)
        repeated = restarted.extend_budget(identifier, extra_steps=3, extra_model_calls=3, source="telegram:extend:123")
        self.assertEqual(repeated["limits"]["steps"], 7)
        self.assertEqual(repeated["limits"]["model_calls"], 7)
        other = restarted.enqueue("Different task", 10)
        restarted.configure_task(other)
        with self.assertRaises(ValueError):
            restarted.extend_budget(other, extra_steps=10, source="telegram:extend:123")

    def test_legacy_error_is_restored_from_canonical_event_and_not_lost_to_new_steps(self):
        store = Store(self.path)
        identifier = self.queue.enqueue("Continue legacy code task", 0)
        job = self.queue.claim()
        old_args, new_args = {"argv": ["python", "old.py"]}, {"argv": ["python", "other.py"]}
        failure = {"ok": True, "result": {"exit_code": 2}}
        old_event = store.event("tool", json.dumps(failure), session="work:" + identifier,
                                meta={"job": identifier, "tool": "code.run", "arguments": old_args})
        new_event = store.event("tool", '{"ok":true,"result":{"exit_code":0}}', session="work:" + identifier,
                                meta={"job": identifier, "tool": "code.run", "arguments": new_args})
        trace = [{"kind": "tool", "name": "code.run", "arguments": json.dumps(old_args)},
                 {"kind": "observation", "event_id": old_event, "content": '{"ok":true,"result":'},
                 {"kind": "tool", "name": "code.run", "arguments": json.dumps(new_args)},
                 {"kind": "observation", "event_id": new_event, "content": '{"ok":true}'}]
        self.queue.checkpoint(identifier, trace, lease=job["lease"])
        self.queue.record_step(identifier, lease=job["lease"], number=1, name="code.run", arguments=new_args,
                               outcome={"ok": True, "result": {"exit_code": 0}}, event_id=new_event)
        evidence = Queue(self.path).evidence_trace(identifier)
        self.assertEqual(len(evidence), 4)
        self.assertEqual([evidence[1]["event_id"], evidence[3]["event_id"]], [old_event, new_event])
        self.assertEqual(json.loads(evidence[1]["content"]), failure)
        self.assertEqual(verify_completion(evidence)["status"], "contradicted")

    def test_evidence_restore_never_borrows_another_job_role_session_or_tool(self):
        store = Store(self.path)
        identifier = self.queue.enqueue("Local legacy evidence", 0)
        job = self.queue.claim()
        variants = [("tool", "work:another-job", {"job": identifier, "tool": "code.run"}),
                    ("user", "work:" + identifier, {"job": identifier, "tool": "code.run"}),
                    ("tool", "work:" + identifier, {"job": "another-job", "tool": "code.run"}),
                    ("tool", "work:" + identifier, {"job": identifier, "tool": "workspace.read"})]
        for role, session, meta in variants:
            event_id = store.event(role, '{"ok":true,"result":{"exit_code":0,"private":"FOREIGN_MARKER"}}', session=session, meta=meta)
            trace = [{"kind": "tool", "name": "code.run", "arguments": '{"argv":["python","a.py"]}'},
                     {"kind": "observation", "event_id": event_id, "content": '{"ok":true,"result":{"exit_code":1}}'}]
            self.queue.checkpoint(identifier, trace, lease=job["lease"])
            evidence = self.queue.evidence_trace(identifier)
            self.assertNotIn("FOREIGN_MARKER", json.dumps(evidence))
            self.assertIsNone(evidence[1]["event_id"])
            self.assertEqual(verify_completion(evidence)["status"], "contradicted")

    def test_evidence_keeps_legacy_checkpoint_after_event_retention(self):
        store = Store(self.path)
        identifier = self.queue.enqueue("Retained checkpoint", 0)
        job = self.queue.claim()
        event_id = store.event("tool", '{"ok":false,"error":"execution failed"}', session="work:" + identifier,
                               meta={"job": identifier, "tool": "code.run"})
        trace = [{"kind": "tool", "name": "code.run", "arguments": '{"argv":["python","a.py"]}'},
                 {"kind": "observation", "event_id": event_id, "content": '{"ok":false,"error":"execution failed"}'}]
        self.queue.checkpoint(identifier, trace, lease=job["lease"])
        with store._connect() as db:
            db.execute("DELETE FROM events WHERE id=?", (event_id,))
        evidence = self.queue.evidence_trace(identifier)
        self.assertEqual(evidence, trace)
        self.assertEqual(verify_completion(evidence)["status"], "contradicted")

    def test_evidence_deduplicates_events_and_preserves_canonical_chronology(self):
        store = Store(self.path)
        identifier = self.queue.enqueue("Ordering", 0)
        job = self.queue.claim()
        first = store.event("tool", '{"ok":true,"result":{"exit_code":1}}', session="work:" + identifier,
                            meta={"job": identifier, "tool": "code.run"})
        second = store.event("tool", '{"ok":true,"result":{"exit_code":0}}', session="work:" + identifier,
                             meta={"job": identifier, "tool": "code.run"})
        args = {"argv": ["python", "a.py"]}
        self.queue.record_step(identifier, lease=job["lease"], number=1, name="code.run", arguments=args,
                               outcome={"ok": True, "result": {"exit_code": 1}}, event_id=first)
        pair = [{"kind": "tool", "name": "code.run", "arguments": json.dumps(args)},
                {"kind": "observation", "event_id": second, "content": '{"ok":true}'}]
        self.queue.checkpoint(identifier, pair + pair, lease=job["lease"])
        evidence = self.queue.evidence_trace(identifier)
        self.assertEqual(len(evidence), 4)
        self.assertEqual([evidence[1]["event_id"], evidence[3]["event_id"]], [first, second])
        self.assertEqual(verify_completion(evidence)["status"], "observed")

    def test_large_unicode_observation_restores_only_hash_matching_canonical_source(self):
        store = Store(self.path)
        identifier = self.queue.enqueue("Check large command output", 0)
        job = self.queue.claim()
        outcome = {"ok": True, "result": {"exit_code": 2, "output": "Ошибка" * 10000}}
        event_id = store.event("tool", json.dumps(outcome, ensure_ascii=False), session="work:" + identifier,
                               meta={"job": identifier, "tool": "code.run"})
        self.queue.record_step(identifier, lease=job["lease"], number=1, name="code.run", arguments={"argv": ["python", "a.py"]},
                               outcome=outcome, event_id=event_id)
        self.assertTrue(self.queue.progress(identifier)["steps"][0]["outcome"]["truncated"])
        evidence = self.queue.evidence_trace(identifier)
        self.assertEqual(json.loads(evidence[1]["content"]), outcome)
        self.assertEqual(verify_completion(evidence)["status"], "contradicted")
        changed = {"ok": True, "result": {"exit_code": 0, "output": "Changed canonical source"}}
        with store._connect() as db:
            db.execute("UPDATE events SET content=? WHERE id=?", (json.dumps(changed), event_id))
        evidence = self.queue.evidence_trace(identifier)
        self.assertTrue(json.loads(evidence[1]["content"])["truncated"])
        self.assertIsNone(evidence[1]["event_id"])
        self.assertEqual(verify_completion(evidence)["status"], "unverified")

    def test_intact_durable_observation_cannot_be_rewritten_by_canonical_event(self):
        store = Store(self.path)
        identifier = self.queue.enqueue("Immutable receipt", 0)
        job = self.queue.claim()
        failure = {"ok": True, "result": {"exit_code": 1}}
        event_id = store.event("tool", '{"ok":true,"result":{"exit_code":0}}', session="work:" + identifier,
                               meta={"job": identifier, "tool": "code.run", "arguments": {"argv": ["python", "different.py"]}})
        args = {"argv": ["python", "original.py"]}
        self.queue.record_step(identifier, lease=job["lease"], number=1, name="code.run", arguments=args, outcome=failure, event_id=event_id)
        evidence = self.queue.evidence_trace(identifier)
        self.assertEqual(json.loads(evidence[0]["arguments"]), args)
        self.assertEqual(json.loads(evidence[1]["content"]), failure)
        self.assertEqual(verify_completion(evidence)["status"], "contradicted")

    def test_sensitive_nested_fields_use_shared_structural_redaction(self):
        identifier = self.queue.enqueue("Structural redaction", 0)
        job = self.queue.claim()
        self.queue.record_step(identifier, lease=job["lease"], number=1, name="test",
                               arguments={"password": "SYNTHETIC_NESTED_SECRET"},
                               outcome={"ok": True, "result": {"api_key": "SYNTHETIC_NESTED_KEY"}})
        evidence = json.dumps(self.queue.evidence_trace(identifier))
        self.assertNotIn("SYNTHETIC_NESTED_SECRET", evidence)
        self.assertNotIn("SYNTHETIC_NESTED_KEY", evidence)
