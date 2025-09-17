from typing import Any, Dict

from .config import settings


async def agent_run_task(task: str, params: Dict[str, Any] | None = None, dry_run: bool | None = None) -> dict:
	dry = settings.dry_run_default if dry_run is None else dry_run
	result = {
		"task": task,
		"params": params or {},
		"dry_run": True,
		"note": "No real side-effects performed."
	}
	if dry:
		return result
	# Place for real execution integration if enabled in future
	return {**result, "dry_run": False, "note": "Executed placeholder."}
