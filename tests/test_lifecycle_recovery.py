import asyncio
import json
import os
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from marka.app import Application
from marka.health import Heartbeat
import test_guardian as support
guardian, BASE, NEW = support.guardian, support.BASE, support.NEW


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = object.__new__(Application)
        app = self.app
        app.settings = SimpleNamespace(data_dir=self.root, retention_days=30)
        app.client = SimpleNamespace(get_me=AsyncMock(return_value={}), call=AsyncMock(return_value={}))
        app.queue, app.store = Mock(), Mock()
        app.refresh_bridge_status = AsyncMock()
        app.stopping = asyncio.Event()
        app.heartbeat = Heartbeat(self.root)
        app.current = None
        for name in ('polling', 'worker', 'delivery', 'maintenance'):
            setattr(app, name, AsyncMock(side_effect=lambda: None))
        async def wait():
            await app.stopping.wait()
        for name in ('polling', 'worker', 'delivery', 'maintenance'):
            setattr(app, name, wait)

    def receipt(self):
        return json.loads((self.root / 'last-exit.json').read_text())

    async def test_component_failure_is_saved_before_shutdown_without_secret_text(self):
        async def fail():
            raise RuntimeError('secret-value must never reach the receipt')
        self.app.worker = fail
        with self.assertRaises(RuntimeError):
            await self.app.run()
        row = self.receipt()
        self.assertEqual((row['component'], row['event'], row['exception']), ('worker', 'failed', 'RuntimeError'))
        self.assertNotIn('secret-value', json.dumps(row))
        self.assertEqual(json.loads((self.root/'heartbeat.json').read_text())['phase'], 'stopping')
        self.assertEqual(row['boot_id'], self.app.heartbeat.boot_id)

    async def test_startup_failure_is_saved(self):
        self.app.client.get_me.side_effect = ValueError('private endpoint')
        with self.assertRaises(ValueError):
            await self.app.run()
        self.assertEqual(self.receipt()['component'], 'startup')
        self.assertNotIn('private endpoint', (self.root/'last-exit.json').read_text())

    async def test_unexpected_return_is_failure_not_silent_gateway_exit(self):
        self.app.polling = AsyncMock(return_value=None)
        with self.assertRaisesRegex(RuntimeError, 'returned unexpectedly'):
            await self.app.run()
        self.assertEqual((self.receipt()['component'], self.receipt()['event']), ('polling', 'returned'))

    async def test_cancelled_component_is_named(self):
        async def fail():
            raise asyncio.CancelledError()
        self.app.delivery = fail
        with self.assertRaises(asyncio.CancelledError):
            await self.app.run()
        self.assertEqual((self.receipt()['component'], self.receipt()['event']), ('delivery', 'cancelled'))

    async def test_external_signal_is_distinguished_from_component_error(self):
        async def stop():
            self.app._signal_stop(15)
        self.app.polling = stop
        await self.app.run()
        row = self.receipt()
        self.assertEqual((row['component'], row['event'], row['signal']), ('signal', 'signal', 15))

    async def test_receipt_io_error_does_not_hide_original_failure(self):
        self.app.client.get_me.side_effect = ValueError('original')
        with patch.object(self.app.heartbeat, 'record_exit', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(ValueError, 'original'):
                await self.app.run()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = support.GuardianTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.g = self.fixture.controller

    def accepted_new_release(self):
        f = self.fixture
        f.probation()
        f.now += 16
        f.heartbeat()
        self.g.tick()
        self.assertEqual(self.g.state['phase'], 'accepted')
        self.assertEqual(self.g.state['current_image'], NEW)

    def stopped_heartbeat(self):
        p = self.fixture.state_dir / 'heartbeat.json'
        value = json.loads(p.read_text())
        value['phase'] = 'stopping'
        guardian.atomic(p, guardian.canonical(value))

    def test_stable_liveness_failure_restarts_once_and_preserves_previous(self):
        self.accepted_new_release()
        self.stopped_heartbeat()
        self.g.tick()
        self.assertTrue(self.g.state['active']['restart_only'])
        self.g.tick()
        self.assertEqual(self.g.state['current_image'], NEW)
        self.assertEqual(self.g.state['previous_image'], BASE)
        self.assertEqual(self.g.state['last_result']['action'], 'restart')
        self.assertFalse(self.g.state['last_result']['restored_database'])
        self.assertTrue(list(self.g.root.glob('incident-*.json')))

    def test_second_failure_rolls_back_and_does_not_loop_restarting(self):
        self.accepted_new_release()
        self.stopped_heartbeat()
        self.g.tick(); self.g.tick()
        self.fixture.now += 6
        self.g.tick(); self.g.tick()
        self.assertEqual(self.g.state['current_image'], BASE)
        self.assertEqual(self.g.state['last_result']['action'], 'rollback')
        self.fixture.now += 6
        self.g.tick()
        self.assertEqual(self.g.state['phase'], 'manual_intervention')

    def test_candidate_probation_still_rolls_back_immediately(self):
        self.fixture.probation()
        self.fixture.now += 6
        self.stopped_heartbeat()
        self.g.tick(); self.g.tick()
        self.assertEqual(self.g.state['current_image'], BASE)
        self.assertEqual(self.g.state['last_result']['action'], 'rollback')

    def test_owner_recovery_does_not_restart_current_version(self):
        self.accepted_new_release()
        self.g.begin_recovery('owner recovery command')
        self.assertFalse(self.g.state['active']['restart_only'])
        self.assertEqual(self.g.state['active']['rollback_image'], BASE)

    def test_incident_only_copies_allowed_fields_and_marks_old_boot(self):
        secret = 'synthetic-private-content'
        guardian.atomic(self.fixture.state_dir/'last-exit.json', guardian.canonical({
            'component': 'worker', 'event': 'failed', 'exception': 'RuntimeError',
            'message': secret, 'sqlite_errorcode': 5, 'boot_id': 'a'*32, 'frames': [
                {'module': 'app', 'line': 42, 'source': secret}, {'module': secret, 'line': 9}]}))
        self.g.capture_incident('heartbeat unavailable')
        row = json.loads(next(self.g.root.glob('incident-*.json')).read_text())
        self.assertNotIn(secret, json.dumps(row))
        self.assertEqual(row['runtime_exit']['frames'], [{'module': 'app', 'line': 42}])
        self.assertFalse(row['runtime_exit_matches_boot'])
        self.assertEqual(row['runtime_exit']['sqlite_errorcode'], 5)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO')
    def test_fifo_cannot_block_incident_capture(self):
        os.mkfifo(self.fixture.state_dir/'last-exit.json')
        self.g.capture_incident('heartbeat unavailable')
        row = json.loads(next(self.g.root.glob('incident-*.json')).read_text())
        self.assertTrue(row['runtime_exit']['unavailable'])

    def test_incident_disk_error_does_not_disable_recovery(self):
        self.accepted_new_release()
        original = guardian.atomic
        def write(path, *args, **kwargs):
            if Path(path).name.startswith('incident-'):
                raise OSError('synthetic full disk')
            return original(path, *args, **kwargs)
        self.stopped_heartbeat()
        with patch.object(guardian, 'atomic', side_effect=write):
            self.g.tick()
        self.assertEqual(self.g.state['phase'], 'rolling_back')
        self.assertFalse(self.g.state['last_incident']['persisted'])

    def test_real_docker_byte_output_is_filtered_before_container_removal(self):
        docker = guardian.Docker(self.fixture.config)
        self.g.docker = docker
        output = subprocess.CompletedProcess([], 0, b'private chat content',
            b'  File "/app/marka/app.py", line 123, in run\nRuntimeError: synthetic-private-error\n')
        with patch.object(docker, 'inspect', return_value=self.fixture.docker.row), patch.object(docker, 'command', return_value=output):
            self.g.capture_incident('heartbeat unavailable')
        row = json.loads(next(self.g.root.glob('incident-*.json')).read_text())
        self.assertNotIn('capture_incomplete', row)
        self.assertEqual(row['log_exception_classes'], ['RuntimeError'])
        self.assertEqual(row['log_frames'], [{'module': 'app', 'line': 123}])
        self.assertNotIn('private', json.dumps(row))
