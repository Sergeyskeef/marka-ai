"""Filesystem helper functions exposed via the MCP tools layer."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from fastapi import HTTPException

from .config import settings
from .repo_tools import ensure_prechange_snapshot


_ALLOW: Tuple[Path, ...] = tuple(Path(p).resolve() for p in settings.allow_paths)
_PENDING_WRITES: Dict[str, Tuple[Path, bytes]] = {}


def _is_allowed(path: Path) -> bool:
    """Check if the requested path is within one of the allow-listed roots."""

    try:
        resolved = path.resolve()
    except Exception:
        return False
    return any(resolved.is_relative_to(base) for base in _ALLOW)


async def _walk_glob(bases: Iterable[Path], pattern: str, limit: int) -> List[str]:
    """Collect glob matches in a background thread to avoid blocking the loop."""

    def _collect() -> List[str]:
        matches: List[str] = []
        for base in bases:
            if not base.exists():
                continue
            for root, dnames, fnames in os.walk(base):
                for name in [*dnames, *fnames]:
                    full = Path(root) / name
                    rel = full.relative_to(base)
                    if fnmatch.fnmatch(rel.as_posix(), pattern) or fnmatch.fnmatch(
                        full.as_posix(), pattern
                    ):
                        matches.append(str(full))
                        if len(matches) >= limit:
                            return matches
        return matches

    return await asyncio.to_thread(_collect)


async def fs_glob(pattern: str, root: str | None = None) -> List[str]:
    """Return files matching ``pattern`` respecting the allow-list."""

    if root is not None:
        root_path = Path(root)
        if not _is_allowed(root_path):
            raise HTTPException(status_code=403, detail="Root not allowed")
        bases: Tuple[Path, ...] = (root_path.resolve(),)
    else:
        bases = _ALLOW

    return await _walk_glob(bases, pattern, settings.max_glob_items)


async def fs_read(path: str, max_bytes: int | None = None) -> str:
    """Read a file from the allow-list with an optional size limit."""

    file_path = Path(path)
    if not _is_allowed(file_path):
        raise HTTPException(status_code=403, detail="Path not allowed")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    limit = max_bytes or settings.max_read_bytes

    def _read() -> str:
        data = file_path.read_bytes()[:limit]
        return data.decode("utf-8", errors="replace")

    return await asyncio.to_thread(_read)


async def security_request_write(path: str, content: str) -> dict:
    """Request approval for a write operation (two-step write flow)."""

    target = Path(path)
    if not _is_allowed(target):
        raise HTTPException(status_code=403, detail="Path not allowed")

    request_id = os.urandom(8).hex()
    _PENDING_WRITES[request_id] = (target, content.encode("utf-8"))
    preview = content[:200]
    return {
        "request_id": request_id,
        "dry_run": True,
        "path": str(target),
        "preview": preview,
    }


async def confirm_write(request_id: str, allow: bool) -> dict:
    """Apply or discard a pending write request."""

    item = _PENDING_WRITES.pop(request_id, None)
    if not item:
        raise HTTPException(status_code=404, detail="Pending request not found")

    target, data = item
    if not allow:
        return {"request_id": request_id, "applied": False}

    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_bytes, data)
    return {"request_id": request_id, "applied": True, "path": str(target)}


async def fs_write(path: str, content: str, mode: str = "w") -> dict:
    """Write a file after taking a pre-change snapshot."""

    target = Path(path)
    if not _is_allowed(target):
        raise HTTPException(status_code=403, detail="Path not allowed")

    await ensure_prechange_snapshot()
    target.parent.mkdir(parents=True, exist_ok=True)

    async def _write_text() -> None:
        target.write_text(content, encoding="utf-8")

    data = content.encode("utf-8")
    if "b" in mode:
        await asyncio.to_thread(target.write_bytes, data)
    else:
        await asyncio.to_thread(_write_text)

    return {"path": str(target), "bytes": len(data), "mode": mode}
