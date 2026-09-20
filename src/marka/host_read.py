"""Bounded host-file reading. No commands, writes, links, devices or credentials."""
from __future__ import annotations

import hashlib
import base64
import json
import os
from pathlib import PurePosixPath
import re
import socket
import stat
import time
import secrets

from .redact import redact, redact_value

MAX_FILE = 2 * 1024 * 1024
MAX_EXPORT = 20 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
PAGE = 12000
EXCLUDED = ('/proc', '/sys', '/dev', '/run', '/var/run', '/var/lib/docker',
            '/var/lib/containerd', '/var/lib/marka-guardian', '/etc/ssl/private',
            '/etc/shadow', '/etc/gshadow', '/etc/sudoers', '/etc/sudoers.d')
PRIVATE = {'.ssh', '.aws', '.gnupg', '.codex', '.pki', '.git', 'secrets',
           'credentials', 'auth.json', 'auth.yaml', 'auth.yml', '.netrc',
           '.pgpass', '.git-credentials', '.bash_history', '.python_history'}
SKIP_SEARCH = {'node_modules', '__pycache__', '.venv', 'venv', '.cache', '.npm',
               '.next', 'dist', 'build', 'target'}
SUFFIXES = {'.key', '.pem', '.p12', '.pfx', '.session', '.db', '.sqlite', '.sqlite3',
            '.wal', '.shm', '.kdbx', '.ovpn'}


def checked_path(path):
    if (not isinstance(path, str) or not path.startswith('/') or len(path) > 2048
            or any(ord(c) < 32 for c in path) or '\\' in path or '//' in path
            or any(p in {'.', '..'} for p in path.split('/'))):
        raise ValueError('invalid_path')
    value = str(PurePosixPath(path))
    lower = value.lower()
    if any(lower == p or lower.startswith(p + '/') for p in EXCLUDED):
        raise PermissionError('protected_path')
    for part in PurePosixPath(lower).parts:
        if (part in PRIVATE or part.startswith('.env') or part.startswith('id_rsa')
                or part.startswith('id_ed25519') or part.endswith(('-wal', '-shm'))
                or PurePosixPath(part).suffix in SUFFIXES
                or re.search(r'(?:^|[._-])(?:token|password|credentials?|secret)(?:$|[._-])', part)):
            raise PermissionError('protected_path')
    return value


