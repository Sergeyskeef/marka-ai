"""Authenticated owner commands must not restart an exhausted task or fake retry authorization."""
import tempfile
from pathlib import Path
import unittest

from marka.app import Application
from marka.config import Settings
from test_app import FakeClient, FinalProvider, update


class BudgetCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name) / 'state')
        self.settings.prepare()
        self.provider = FinalProvider()
        self.app = Application(self.settings, provider=self.provider, client=FakeClient())
        self.app.store.set_meta('owner_id', 17)

    def exhausted(self):
        identifier = self.app.queue.enqueue('Synthetic typing task', 17)
        self.app.queue.configure_task(identifier, max_steps=1, max_model_calls=2, max_seconds=600)
        job = self.app.queue.claim()
        self.app.queue.reserve_call(identifier, job['lease'], step=True)
        self.app.queue.finish(identifier, 'blocked', error='Step budget exhausted', lease=job['lease'])
        return identifier

    def replies(self):
        with self.app.queue.connection() as db:
            return [row['text'] for row in db.execute('SELECT text FROM deliveries ORDER BY id')]

    async def test_resume_exhausted_task_does_not_create_retry_epoch_or_queue_work(self):
        identifier = self.exhausted()
        before = self.app.queue.get(identifier)
        await self.app.ingest(update(501, '/resume ' + identifier))
        self.assertEqual(self.app.queue.get(identifier), before)
        self.assertIsNone(self.app.queue.claim())
        self.assertIsNone(self.app.store.get_meta('model-attempt:' + identifier))
        self.assertIn('/extend ' + identifier, self.replies()[-1])
        self.assertNotIn('Продолжу задачу', self.replies()[-1])
        self.assertEqual(self.provider.calls, [])

    async def test_extend_requeues_once_and_only_then_authorizes_owner_retry(self):
        identifier = self.exhausted()
        await self.app.ingest(update(502, '/extend ' + identifier))
        current = self.app.queue.get(identifier)
        self.assertEqual(current['state'], 'queued')
        self.assertEqual(current['steps_used'], 1)
        self.assertEqual(current['max_steps'], 1 + self.settings.task_max_steps)
        self.assertEqual(self.app.store.get_meta('model-attempt:' + identifier), 'owner-502')
        await self.app.ingest(update(502, '/extend ' + identifier))
        self.assertEqual(self.app.queue.get(identifier)['max_steps'], current['max_steps'])
        self.assertEqual(self.provider.calls, [])

    async def test_empty_read_progress_refreshes_liveness_without_chat_noise(self):
        identifier = self.exhausted()
        job = self.app.queue.get(identifier)
        before = self.replies()
        self.app.last_progress = 0
        await self.app.progress(job, '')
        self.assertEqual(self.replies(), before)
        self.assertEqual(self.app.heartbeat.job_id, identifier)


if __name__ == '__main__':
    unittest.main()
