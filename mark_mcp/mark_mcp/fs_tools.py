"""Filesystem helper functions exposed via the MCP tools layer."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path
from typing import List, Tuple

from fastapi import HTTPException

from .config import settings
from .repo_tools import ensure_prechange_snapshot


_ALLOW: List[Path] = [Path(p).resolve() for p in settings.allow_paths if p]
_PENDING_WRITES: dict[str, Tuple[Path, bytes]] = {}


def _is_allowed(path: Path) -> bool:
    """Check if the requested path is within one of the allow-listed roots."""

    try:
        res = path.resolve()
        return any(res.is_relative_to(base) for base in _ALLOW)
    except Exception:
        return False


async def fs_glob(pattern: str, root: str | None = None) -> list[str]:
    """Return files matching ``pattern`` respecting the allow-list."""

    if root:
        root_path = Path(root)
        if not _is_allowed(root_path):
            raise HTTPException(status_code=403, detail="Root not allowed")
        bases: List[Path] = [root_path]
    else:
        bases = list(_ALLOW)

    items: list[str] = []
    for base in bases:
        for r, dnames, fnames in os.walk(base):
            for name in fnames + dnames:
                full = os.path.join(r, name)
                rel = os.path.relpath(full, base)
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(full, pattern):
                    items.append(full)
                    if len(items) >= settings.max_glob_items:
                        return items
    return items


async def fs_read(path: str, max_bytes: int | None = None) -> str:
    """Read a file from the allow-list with an optional size limit."""

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(status_code=403, detail="Path not allowed")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    limit = max_bytes or settings.max_read_bytes
    data = await asyncio.to_thread(p.read_bytes)
    return data[:limit].decode("utf-8", errors="replace")


async def security_request_write(path: str, content: str) -> dict:
    """Request approval for a write operation (two-step write flow)."""

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(status_code=403, detail="Path not allowed")
    request_id = os.urandom(8).hex()
    _PENDING_WRITES[request_id] = (p, content.encode("utf-8"))
    return {"request_id": request_id, "dry_run": True, "path": str(p)}


async def confirm_write(request_id: str, allow: bool) -> dict:
    """Apply or discard a pending write request."""

    item = _PENDING_WRITES.pop(request_id, None)
    if not item:
        raise HTTPException(status_code=404, detail="Pending request not found")
    p, data = item
    if not allow:
        return {"request_id": request_id, "applied": False}
    p.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(p.write_bytes, data)
    return {"request_id": request_id, "applied": True, "path": str(p)}


async def fs_write(path: str, content: str, mode: str = "w") -> dict:
    """Write a file after taking a pre-change snapshot."""

    p = Path(path)
    if not _is_allowed(p):
        raise HTTPException(status_code=403, detail="Path not allowed")
    await ensure_prechange_snapshot()
    p.parent.mkdir(parents=True, exist_ok=True)
    if "b" in mode:
        data = content.encode("utf-8")
        await asyncio.to_thread(p.write_bytes, data)
    else:
        await asyncio.to_thread(p.write_text, content, "utf-8")
    return {"path": str(p), "bytes": len(content.encode("utf-8")), "mode": mode}
