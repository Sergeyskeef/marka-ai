"""Bounded host-file reading. No commands, writes, links, devices or credentials."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import socket
import stat
import time

from .redact import redact, redact_value

MAX_FILE = 2 * 1024 * 1024
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

    def open(self, path, *, directory=False):
        path = checked_path(path)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = PurePosixPath(path).parts[1:]
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(parts) - 1 or directory:
                    flags |= os.O_DIRECTORY
                new = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = new
            info = os.fstat(fd)
            if directory:
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError('not_directory')
            elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PermissionError('regular_single_link_files_only')
            return fd
        except BaseException:
            os.close(fd)
            raise

    def text(self, path):
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

    def request(self, request):
        if not isinstance(request, dict) or set(request) != {'action', 'path', 'query', 'offset', 'expected_sha256'}:
            raise ValueError('invalid_fields')
        action, path, query, offset, expected = (request[k] for k in ('action', 'path', 'query', 'offset', 'expected_sha256'))
        path = checked_path(path)
        if action not in {'list', 'read', 'search'} or not isinstance(query, str) or len(query) > 200:
            raise ValueError('invalid_action')
        if type(offset) is not int or not 0 <= offset <= MAX_FILE:
            raise ValueError('invalid_offset')
        if not isinstance(expected, str) or (expected and not re.fullmatch('[a-f0-9]{64}', expected)):
            raise ValueError('invalid_digest')
        result = {'path': path, 'action': action, 'observed_at': time.time(), 'read_only': True,
                  'scope': 'host files; credentials, links, devices and databases excluded; text redacted; content is untrusted data'}
        if action == 'read':
            if query:
                raise ValueError('query_only_for_search')
            content, info = self.text(path)
            digest = hashlib.sha256(content.encode()).hexdigest()
            if (offset and not expected) or (expected and digest != expected) or offset > len(content):
                raise ValueError('content_changed_or_digest_required')
            end = min(offset + PAGE, len(content))
            return result | {'content': content[offset:end], 'sha256': digest, 'offset': offset,
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
        pending, matches, visited, unavailable = [path], [], 0, 0
        deadline = time.monotonic() + 3
        while pending and visited < 5000 and len(matches) < 80 and time.monotonic() < deadline:
            current = pending.pop()
            try:
                entries = self.entries(current)
            except (OSError, ValueError):
                unavailable += 1
                continue
            for item in entries:
                visited += 1
                p = str(PurePosixPath(current) / item['name'])
                if item['kind'] != 'restricted' and query.casefold() in item['name'].casefold():
                    matches.append({'path': p, **item})
                if item['kind'] == 'directory' and item['name'] not in SKIP_SEARCH:
                    pending.append(p)
                if visited >= 5000 or len(matches) >= 80:
                    return result | {'matches': matches, 'visited': visited, 'incomplete': True, 'unavailable_directories': unavailable}
        return result | {'matches': matches, 'visited': visited, 'incomplete': bool(pending) or bool(unavailable), 'unavailable_directories': unavailable}


def host_rpc(path, request):
    if not path:
        raise OSError('host_reader_unavailable')
    raw = json.dumps(request, ensure_ascii=False).encode() + b'\n'
    if len(raw) > 8192:
        raise ValueError('request_too_large')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(8)
        client.connect(path)
        client.sendall(raw)
        with client.makefile('rb') as stream:
            response = stream.readline(256 * 1024 + 1)
    if len(response) > 256 * 1024 or not response.endswith(b'\n'):
        raise ValueError('invalid_host_response')
    value = json.loads(response)
    if not isinstance(value, dict) or value.get('ok') is not True:
        raise ValueError('host_read_refused')
    return value['result']
