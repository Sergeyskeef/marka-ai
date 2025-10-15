"""Utilities for interacting with the on-disk Git repository."""

from __future__ import annotations

import asyncio
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Optional


_PRECHANGE_DONE = False


def _should_exclude(path: Path, src: Path, out_file: Path) -> bool:
    rel = path.relative_to(src)
    parts = rel.parts
    if parts and parts[0] in {"data", ".git", "node_modules", "venv", ".venv"}:
        return True
    if "__pycache__" in parts:
        return True
    # Exclude the archive itself if the destination is inside the repo tree.
    try:
        out_rel = out_file.resolve().relative_to(src.resolve())
        if str(rel).startswith(str(out_rel)):
            return True
    except Exception:
        pass
    return False


async def repo_snapshot(root: str = "/srv/mark", label: Optional[str] = None) -> dict:
    src = Path(root).resolve()
    if not src.exists():
        raise FileNotFoundError(root)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    out = Path("/data/mark/backups").resolve() / f"{timestamp}{suffix}.tar.gz"
    out.parent.mkdir(parents=True, exist_ok=True)

    def _create_tar() -> None:
        with tarfile.open(out, "w:gz", dereference=True) as archive:
            for path in src.rglob("*"):
                if _should_exclude(path, src, out):
                    continue
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(src)))

    await asyncio.to_thread(_create_tar)
    return {"archive": str(out)}


async def ensure_prechange_snapshot(root: str = "/srv/mark") -> None:
    global _PRECHANGE_DONE
    if _PRECHANGE_DONE:
        return
    await repo_snapshot(root, label="pre-change")
    _PRECHANGE_DONE = True


async def git_local_commit(root: str = "/srv/mark", message: str = "chore: automated change") -> dict:
    """Create a lightweight commit inside ``root`` using the Git CLI."""

    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
        )

    add = _run("add", "-A")
    if add.returncode != 0:
        return {"ok": False, "step": "add", "stderr": add.stderr.strip()}

    commit = _run("commit", "-m", message)
    if commit.returncode != 0:
        return {"ok": False, "step": "commit", "stderr": commit.stderr.strip()}

    tag_name = f"mcp-{int(time.time())}"
    tag = _run("tag", "-f", tag_name, "-m", message)

    return {
        "ok": True,
        "commit": commit.stdout.strip(),
        "tag": tag.returncode == 0,
        "tag_name": tag_name,
    }
