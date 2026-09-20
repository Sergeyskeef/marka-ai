import asyncio
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from marka.host_read import HostReader, checked_path, scrub, PAGE
from marka.bridge import Bridge, Rejected
from test_bridge import configuration, FakeTelegram, FakeProvider
import test_guardian as support


class PolicyTests(unittest.TestCase):
    def test_secrets_and_kernel_interfaces_are_not_readable(self):
        for path in ['/proc/self/environ', '/dev/sda', '/run/docker.sock', '/var/lib/docker/x',
                     '/etc/shadow', '/root/.ssh/config', '/project/.env.prod', '/project/id_rsa',
                     '/project/oauth-token.json', '/root/.codex/auth.json', '/project/db.sqlite3',
                     '/var/lib/marka-guardian/controller/controller.json']:
            with self.subTest(path=path), self.assertRaises(PermissionError):
                checked_path(path)
        for path in ['relative', '/project/../etc/passwd', '/project//x', '/project/./x', '/a\x00b']:
            with self.assertRaises(ValueError):
                checked_path(path)

    def test_credentials_are_removed_before_paging_and_structured_values(self):
        value = {'project': 'live', 'private_key': 'multiple words secret',
                 'nested': {'Authorization': 'Basic aGVsbG86c2VjcmV0', 'label': 'allowed'}}
        clean = scrub(json.dumps(value))
        self.assertNotIn('multiple words secret', clean)
        self.assertNotIn('aGVsbG86c2VjcmV0', clean)
        self.assertIn('allowed', clean)
        clean = scrub('DATABASE_URL=postgres://user:pass@db/data\nexport SERVICE_TOKEN="many words secret"\nproject=live')
        self.assertNotIn('user:pass', clean)
        self.assertNotIn('many words secret', clean)
        self.assertIn('project=live', clean)
        clean = scrub('password: |\n  yaml-private\nproject: live\nAPI_KEY="first-line\nsecond-line"\n')
        for secret in ['yaml-private', 'first-line', 'second-line']:
            self.assertNotIn(secret, clean)
        self.assertIn('project: live', clean)


@unittest.skipUnless(os.name == 'posix', 'host broker uses Linux descriptor traversal')
class FilesystemTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root/'project').mkdir()
        self.reader = HostReader(self.root)

    def call(self, action, path='/project', **kwargs):
        return self.reader.request({'action': action, 'path': path, 'query': '', 'offset': 0,
                                    'expected_sha256': '', **kwargs})

    def test_reads_real_code_and_paginates_hash_pinned_redacted_content(self):
        p = self.root/'project/code.py'
        p.write_text('x' * (PAGE + 80), encoding='utf-8')
        first = self.call('read', '/project/code.py')
        tail = self.call('read', '/project/code.py', offset=first['next_offset'], expected_sha256=first['sha256'])
        self.assertEqual(first['content'] + tail['content'], p.read_text())
        with self.assertRaises(ValueError):
            self.call('read', '/project/code.py', offset=PAGE)
        p.write_text('changed')
        with self.assertRaises(ValueError):
            self.call('read', '/project/code.py', expected_sha256=first['sha256'])

    def test_symlink_ancestor_final_hardlink_fifo_and_binary_are_denied(self):
        (self.root/'outside').mkdir()
        target = self.root/'outside/plain.txt'
        target.write_text('private')
        (self.root/'project/alias').symlink_to(self.root/'outside', target_is_directory=True)
        (self.root/'project/file.txt').symlink_to(target)
        os.link(target, self.root/'project/hard.txt')
        os.mkfifo(self.root/'project/pipe')
        (self.root/'project/blob').write_bytes(b'\0binary')
        for path in ['alias/plain.txt', 'file.txt', 'hard.txt', 'pipe', 'blob']:
            with self.subTest(path=path), self.assertRaises((OSError, ValueError)):
                self.call('read', '/project/' + path)

    def test_listing_search_and_read_never_change_source(self):
        (self.root/'project/README.md').write_text('project description')
        (self.root/'project/.env').write_text('SECRET=private')
        before = {p.name: p.read_bytes() for p in (self.root/'project').iterdir()}
        listing = self.call('list')
        self.assertEqual(listing['total'], 2)
        self.assertEqual(next(x for x in listing['entries'] if x['name'] == '.env')['kind'], 'restricted')
        search = self.call('search', query='readme')
        self.assertEqual([x['path'] for x in search['matches']], ['/project/README.md'])
        self.assertFalse(search['incomplete'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root/'project').iterdir()})

    def test_directory_pagination_requires_hash(self):
        for i in range(102):
            (self.root/'project'/str(i)).write_text('file')
        first = self.call('list')
        self.assertEqual(first['next_offset'], 100)
        second = self.call('list', offset=100, expected_sha256=first['sha256'])
        self.assertEqual(len(second['entries']), 2)
        (self.root/'project/new').write_text('new')
        with self.assertRaises(ValueError):
            self.call('list', offset=100, expected_sha256=first['sha256'])


class BridgeHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_bridge_forwards_only_fixed_read_protocol_and_refuses_commands(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = configuration(root)
            cfg['host_reader_socket'] = '/host-reader/reader.sock'
            bridge = Bridge(cfg, telegram=FakeTelegram(), provider=FakeProvider())
            request = {'op': 'server.files', 'action': 'read', 'path': '/project/README.md',
                       'query': '', 'offset': 0, 'expected_sha256': ''}
            with patch('marka.host_read.host_rpc', return_value={'content': 'project'}) as rpc:
                result = await bridge._dispatch(request)
                self.assertEqual(result['content'], 'project')
                self.assertEqual(rpc.call_args.args[0], cfg['host_reader_socket'])
                with self.assertRaises(Rejected):
                    await bridge._dispatch(request | {'command': 'touch /tmp/change'})
                self.assertEqual(rpc.call_count, 1)


class InspectionContentionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = support.GuardianTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.g = self.fixture.controller
        self.fixture.now += 10
        self.fixture.heartbeat()

    def busy(self):
        error = sqlite3.OperationalError('private diagnostic')
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        return error

    def test_temporary_busy_does_not_roll_back_live_bot_but_persistent_does(self):
        with patch.object(support.guardian, 'db_fingerprint', side_effect=self.busy()):
            self.g.tick()
            self.assertEqual(self.g.state['phase'], 'accepted')
            self.fixture.now += 11
            self.fixture.heartbeat()
            self.g.tick()
            self.assertEqual(self.g.state['phase'], 'rolling_back')
        self.assertEqual(self.g.state['last_inspection_error']['sqlite_errorcode'], sqlite3.SQLITE_BUSY)

    def test_success_resets_contention_deadline(self):
        with patch.object(support.guardian, 'db_fingerprint', side_effect=self.busy()):
            self.g.healthy(support.BASE)
        self.assertIn('inspection_busy_since', self.g.state)
        self.assertTrue(self.g.healthy(support.BASE)[0])
        self.assertNotIn('inspection_busy_since', self.g.state)

    def test_busy_does_not_mask_dead_heartbeat(self):
        self.fixture.now += 100
        with patch.object(support.guardian, 'db_fingerprint', side_effect=self.busy()):
            self.g.tick()
        self.assertEqual(self.g.state['phase'], 'rolling_back')
