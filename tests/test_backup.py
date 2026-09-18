"""Real SQLite snapshot/restore and bounded daily retention, with no provider."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from marka.backup import DailyBackups
from marka.queue import Queue
from marka.store import Store


DAY = datetime(2026, 9, 1, 12, tzinfo=timezone.utc).timestamp()


class BackupTests(unittest.TestCase):
    def setUp(self):
        # The suite also runs in a 128 MiB tmpfs sandbox. This fixture models a
        # disk with room for backups; explicit low-space tests override it.
        disk = patch('marka.backup.shutil.disk_usage', return_value=type('Usage', (), {'free': 8 * 1024**3})())
        disk.start()
        self.addCleanup(disk.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'marka.sqlite3')
        self.backups = DailyBackups(self.store, self.root)
        self.queue = Queue(self.store.path)
        self.source = self.store.event('user', 'A memory worth preserving')
        self.memory = self.store.remember('A memory worth preserving', sources=[self.source], status='accepted', actor='owner')
        self.job = self.queue.enqueue('A queued task', 17)

    def test_snapshot_restores_memory_sources_and_queue_without_auth(self):
        (self.root / 'settings.json').write_text('private settings fixture', 'utf-8')
        (self.root / 'codex').mkdir()
        (self.root / 'codex' / 'auth.json').write_text('private auth fixture', 'utf-8')
        result = self.backups.run_due(now=DAY)
        self.assertEqual(result['state'], 'ok')
        target = self.backups.directory / result['filename']
        with closing(sqlite3.connect(target)) as snapshot:
            self.assertEqual(snapshot.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            self.assertEqual(snapshot.execute('SELECT content FROM events WHERE id=?', (self.source,)).fetchone()[0], 'A memory worth preserving')
            self.assertEqual(snapshot.execute('SELECT state FROM jobs WHERE id=?', (self.job,)).fetchone()[0], 'queued')
            self.assertEqual(snapshot.execute('SELECT count(*) FROM memory_sources').fetchone()[0], 1)
        self.assertEqual([p.name for p in self.backups.directory.iterdir()], ['2026-09-01.sqlite3'])
        self.assertNotIn(b'private auth fixture', target.read_bytes())
        restored = Store(target)
        self.assertEqual(restored.stats()['by_status']['accepted'], 1)
        self.assertEqual(Queue(target).get(self.job)['prompt'], 'A queued task')

    def test_daily_deduplication_survives_restart_and_next_utc_day_runs(self):
        self.assertEqual(self.backups.run_due(now=DAY)['state'], 'ok')
        self.store.event('user', 'arrived after snapshot')
        restarted = DailyBackups(Store(self.store.path), self.root)
        self.assertEqual(restarted.run_due(now=DAY + 60)['state'], 'not_due')
        self.assertEqual(restarted.run_due(now=DAY + 86400)['state'], 'ok')
        with closing(sqlite3.connect(restarted.directory / '2026-09-02.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 2)

    def test_rotation_keeps_seven_and_leaves_manual_files_and_sources(self):
        self.backups.directory.mkdir(parents=True)
        manual = self.backups.directory / 'owner-important.sqlite3'
        manual.write_bytes(b'manual copy')
        outer = self.root / 'backups' / 'before-upgrade.sqlite3'
        outer.write_bytes(b'earlier manual copy')
        for number in range(10):
            self.assertEqual(self.backups.run_due(now=DAY + number * 86400)['state'], 'ok')
        completed = sorted(path.name for path in self.backups.directory.glob('2026-*.sqlite3'))
        self.assertEqual(completed, [f'2026-09-{day:02}.sqlite3' for day in range(4, 11)])
        self.assertEqual(manual.read_bytes(), b'manual copy')
        self.assertEqual(outer.read_bytes(), b'earlier manual copy')
        self.assertEqual(self.store.stats()['events'], 1)

    def test_low_disk_defers_without_deleting_existing_copies_and_retries_hourly(self):
        first = self.backups.run_due(now=DAY)
        target = self.backups.directory / first['filename']
        before = target.read_bytes()
        usage = type('Usage', (), {'free': 10})()
        with patch('marka.backup.shutil.disk_usage', return_value=usage):
            state = self.backups.run_due(now=DAY + 86400)
        self.assertEqual(state['state'], 'deferred')
        self.assertEqual(state['error'], 'insufficient_disk_space')
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.backups.run_due(now=DAY + 86401)['state'], 'not_due')
        self.assertEqual(self.backups.run_due(now=DAY + 90001)['state'], 'ok')

    def test_disk_reserve_is_for_after_the_snapshot_including_wal_pages(self):
        with self.store._connect() as writer:
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('CREATE TABLE backup_fixture(payload BLOB)')
            writer.execute('INSERT INTO backup_fixture VALUES(zeroblob(2097152))')
            writer.commit()
            self.assertGreater((self.root / 'marka.sqlite3-wal').stat().st_size, self.store.path.stat().st_size)
            usage = type('Usage', (), {'free': 577 * 1024 * 1024})()
            with patch('marka.backup.shutil.disk_usage', return_value=usage):
                result = self.backups.run_due(now=DAY)
            self.assertEqual(result['state'], 'deferred')
            self.assertFalse(any(self.backups.directory.glob('*.sqlite3')))

    def test_interrupted_snapshot_keeps_last_success_and_does_not_rotate(self):
        self.backups.run_due(now=DAY)
        with patch.object(self.backups, '_snapshot', side_effect=TimeoutError('synthetic')):
            result = self.backups.run_due(now=DAY + 86400)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['last_success_at'], DAY)
        self.assertTrue((self.backups.directory / '2026-09-01.sqlite3').exists())
        self.assertFalse((self.backups.directory / '2026-09-02.sqlite3').exists())

    def test_file_symlink_cannot_replace_external_file(self):
        self.backups.directory.mkdir(parents=True)
        unrelated = self.root / 'unrelated.txt'
        unrelated.write_text('preserve', 'utf-8')
        try:
            (self.backups.directory / '2026-09-01.sqlite3').symlink_to(unrelated)
        except OSError:
            self.skipTest('symlink privileges unavailable')
        result = self.backups.run_due(now=DAY)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(unrelated.read_text('utf-8'), 'preserve')

    def test_crashed_claim_waits_then_recovers_and_replaces_only_own_partial(self):
        self.backups._prepare_directory()
        partial = self.backups.directory / '2026-09-01.partial'
        partial.write_bytes(b'incomplete')
        self.backups._claim(DAY)
        restarted = DailyBackups(Store(self.store.path), self.root)
        self.assertEqual(restarted.run_due(now=DAY + 10)['state'], 'not_due')
        self.assertEqual(restarted.run_due(now=DAY + 3601)['state'], 'ok')
        self.assertFalse(partial.exists())

    def test_real_snapshot_timeout_removes_partial_and_keeps_previous_snapshot(self):
        self.assertEqual(self.backups.run_due(now=DAY)['state'], 'ok')
        previous = self.backups.directory / '2026-09-01.sqlite3'
        before = previous.read_bytes()
        with patch('marka.backup.time.monotonic', side_effect=[0, 46]):
            result = self.backups.run_due(now=DAY + 86400)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error'], 'TimeoutError')
        self.assertEqual(previous.read_bytes(), before)
        self.assertFalse((self.backups.directory / '2026-09-02.partial').exists())
        self.assertFalse((self.backups.directory / '2026-09-02.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
