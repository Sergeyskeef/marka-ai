"""FastAPI entrypoint wiring the MCP server and tool facade."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from mark_mcp.agent_tools import agent_run_task
from mark_mcp.config import settings
from mark_mcp.docker_tools import compose_cmd, compose_logs, container_exec, tests_run
from mark_mcp.fs_tools import fs_glob, fs_read, fs_write
from mark_mcp.logging_config import setup_logging
from mark_mcp.mcp_server import mcp
from mark_mcp.memory_tools import memory_search, memory_upsert
from mark_mcp.oidc import router as oidc_router
from mark_mcp.repo_tools import git_local_commit, repo_snapshot
from mark_mcp.security import require_auth, require_scope_write

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, redirect_slashes=False)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.bearer_token or "supersecret",
)

# Auth endpoints exposed under /auth so they don't conflict with the MCP mount.
app.include_router(oidc_router, prefix="/auth", tags=["auth"])

# Mount the official FastMCP SSE/JSON-RPC app.
app.mount("/mcp", mcp.sse_app(), name="mcp")


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "mcp": "/mcp",
    }


@app.get("/healthz")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/oauth-protected-resource")
async def oauth_metadata() -> Dict[str, Any]:
    issuer = settings.oauth_issuer or "https://<AUTH_DOMAIN>/realms/marka"
    resource = (settings.oauth_resource or "https://<DOMAIN>/mcp").rstrip("/")
    return {
        "resource": resource,
        "authorization_servers": [issuer],
        "scopes_supported": ["mcp.read", "mcp.write"],
    }


@app.get("/.well-known/oauth-protected-resource/{suffix:path}")
async def oauth_metadata_suffix(suffix: str) -> Dict[str, Any]:
    del suffix
    return await oauth_metadata()


tools_router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_auth)])


@tools_router.get("/")
async def list_tools() -> Dict[str, Any]:
    tools = []
    for tool in await mcp.list_tools():
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
                "schema": tool.inputSchema,
            }
        )
    return {"tools": tools}


@tools_router.get("/fs_glob")
async def tool_fs_glob(pattern: str, root: str | None = None) -> Dict[str, Any]:
    return {"items": await fs_glob(pattern, root)}


@tools_router.get("/fs_read")
async def tool_fs_read(path: str, max_bytes: int | None = None) -> Dict[str, Any]:
    return {"path": path, "content": await fs_read(path, max_bytes)}


@tools_router.post("/fs_write")
async def tool_fs_write(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_scope_write(request)
    path = payload.get("path")
    if not path:
        raise HTTPException(status_code=422, detail="path is required")
    return await fs_write(
        path,
        payload.get("content", ""),
        payload.get("mode", "w"),
    )


@tools_router.post("/repo_snapshot")
async def tool_repo_snapshot(
    request: Request, payload: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    require_scope_write(request)
    label = (payload or {}).get("label")
    return await repo_snapshot("/srv/mark", label)


@tools_router.post("/git_local_commit")
async def tool_git_local_commit(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_scope_write(request)
    return await git_local_commit("/srv/mark", payload.get("message", "chore: automated change"))


@tools_router.post("/compose_cmd")
async def tool_compose_cmd(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    if payload.get("cmd", "ps") != "ps":
        require_scope_write(request)
    return await compose_cmd(payload.get("cmd", "ps"), payload.get("service"), payload.get("flags"))


@tools_router.get("/compose_logs")
async def tool_compose_logs(service: str, tail: int = 200, since: str | None = None) -> Dict[str, Any]:
    return await compose_logs(service, tail, since)


@tools_router.post("/container_exec")
async def tool_container_exec(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_scope_write(request)
    service = payload.get("service")
    cmd = payload.get("cmd")
    if not service or not cmd:
        raise HTTPException(status_code=422, detail="service and cmd are required")
    return await container_exec(
        service,
        cmd,
        payload.get("workdir", "/srv/mark"),
        int(payload.get("timeout", 300)),
    )


@tools_router.post("/tests_run")
async def tool_tests_run(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_scope_write(request)
    service = payload.get("service")
    if not service:
        raise HTTPException(status_code=422, detail="service is required")
    return await tests_run(
        service,
        payload.get("cmd", "pytest -q"),
        payload.get("report_out", "/data/mark/reports"),
    )


@tools_router.get("/memory_search")
async def tool_memory_search(query: str, limit: int = 10) -> Dict[str, Any]:
    return await memory_search(query, limit)


@tools_router.post("/memory_upsert")
async def tool_memory_upsert(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_scope_write(request)
    return await memory_upsert(payload.get("text", ""), payload.get("metadata") or {})


@tools_router.post("/agent_run_task")
async def tool_agent_run_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_run_task(
        payload.get("task", ""),
        payload.get("params") or {},
        payload.get("dry_run"),
    )


app.include_router(tools_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
