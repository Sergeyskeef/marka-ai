import asyncio
import os
import time
from pathlib import Path
from typing import Optional
import tarfile


_PRECHANGE_DONE = False


def _should_exclude(path: Path, src: Path, out_file: Path) -> bool:
	rel = path.relative_to(src)
	parts = rel.parts
	if parts and parts[0] in {"data", ".git", "node_modules", "venv", ".venv"}:
		return True
	if "__pycache__" in parts:
		return True
	# exclude the output file if it appears under src (due to host bind)
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
	stamp = time.strftime("%Y%m%d-%H%M%S")
	lbl = f"-{label}" if label else ""
	out = Path("/data/mark/backups").resolve() / f"{stamp}{lbl}.tar.gz"
	out.parent.mkdir(parents=True, exist_ok=True)

	def _do_tar():
		with tarfile.open(out, "w:gz", dereference=True) as tar:
			for path in src.rglob("*"):
				if _should_exclude(path, src, out):
					continue
					# add files only; directories will be included implicitly
				if path.is_file():
					arcname = path.relative_to(src)
					tar.add(path, arcname=str(arcname))

	await asyncio.to_thread(_do_tar)
	return {"archive": str(out)}


async def ensure_prechange_snapshot(root: str = "/srv/mark") -> None:
	global _PRECHANGE_DONE
	if _PRECHANGE_DONE:
		return
	await repo_snapshot(root, label="pre-change")
	_PRECHANGE_DONE = True


async def git_local_commit(root: str = "/srv/mark", message: str = "chore: automated change") -> dict:
	# lightweight wrapper using git CLI
	def _run(cmd, cwd):
		import subprocess
		return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

	res_add = _run(["git", "add", "-A"], cwd=root)
	if res_add.returncode != 0:
		return {"ok": False, "step": "add", "stderr": res_add.stderr}
	res_commit = _run(["git", "commit", "-m", message], cwd=root)
	if res_commit.returncode != 0:
		return {"ok": False, "step": "commit", "stderr": res_commit.stderr}
	res_tag = _run(["git", "tag", "-f", f"mcp-{int(time.time())}", "-m", message], cwd=root)
	return {"ok": True, "commit": res_commit.stdout.strip(), "tag": res_tag.returncode == 0}
