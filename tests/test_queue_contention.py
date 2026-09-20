import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from marka.app import Application
from marka.health import Heartbeat
from marka.queue import Queue


class QueueContentionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.queue = Queue(self.root / 'test.sqlite3')
        self.app = object.__new__(Application)
        self.app.stopping = asyncio.Event()

    async def test_locked_job_and_delivery_claims_yield_and_resume_once(self):
        job = self.queue.enqueue('work', 42)
        self.queue.deliver('result', 42, 'answer')
        for operation, expected in ((self.queue.claim, job), (self.queue.next_delivery, 1)):
            with self.subTest(operation=operation.__name__):
                lock = sqlite3.connect(self.queue.path)
                try:
                    lock.execute('BEGIN IMMEDIATE')
                    ticks = []
                    async def release():
                        # This runs on the same loop as the contended claim.
                        await asyncio.sleep(0.15)
                        ticks.append(time.monotonic())
                        lock.rollback()
                    releasing = asyncio.create_task(release())
                    result = await asyncio.wait_for(self.app.poll_queue(operation), 3)
                    await releasing
                    self.assertTrue(ticks)
                    self.assertEqual(result['id'], expected)
                    self.assertIsNone(operation())
                finally:
                    lock.close()

    async def test_persistent_contention_is_bounded_and_queue_preserved(self):
        job = self.queue.enqueue('work', 42)
        lock = sqlite3.connect(self.queue.path)
        try:
            lock.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError) as caught:
                await asyncio.wait_for(self.app.poll_queue(self.queue.claim, budget=0.2), 3)
            self.assertEqual(caught.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
        finally:
            lock.close()
        self.assertEqual(self.queue.get(job)['state'], 'queued')

    async def test_non_contention_error_is_not_retried(self):
        calls = []
        def invalid(**kwargs):
            calls.append(1)
            with self.queue.connection() as db:
                db.execute('SELECT * FROM missing_table')
        with self.assertRaises(sqlite3.OperationalError):
            await self.app.poll_queue(invalid)
        self.assertEqual(len(calls), 1)

    async def test_shutdown_interrupts_contention_wait_without_claim(self):
        lock = sqlite3.connect(self.queue.path)
        try:
            lock.execute('BEGIN IMMEDIATE')
            task = asyncio.create_task(self.app.poll_queue(self.queue.claim))
            await asyncio.sleep(0.15)
            self.app.stopping.set()
            self.assertIsNone(await asyncio.wait_for(task, 1))
        finally:
            lock.close()

    def test_sqlite_diagnostic_keeps_code_without_message(self):
        try:
            with self.queue.connection() as db:
                db.execute('SELECT * FROM private_table_name')
        except sqlite3.Error as exc:
            Heartbeat(self.root).record_exit('worker', 'failed', exc)
        value = json.loads((self.root / 'last-exit.json').read_text())
        self.assertEqual(value['sqlite_errorcode'], sqlite3.SQLITE_ERROR)
        self.assertNotIn('private_table_name', json.dumps(value))

    def test_keepalive_preserves_wal_without_holding_writer_transaction(self):
        wal = Path(str(self.queue.path) + '-wal')
        with self.queue.keepalive():
            self.queue.enqueue('first', 42)
            inode = wal.stat().st_ino
            for _ in range(30):
                observer = sqlite3.connect(self.queue.path.as_uri() + '?mode=ro', uri=True)
                try:
                    observer.execute('SELECT count(*) FROM jobs').fetchall()
                    self.assertEqual(wal.stat().st_ino, inode)
                    with self.queue.connection(timeout=0.1) as writer:
                        writer.execute('BEGIN IMMEDIATE')
                        writer.execute('UPDATE jobs SET updated=updated')
                finally:
                    observer.close()
                self.assertEqual(wal.stat().st_ino, inode)
        self.assertFalse(wal.exists())
