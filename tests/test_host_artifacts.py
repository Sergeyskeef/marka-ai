"""Host artifacts stay bounded, hash-pinned and separate from model text."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from marka.bridge import Bridge, Rejected
from marka.bridge_client import BridgeError, server_fetch
from marka.host_read import HostReader, MAX_EXPORT, MAX_FILE
from marka.tools import Workspace
from test_bridge import FakeProvider, FakeTelegram, configuration


def sha(data):
    return hashlib.sha256(data).hexdigest()


def export_receipt(data, path='/project/report.pdf', *, source=None):
    return {'source_path': path, 'source_sha256': sha(data if source is None else source),
            'sha256': sha(data), 'bytes': len(data), 'mime_type': 'application/pdf',
            'content_base64': base64.b64encode(data).decode('ascii'),
            'source_modified_at': 100, 'observed_at': 200, 'text_redacted': False}


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'O_PATH'),
                     'host artifacts require Linux descriptor-relative traversal')
class HostArtifactTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.reader = HostReader(self.root)

    def call(self, action, path='/project', **kwargs):
        return self.reader.request({'action': action, 'path': path, 'query': '',
                                    'offset': 0, 'expected_sha256': '', **kwargs})

    def populate(self, count=135, *, content='ordinary content'):
        for index in range(count):
            (self.project / f'match-{index:03}.txt').write_text(content, encoding='utf-8')

    def test_export_binary_over_read_limit_is_exact_and_hash_pinned(self):
        data = b'%PDF-1.7\n' + bytes(range(256)) * 8193
        self.assertGreater(len(data), MAX_FILE)
        target = self.project / 'report.pdf'
        target.write_bytes(data)
        before = target.stat()
        result = self.call('fetch', '/project/report.pdf', expected_sha256=sha(data))
        self.assertEqual(base64.b64decode(result['content_base64'], validate=True), data)
        self.assertEqual((result['source_sha256'], result['sha256']), (sha(data), sha(data)))
        self.assertEqual(result['bytes'], len(data))
        self.assertEqual(result['mime_type'], 'application/pdf')
        self.assertFalse(result['text_redacted'])
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(target.stat().st_mtime_ns, before.st_mtime_ns)
        with self.assertRaisesRegex(ValueError, 'file_too_large'):
            self.call('read', '/project/report.pdf')
        with self.assertRaisesRegex(ValueError, 'source_digest_changed'):
            self.call('fetch', '/project/report.pdf', expected_sha256='0' * 64)

    def test_read_then_fetch_minified_json_uses_original_digest_and_masks_values(self):
        canary = 'synthetic-private-json-value'
        original = json.dumps({'label': 'keep visible', 'nested': {'api_key': canary}},
                              separators=(',', ':')).encode()
        target = self.project / 'manifest.json'
        target.write_bytes(original)
        read = self.call('read', '/project/manifest.json')
        self.assertNotEqual(read['sha256'], sha(original))
        self.assertEqual(read['source_sha256'], sha(original))
        result = self.call('fetch', '/project/manifest.json', expected_sha256=read['source_sha256'])
        exported = base64.b64decode(result['content_base64'], validate=True)
        self.assertEqual(result['sha256'], sha(exported))
        self.assertEqual(result['source_sha256'], sha(original))
        self.assertNotEqual(result['sha256'], result['source_sha256'])
        self.assertTrue(result['text_redacted'])
        self.assertNotIn(canary, exported.decode())
        self.assertEqual(json.loads(exported)['label'], 'keep visible')
        self.assertEqual(json.loads(exported)['nested']['api_key'], '[REDACTED]')
        self.assertEqual(target.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'source_digest_changed'):
            self.call('fetch', '/project/manifest.json', expected_sha256=read['sha256'])

    def test_export_blocks_protected_paths_symlinks_and_hardlinks(self):
        target = self.project / 'original.pdf'
        target.write_bytes(b'%PDF-1.7\nfixture')
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'report.pdf').write_bytes(b'%PDF-1.7\nnot traversable by link')
        (self.project / 'alias').symlink_to(outside, target_is_directory=True)
        (self.project / 'linked.pdf').symlink_to(outside / 'report.pdf')
        os.link(target, self.project / 'hard.pdf')
        for path in ['/project/.env', '/etc/shadow', '/project/auth.json']:
            with self.subTest(path=path), self.assertRaises(PermissionError):
                self.call('fetch', path)
        for path in ['/project/alias/report.pdf', '/project/linked.pdf',
                     '/project/hard.pdf', '/project/original.pdf']:
            with self.subTest(path=path), self.assertRaises(OSError):
                self.call('fetch', path)
        self.assertEqual(target.read_bytes(), b'%PDF-1.7\nfixture')

    def test_export_rejects_oversize_text_binary_text_and_false_media_extension(self):
        for name, data in [('large.txt', b'x' * (MAX_FILE + 1)),
                           ('binary.txt', b'ordinary\0binary'),
                           ('fake.png', b'not an image'), ('archive.zip', b'PK\x03\x04')]:
            (self.project / name).write_bytes(data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call('fetch', '/project/' + name)
        oversized = self.project / 'oversized.pdf'
        with oversized.open('wb') as stream:
            stream.write(b'%PDF-1.7\n')
            stream.truncate(MAX_EXPORT + 1)
        with self.assertRaisesRegex(ValueError, 'export_exceeds_20_mib'):
            self.call('fetch', '/project/oversized.pdf')

    def test_stat_distinguishes_missing_existing_and_protected_without_following_links(self):
        (self.project / 'plain.txt').write_text('ordinary', encoding='utf-8')
        missing = self.call('stat', '/project/missing.txt')
        self.assertIs(missing['exists'], False)
        self.assertNotIn('kind', missing)
        existing = self.call('stat', '/project/plain.txt')
        self.assertEqual((existing['exists'], existing['kind'], existing['bytes']), (True, 'file', 8))
        self.assertEqual(self.call('stat')['kind'], 'directory')
        for path in ['/project/.env.missing', '/project/auth.json', '/etc/shadow']:
            with self.subTest(path=path), self.assertRaises(PermissionError):
                self.call('stat', path)
        (self.project / 'alias.txt').symlink_to(self.project / 'plain.txt')
        os.link(self.project / 'plain.txt', self.project / 'hard.txt')
        self.assertEqual(self.call('stat', '/project/alias.txt')['kind'], 'restricted')
        self.assertEqual(self.call('stat', '/project/hard.txt')['kind'], 'restricted')

    def test_search_more_than_sixty_continues_without_duplicates_or_gaps(self):
        self.populate()
        pages, paths, cursor = [], [], ''
        with patch('marka.host_read.time.monotonic', return_value=100):
            for _ in range(4):
                result = self.call('search', query='match-', cursor=cursor)
                pages.append(len(result['matches']))
                paths.extend(item['path'] for item in result['matches'])
                cursor = result['next_cursor']
                if not cursor:
                    self.assertFalse(result['incomplete'])
                    break
                self.assertTrue(result['incomplete'])
                self.assertEqual(result['cursor_expires_in_seconds'], 300)
                self.assertRegex(cursor, r'^[a-f0-9]{64}$')
        self.assertEqual(pages, [60, 60, 15])
        self.assertEqual(paths, [f'/project/match-{index:03}.txt' for index in range(135)])
        self.assertEqual(len(set(paths)), 135)

    def test_search_cursor_is_bound_to_query_root_mode_and_expires(self):
        self.populate(65)
        with patch('marka.host_read.time.monotonic', return_value=100):
            cursor = self.call('search', query='match-')['next_cursor']
            for changes in [{'query': 'other'}, {'path': '/'}, {'action': 'grep'}]:
                kwargs = {'action': 'search', 'path': '/project', 'query': 'match-', 'cursor': cursor}
                kwargs.update(changes)
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'cursor_expired_or_query_changed'):
                    self.call(**kwargs)
        with patch('marka.host_read.time.monotonic', return_value=401):
            with self.assertRaisesRegex(ValueError, 'cursor_expired_or_query_changed'):
                self.call('search', query='match-', cursor=cursor)

    def test_search_refuses_continuation_when_saved_directory_changed(self):
        self.populate(65)
        with patch('marka.host_read.time.monotonic', return_value=100):
            cursor = self.call('search', query='match-')['next_cursor']
            (self.project / 'match-000.txt').unlink()
            with self.assertRaisesRegex(ValueError, 'search_directory_changed'):
                self.call('search', query='match-', cursor=cursor)

    def test_unreadable_count_survives_cursor_and_final_page_stays_incomplete(self):
        self.populate(66, content='needle public text')
        original_text = self.reader.text

        def read(path):
            if path == '/project/match-000.txt':
                raise PermissionError('synthetic unreadable entry')
            return original_text(path)

        with patch.object(self.reader, 'text', side_effect=read), patch('marka.host_read.time.monotonic', return_value=100):
            first = self.call('grep', query='needle')
            self.assertEqual((len(first['matches']), first['unavailable_entries']), (60, 1))
            self.assertTrue(first['next_cursor'])
            final = self.call('grep', query='needle', cursor=first['next_cursor'])
        self.assertEqual(len(final['matches']), 5)
        self.assertIsNone(final['next_cursor'])
        self.assertEqual(final['unavailable_entries'], 1)
        self.assertTrue(final['incomplete'])

    def test_grep_filters_content_before_matching_and_never_exposes_secret_canaries(self):
        token = '1234567890:' + 'A' * 35
        private = 'synthetic-private-assignment'
        original = f'needle prefix{token}\nAPI_KEY={private}\nneedle public detail\n'
        target = self.project / 'application.log'
        target.write_text(original, encoding='utf-8')
        result = self.call('grep', query='needle')
        self.assertEqual(len(result['matches']), 1)
        self.assertEqual(len(result['matches'][0]['hits']), 2)
        self.assertTrue(result['matches'][0]['redacted_text'])
        rendered = json.dumps(result)
        self.assertNotIn(token, rendered)
        self.assertNotIn(private, rendered)
        self.assertIn('public detail', rendered)
        self.assertEqual(self.call('grep', query=private)['matches'], [])
        self.assertEqual(target.read_text(encoding='utf-8'), original)


class WorkspaceImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.workspace = Workspace(self.parent / 'workspace')
        disk = patch('shutil.disk_usage', return_value=SimpleNamespace(free=1024**3))
        disk.start()
        self.addCleanup(disk.stop)

    def test_large_artifact_import_is_exact_idempotent_and_outside_runner_limits(self):
        data = b'%PDF-1.7\n' + b'bounded-artifact\n' * 40000
        self.assertGreater(len(data), 524288)
        first = self.workspace.import_bytes('retrieved/report.pdf', data)
        self.assertEqual(first, {'path': 'retrieved/report.pdf', 'bytes': len(data),
                                 'sha256': sha(data), 'already_present': False})
        target = self.workspace.root / 'retrieved/report.pdf'
        before = target.stat().st_mtime_ns
        self.assertEqual(target.read_bytes(), data)
        again = self.workspace.import_bytes('retrieved/report.pdf', data)
        self.assertEqual(again, first | {'already_present': True})
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertEqual([p.name for p in target.parent.iterdir()], ['report.pdf'])
        with self.assertRaisesRegex(ValueError, '512 KiB'):
            self.workspace.snapshot(['retrieved/report.pdf'])

    def test_existing_different_destination_is_never_overwritten(self):
        self.workspace.import_bytes('result.txt', b'original')
        with self.assertRaisesRegex(ValueError, 'different contents'):
            self.workspace.import_bytes('result.txt', b'replaced')
        self.assertEqual((self.workspace.root / 'result.txt').read_bytes(), b'original')
        (self.workspace.root / 'directory').mkdir()
        with self.assertRaises(ValueError):
            self.workspace.import_bytes('directory', b'new')

    def test_concurrent_destination_wins_without_partial_file_or_temporary_residue(self):
        real_link = os.link

        def raced_link(source, destination):
            Path(destination).write_bytes(b'concurrent winner')
            return real_link(source, destination)

        with patch('marka.tools.os.link', side_effect=raced_link):
            with self.assertRaises(FileExistsError):
                self.workspace.import_bytes('result.pdf', b'%PDF-1.7\nnew payload')
        self.assertEqual((self.workspace.root / 'result.pdf').read_bytes(), b'concurrent winner')
        self.assertEqual([p.name for p in self.workspace.root.iterdir()], ['result.pdf'])

    def test_import_rejects_escape_hidden_and_state_paths_without_writing(self):
        outside = self.parent / 'outside.txt'
        for value in ['../outside.txt', 'nested/../../outside.txt', str(outside),
                      '.private/item.txt', 'nested/.private', 'auth.json',
                      'nested/settings.json', 'file:stream', '', 'bad\0path']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.workspace.import_bytes(value, b'fixture')
        self.assertFalse(outside.exists())
        self.assertEqual(list(self.workspace.root.iterdir()), [])

    def test_import_enforces_payload_and_free_space_bounds_before_creating_files(self):
        for data in [b'', 'not bytes', bytearray(b'not immutable'), b'x' * (MAX_EXPORT + 1)]:
            with self.subTest(kind=type(data).__name__), self.assertRaises(ValueError):
                self.workspace.import_bytes('result.bin', data)
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, 'Insufficient space'):
                self.workspace.import_bytes('nested/result.bin', b'bounded')
        self.assertEqual(list(self.workspace.root.iterdir()), [])


class BridgeArtifactTests(unittest.IsolatedAsyncioTestCase):
    async def test_files_protocol_cannot_smuggle_fetch_or_unknown_operation(self):
        with tempfile.TemporaryDirectory() as root:
            bridge = Bridge(configuration(root), telegram=FakeTelegram(), provider=FakeProvider())
            request = {'op': 'server.files', 'action': 'fetch', 'path': '/project/report.pdf',
                       'query': '', 'offset': 0, 'expected_sha256': ''}
            with patch('marka.host_read.host_rpc') as rpc:
                for action in ['fetch', 'write', ['read'], None]:
                    with self.subTest(action=action), self.assertRaises(Rejected):
                        await bridge._dispatch(request | {'action': action})
                rpc.assert_not_called()

    async def test_fetch_uses_separate_protocol_with_no_caller_injected_query(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = configuration(root) | {'host_reader_socket': '/host-reader/reader.sock'}
            bridge = Bridge(cfg, telegram=FakeTelegram(), provider=FakeProvider())
            request = {'op': 'server.fetch', 'path': '/project/report.pdf', 'expected_sha256': 'a' * 64}
            receipt = export_receipt(b'%PDF-1.7\nfixture')
            with patch('marka.host_read.host_rpc', return_value=receipt) as rpc:
                self.assertEqual(await bridge._dispatch(request), receipt)
                rpc.assert_called_once_with('/host-reader/reader.sock', {
                    'action': 'fetch', 'path': '/project/report.pdf', 'expected_sha256': 'a' * 64,
                    'query': '', 'offset': 0})
                with self.assertRaises(Rejected):
                    await bridge._dispatch(request | {'query': 'unapproved'})
                self.assertEqual(rpc.call_count, 1)

    async def test_client_verifies_export_and_returns_metadata_without_binary(self):
        data = b'%PDF-1.7\nfixture'
        receipt = export_receipt(data)
        with patch('marka.bridge_client._rpc', new_callable=AsyncMock, return_value=receipt) as rpc:
            actual, metadata = await server_fetch('/fixture.sock', '/project/report.pdf', expected_sha256=sha(data))
        self.assertEqual(actual, data)
        self.assertEqual(metadata, {k: v for k, v in receipt.items() if k != 'content_base64'})
        rpc.assert_awaited_once_with('/fixture.sock', {'op': 'server.fetch',
            'path': '/project/report.pdf', 'expected_sha256': sha(data)}, timeout=30)

    async def test_client_verifies_original_and_redacted_hashes_separately(self):
        original = b'{"api_key":"synthetic-private-canary","label":"visible"}'
        exported = b'{"api_key":"[REDACTED]","label":"visible"}'
        receipt = export_receipt(exported, '/project/manifest.json', source=original)
        receipt.update(mime_type='text/plain; charset=utf-8', text_redacted=True)
        with patch('marka.bridge_client._rpc', new_callable=AsyncMock, return_value=receipt):
            data, metadata = await server_fetch('/fixture.sock', '/project/manifest.json',
                                                expected_sha256=sha(original))
        self.assertEqual(data, exported)
        self.assertEqual(metadata['source_sha256'], sha(original))
        self.assertEqual(metadata['sha256'], sha(exported))

    async def test_client_rejects_digest_size_path_and_original_hash_mismatches(self):
        data = b'%PDF-1.7\nfixture-private-payload'
        receipt = export_receipt(data)
        for changes in [{'content_base64': base64.b64encode(data + b'changed').decode()},
                        {'bytes': len(data) + 1}, {'sha256': '0' * 64},
                        {'source_path': '/project/other.pdf'}, {'source_sha256': '0' * 64},
                        {'content_base64': '!!invalid fixture encoding!!'}]:
            with self.subTest(fields=tuple(changes)), patch('marka.bridge_client._rpc',
                    new_callable=AsyncMock, return_value=receipt | changes):
                with self.assertRaises(BridgeError) as rejected:
                    await server_fetch('/fixture.sock', '/project/report.pdf', expected_sha256=sha(data))
                self.assertNotIn('fixture-private-payload', str(rejected.exception))


if __name__ == '__main__':
    unittest.main()
