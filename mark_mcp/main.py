import asyncio
import json
import logging
from typing import Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import StreamingResponse, JSONResponse

from mark_mcp.logging_config import setup_logging
from mark_mcp.security import require_bearer
from mark_mcp.config import settings
from mark_mcp.fs_tools import fs_glob, fs_read, security_request_write, confirm_write
from mark_mcp.memory_tools import memory_search, memory_upsert
from mark_mcp.agent_tools import agent_run_task

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)


@app.middleware("http")
async def audit_log(request: Request, call_next):
	try:
		body = await request.body()
		logger.info(f"MCP CALL {request.method} {request.url.path} q={dict(request.query_params)} body={body[:500]!r}")
		response = await call_next(request)
		logger.info(f"MCP RESP {request.method} {request.url.path} status={response.status_code}")
		return response
	except Exception as e:
		logger.exception(f"MCP ERROR {request.method} {request.url.path}: {e}")
		raise


@app.get("/health")
async def health() -> dict[str, Any]:
	return {"status": "ok", "service": settings.app_name}


@app.get("/tools")
async def list_tools(_: None = Depends(require_bearer)) -> dict:
	return {
		"tools": [
			{"name": "fs_glob", "params": ["pattern", "root?" ]},
			{"name": "fs_read", "params": ["path", "max_bytes?"]},
			{"name": "security_request_write", "params": ["path", "content"]},
			{"name": "confirm_write", "params": ["request_id", "allow"]},
			{"name": "memory_search", "params": ["query", "limit?"]},
			{"name": "memory_upsert", "params": ["text", "metadata?"]},
			{"name": "agent_run_task", "params": ["task", "params?", "dry_run?"]},
		]
	}


@app.get("/tools/fs_glob")
async def tool_fs_glob(pattern: str, root: str | None = None, _: None = Depends(require_bearer)) -> dict:
	items = await fs_glob(pattern, root)
	return {"items": items}


@app.get("/tools/fs_read")
async def tool_fs_read(path: str, max_bytes: int | None = None, _: None = Depends(require_bearer)) -> dict:
	content = await fs_read(path, max_bytes)
	return {"path": path, "content": content}


@app.post("/tools/security_request_write")
async def tool_security_request_write(payload: dict, _: None = Depends(require_bearer)) -> dict:
	path = payload.get("path")
	content = payload.get("content", "")
	return await security_request_write(path, content)


@app.post("/tools/confirm_write")
async def tool_confirm_write(payload: dict, _: None = Depends(require_bearer)) -> dict:
	request_id = payload.get("request_id")
	allow = bool(payload.get("allow", False))
	return await confirm_write(request_id, allow)


@app.get("/tools/memory_search")
async def tool_memory_search(query: str, limit: int = 10, _: None = Depends(require_bearer)) -> dict:
	return await memory_search(query, limit)


@app.post("/tools/memory_upsert")
async def tool_memory_upsert(payload: dict, _: None = Depends(require_bearer)) -> dict:
	text = payload.get("text", "")
	metadata = payload.get("metadata") or {}
	return await memory_upsert(text, metadata)


@app.post("/tools/agent_run_task")
async def tool_agent_run_task(payload: dict, _: None = Depends(require_bearer)) -> dict:
	task = payload.get("task", "")
	params = payload.get("params") or {}
	dry_run = payload.get("dry_run")
	return await agent_run_task(task, params, dry_run)


@app.get("/events")
async def sse_events(_: None = Depends(require_bearer)):
	async def event_stream():
		for i in range(3):
			data = json.dumps({"type": "heartbeat", "i": i})
			yield f"data: {data}\n\n"
			await asyncio.sleep(5)
	return StreamingResponse(event_stream(), media_type="text/event-stream")
