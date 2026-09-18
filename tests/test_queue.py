from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from marka.queue import Queue


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