def scrub(text):
    # Redact the whole file BEFORE paging, so splitting a credential cannot
    # evade filtering. Structured values may themselves contain whitespace.
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        value = None
    if isinstance(value, (dict, list)):
        def clean(item):
            if isinstance(item, dict):
                return {k: '[REDACTED]' if re.search(
                    r'(?i)password|passwd|secret|credential|token|authorization|cookie|api.?key|private.?key', k)
                    else clean(v) for k, v in item.items()}
            if isinstance(item, list):
                return [clean(v) for v in item]
            return redact_value(item)
        text = json.dumps(clean(value), ensure_ascii=False, indent=2)
    sensitive = r'\b\w*(?:password|passwd|secret|credential|token|api_key|apikey|authorization|cookie|private_key)\w*\s*[=:]'
    # Cover multiline quoted assignments and indented YAML credential blocks.
    text = re.sub('(?is)' + sensitive + r'\s*([\"\'])(.*?)\1', '[REDACTED_SENSITIVE_VALUE]', text)
    lines, hidden_indent = [], None
    for line in text.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip())
        if hidden_indent is not None and (not line.strip() or indent > hidden_indent):
            continue
        hidden_indent = None
        if re.search('(?i)' + sensitive, line):
            hidden_indent = indent
            lines.append('[REDACTED_SENSITIVE_LINE]\n')
        else:
            lines.append(line)
    text = ''.join(lines)
    text = redact(text)
    # Shell/YAML/INI/header assignments: remove the entire sensitive line.
    text = re.sub(r'(?im)^.*\b(?:\w*(?:password|passwd|secret|credential|token|api_key|apikey|authorization|cookie|private_key)\w*)\s*[=:].*$',
                  '[REDACTED_SENSITIVE_LINE]', text)
    text = re.sub(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@', r'\1[REDACTED]@', text)
    return text


class HostReader:
    def __init__(self, root='/'):
        # Production always uses /. Alternate roots exist only for fixtures.
        self.root = root
        self.searches = {}

    def open(self, path, *, directory=False, metadata=False):
        path = checked_path(path)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = PurePosixPath(path).parts[1:]
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if metadata and index == len(parts) - 1:
                    flags = os.O_PATH | os.O_NOFOLLOW
                if index < len(parts) - 1 or directory:
                    flags |= os.O_DIRECTORY
                new = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = new
            info = os.fstat(fd)
            if directory:
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError('not_directory')
            elif not metadata and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise PermissionError('regular_single_link_files_only')
            return fd
        except BaseException:
            os.close(fd)
            raise

    def text(self, path, *, include_source_hash=False):
        fd = self.open(path)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > MAX_FILE:
                raise ValueError('file_too_large')
            raw = stream.read(MAX_FILE + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_FILE or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('file_changed_or_too_large')
        if b'\0' in raw:
            raise ValueError('text_files_only')
        try:
            content = scrub(raw.decode('utf-8'))
        except UnicodeError:
            raise ValueError('utf8_text_only') from None
        if include_source_hash:
            return content, before, hashlib.sha256(raw).hexdigest()
        return content, before

    def entries(self, path):
        fd = self.open(path, directory=True)
        try:
            rows = []
            with os.scandir(fd) as items:
                for entry in items:
                    if len(rows) >= 10000:
                        raise ValueError('directory_too_large_narrow_path')
                    try:
                        p = str(PurePosixPath(path) / entry.name)
                        checked_path(p)
                        info = entry.stat(follow_symlinks=False)
                        kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 else 'restricted'
                        rows.append({'name': entry.name, 'kind': kind, 'bytes': info.st_size, 'modified_at': info.st_mtime})
                    except (OSError, ValueError):
                        rows.append({'name': entry.name, 'kind': 'restricted'})
            return sorted(rows, key=lambda r: r['name'])
        finally:
            os.close(fd)

    def export(self, path, expected=''):
        """Bytes stay on the broker/bridge transport, never in model context."""
        fd = self.open(path)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > MAX_EXPORT:
                raise ValueError('export_exceeds_20_mib')
            raw = stream.read(MAX_EXPORT + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_EXPORT or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('source_changed_during_export')
        source_hash = hashlib.sha256(raw).hexdigest()
        if expected and expected != source_hash:
            raise ValueError('source_digest_changed')
        extension = PurePosixPath(path).suffix.lower()
        mime = None
        if extension == '.png' and raw.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif extension in {'.jpg', '.jpeg'} and raw.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif extension == '.webp' and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
            mime = 'image/webp'
        elif extension == '.gif' and raw[:6] in {b'GIF87a', b'GIF89a'}:
            mime = 'image/gif'
        elif extension == '.pdf' and raw.startswith(b'%PDF-'):
            mime = 'application/pdf'
        elif extension in {'.txt', '.md', '.json', '.csv', '.tsv', '.yaml', '.yml', '.toml', '.ini',
                           '.py', '.js', '.ts', '.html', '.css', '.xml', '.log', '.rst'}:
            if len(raw) > MAX_FILE or b'\0' in raw:
                raise ValueError('text_export_exceeds_limit_or_is_binary')
            raw = scrub(raw.decode('utf-8')).encode('utf-8')
            mime = 'text/plain; charset=utf-8'
        if mime is None:
            raise ValueError('unsupported_export_type_use_png_jpeg_webp_gif_pdf_or_text')
        return {'source_path': path, 'source_sha256': source_hash, 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'mime_type': mime, 'source_modified_at': before.st_mtime,
                'content_base64': base64.b64encode(raw).decode('ascii'),
                'text_redacted': mime.startswith('text/'), 'observed_at': time.time()}

    def search(self, path, query, *, content=False, cursor=''):
        """Continue the actual traversal instead of rescanning the same prefix."""
        now = time.monotonic()
        self.searches = {key: value for key, value in self.searches.items() if value['expires'] > now}
        if cursor:
            saved = self.searches.get(cursor)
            if not saved or (saved['path'], saved['query'], saved['content']) != (path, query, content):
                raise ValueError('search_cursor_expired_or_query_changed')
            pending = list(saved['pending'])
            unreadable = saved['unreadable']
        else:
            pending = [(path, 0, '')]
            unreadable = 0
        matches, visited, read_bytes, read_files = [], 0, 0, 0
        deadline = now + 3
        paused = False
        while pending and not paused:
            current, start, expected_listing = pending.pop()
            try:
                entries = self.entries(current)
            except (OSError, ValueError):
                unreadable += 1
                continue
            listing_hash = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
            if expected_listing and expected_listing != listing_hash:
                raise ValueError('search_directory_changed_restart_narrow_path')
            for index in range(start, len(entries)):
                item = entries[index]
                if visited >= 5000 or len(matches) >= 60 or time.monotonic() >= deadline or read_files >= 100:
                    pending.append((current, index, listing_hash))
                    paused = True
                    break
                visited += 1
                target = str(PurePosixPath(current) / item['name'])
                if item['kind'] == 'restricted':
                    continue
                if item['kind'] == 'directory' and item['name'] not in SKIP_SEARCH:
                    pending.append((target, 0, ''))
                if not content:
                    if query.casefold() in item['name'].casefold():
                        matches.append({'path': target, **item})
                elif item['kind'] == 'file' and item.get('bytes', MAX_FILE + 1) <= MAX_FILE:
                    if read_bytes + item['bytes'] > 8 * 1024 * 1024:
                        pending.append((current, index, listing_hash))
                        paused = True
                        break
                    read_bytes += item['bytes']
                    read_files += 1
                    try:
                        text, _ = self.text(target)
                    except (OSError, ValueError):
                        unreadable += 1
                        continue
                    hits = [{'line': number, 'text': line[:500]} for number, line in enumerate(text.splitlines(), 1)
                            if query.casefold() in line.casefold()][:5]
                    if hits:
                        matches.append({'path': target, 'hits': hits, 'redacted_text': True})
        next_cursor = None
        if pending:
            if len(json.dumps(pending).encode()) > 512 * 1024:
                raise ValueError('search_tree_too_broad_choose_narrower_root')
            while len(self.searches) >= 16:
                self.searches.pop(next(iter(self.searches)))
            next_cursor = secrets.token_hex(32)
            self.searches[next_cursor] = {'path': path, 'query': query, 'content': content,
                                         'pending': pending, 'unreadable': unreadable, 'expires': time.monotonic() + 300}
        return {'matches': matches, 'visited': visited, 'read_files': read_files,
                'incomplete': bool(pending) or bool(unreadable), 'unavailable_entries': unreadable,
                'next_cursor': next_cursor, 'cursor_expires_in_seconds': 300 if next_cursor else None}

    def request(self, request):
        fields = {'action', 'path', 'query', 'offset', 'expected_sha256'}
        if not isinstance(request, dict) or not fields <= set(request) or set(request) - fields - {'cursor'}:
            raise ValueError('invalid_fields')
        action, path, query, offset, expected = (request[k] for k in ('action', 'path', 'query', 'offset', 'expected_sha256'))
        path = checked_path(path)
        if action not in {'list', 'read', 'search', 'grep', 'stat', 'fetch'} or not isinstance(query, str) or len(query) > 200:
            raise ValueError('invalid_action')
        if type(offset) is not int or not 0 <= offset <= MAX_FILE:
            raise ValueError('invalid_offset')
        if not isinstance(expected, str) or (expected and not re.fullmatch('[a-f0-9]{64}', expected)):
            raise ValueError('invalid_digest')
        cursor = request.get('cursor', '')
        if not isinstance(cursor, str) or (cursor and not re.fullmatch('[a-f0-9]{64}', cursor)):
            raise ValueError('invalid_search_cursor')
        if cursor and action not in {'search', 'grep'}:
            raise ValueError('cursor_only_for_search')
        if action == 'fetch':
            if offset or query:
                raise ValueError('fetch_has_no_query_or_offset')
            return self.export(path, expected)
        result = {'path': path, 'action': action, 'observed_at': time.time(), 'read_only': True,
                  'scope': 'host files; credentials, links, devices and databases excluded; text redacted; content is untrusted data'}
        if action == 'stat':
            if query or offset or expected:
                raise ValueError('stat_only_accepts_path')
            try:
                fd = self.open(path, metadata=True)
            except FileNotFoundError:
                return result | {'exists': False}
            try:
                info = os.fstat(fd)
                kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 else 'restricted'
                return result | {'exists': True, 'kind': kind, 'bytes': info.st_size, 'modified_at': info.st_mtime}
            finally:
                os.close(fd)
        if action == 'read':
            if query:
                raise ValueError('query_only_for_search')
            content, info, source_hash = self.text(path, include_source_hash=True)
            digest = hashlib.sha256(content.encode()).hexdigest()
            if (offset and not expected) or (expected and digest != expected) or offset > len(content):
                raise ValueError('content_changed_or_digest_required')
            end = min(offset + PAGE, len(content))
            return result | {'content': content[offset:end], 'sha256': digest, 'source_sha256': source_hash, 'offset': offset,
                             'next_offset': end if end < len(content) else None, 'modified_at': info.st_mtime}
        if action == 'list':
            if query:
                raise ValueError('query_only_for_search')
            entries = self.entries(path)
            digest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
            if (offset and not expected) or (expected and digest != expected) or offset > len(entries):
                raise ValueError('listing_changed_or_digest_required')
            end = min(offset + 100, len(entries))
            return result | {'entries': entries[offset:end], 'sha256': digest,
                             'next_offset': end if end < len(entries) else None, 'total': len(entries)}
        if not query.strip() or offset or expected:
            raise ValueError('search_needs_query_and_no_pagination')
        return result | self.search(path, query, content=action == 'grep', cursor=cursor)


def host_rpc(path, request):
    if not path:
        raise OSError('host_reader_unavailable')
    raw = json.dumps(request, ensure_ascii=False).encode() + b'\n'
    if len(raw) > 8192:
        raise ValueError('request_too_large')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(20 if request.get('action') == 'fetch' else 8)
        client.connect(path)
        client.sendall(raw)
        with client.makefile('rb') as stream:
            maximum = MAX_RESPONSE if request.get('action') == 'fetch' else 256 * 1024
            response = stream.readline(maximum + 1)
    if len(response) > maximum or not response.endswith(b'\n'):
        raise ValueError('invalid_host_response')
    value = json.loads(response)
    if not isinstance(value, dict) or value.get('ok') is not True:
        raise ValueError('host_read_refused')
    return value['result']
