"""Bounded daily snapshots of canonical SQLite, never credentials or search indexes."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time


_KEY = 'automatic_database_backup'
_NAME = re.compile(r'\d{4}-\d{2}-\d{2}\.sqlite3')


class DailyBackups:
    def __init__(self, store, data_dir: Path, *, keep=7):
        if type(keep) is not int or not 1 <= keep <= 31:
            raise ValueError('Keep 1–31 daily database backups')
        self.store = store
        self.root = Path(data_dir).resolve()
        self.directory = self.root / 'backups' / 'automatic'
        self.keep = keep

    def status(self):
        value = self.store.get_meta(_KEY, {})
        return value if isinstance(value, dict) else {}

    def _claim(self, now):
        with self.store._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM meta WHERE key=?', (_KEY,)).fetchone()
            state = json.loads(row[0]) if row else {}
            if state.get('next_attempt_at', 0) > now:
                return None
            state.update(state='running', last_attempt_at=now, next_attempt_at=now + 3600)
            db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (_KEY, json.dumps(state)))
            return state

    def _prepare_directory(self):
        for path in (self.root / 'backups', self.directory):
            if path.is_symlink():
                raise ValueError('Backup directories must not be symlinks')
            path.mkdir(exist_ok=True, mode=0o700)
            path.chmod(0o700)
        if self.directory.resolve().parent != (self.root / 'backups'):
            raise ValueError('Invalid backup directory')

    def _snapshot(self, target, partial):
        # The stable daily partial belongs only to this component. A previous
        # crash cannot make us follow a symlink or replace an unrelated path.
        if partial.is_symlink() or target.is_symlink():
            raise ValueError('Backup files must not be symlinks')
        if partial.exists():
            if not partial.is_file():
                raise ValueError('Invalid partial backup')
            partial.unlink()
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        deadline = time.monotonic() + 45

        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError('Database snapshot exceeded its time budget')

        try:
            with self.store._connect() as source, closing(sqlite3.connect(partial)) as destination:
                source.backup(destination, pages=128, progress=progress, sleep=0.01)
                destination.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('Snapshot integrity check failed')
            if time.monotonic() > deadline:
                raise TimeoutError('Database snapshot exceeded its time budget')
            with partial.open('r+b') as stream:
                os.fsync(stream.fileno())
            partial.replace(target)
            target.chmod(0o600)
        finally:
            partial.unlink(missing_ok=True)

    def run_due(self, *, now=None):
        now = time.time() if now is None else float(now)
        state = self._claim(now)
        if state is None:
            return {'state': 'not_due'}
        try:
            self._prepare_directory()
            # page_count includes committed pages still in WAL; stat(mainfile)
            # can dramatically underestimate a busy database before checkpoint.
            with self.store._connect() as db:
                size = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
            required = size + 512 * 1024 * 1024 + max(64 * 1024 * 1024, size // 10)
            if shutil.disk_usage(self.directory).free < required:
                state.update(state='deferred', error='insufficient_disk_space')
                self.store.set_meta(_KEY, state)
                return state
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            target = self.directory / (day + '.sqlite3')
            partial = self.directory / (day + '.partial')
            self._snapshot(target, partial)
            # Rotate only completed files owned by this component's exact naming
            # contract. Manual backups, unknown names and symlinks stay untouched.
            candidates = sorted((p for p in self.directory.iterdir()
                                 if _NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()),
                                key=lambda p: p.name, reverse=True)
            for old in candidates[self.keep:]:
                old.unlink()
            state.update(state='ok', last_success_at=now, filename=target.name,
                         bytes=target.stat().st_size, retained=min(len(candidates), self.keep),
                         next_attempt_at=(int(now) // 86400 + 1) * 86400)
            state.pop('error', None)
        except (OSError, ValueError, sqlite3.Error, TimeoutError) as exc:
            state.update(state='failed', error=type(exc).__name__)
        self.store.set_meta(_KEY, state)
        return state
