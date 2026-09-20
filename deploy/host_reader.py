#!/usr/bin/env python3
"""Root-owned local broker. Fixed protocol, bridge UID only, no shell operations."""
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marka.host_read import HostReader


def serve(directory='/var/lib/marka-host-reader'):
    root = Path(directory)
    root.mkdir(mode=0o750, exist_ok=True)
    os.chown(root, 0, 10001)
    logger = logging.getLogger('host-reader-audit')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(root / 'audit.jsonl', maxBytes=2*1024*1024, backupCount=2)
    logger.addHandler(handler)
    path = root / 'reader.sock'
    path.unlink(missing_ok=True)
    reader = HostReader()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        os.chown(path, 0, 10001)
        path.chmod(0o660)
        server.listen(4)
        while True:
            client, _ = server.accept()
            with client:
                client.settimeout(4)
                pid, uid, gid = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                request, ok, result = {}, False, None
                try:
                    if uid != 10002:
                        raise PermissionError('bridge_uid_required')
                    with client.makefile('rb') as stream:
                        raw = stream.readline(8193)
                    if len(raw) > 8192 or not raw.endswith(b'\n'):
                        raise ValueError('invalid_frame')
                    request = json.loads(raw)
                    result = reader.request(request)
                    ok = True
                except (OSError, ValueError, TypeError, RecursionError):
                    pass
                # Never put file contents or possibly credential-bearing query
                # text into audit. Paths are hashed for correlation, too.
                fields = request if isinstance(request, dict) else {}
                action = fields.get('action')
                logger.info(json.dumps({'at': time.time(), 'uid': uid, 'ok': ok,
                    'action': action if isinstance(action, str) and action in {'read','list','search'} else 'invalid',
                    'path_sha256': hashlib.sha256(str(fields.get('path', '')).encode()).hexdigest()}))
                response = {'ok': True, 'result': result} if ok else {'ok': False, 'error': 'refused_or_unavailable'}
                try:
                    payload = json.dumps(response, ensure_ascii=False).encode()
                    if len(payload) > 256*1024:
                        payload = b'{"ok":false,"error":"response_too_large"}'
                    client.sendall(payload + b'\n')
                except OSError:
                    pass


if __name__ == '__main__':
    serve()
