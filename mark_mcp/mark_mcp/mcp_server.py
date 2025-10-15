"""Registration of MCP tools exposed over the FastMCP server."""

from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from .docker_tools import compose_cmd, compose_logs, container_exec, tests_run
from .fs_tools import fs_glob, fs_read, fs_write
from .memory_tools import memory_search, memory_upsert
from .repo_tools import git_local_commit, repo_snapshot

mcp = FastMCP("mark-mcp", version="1.0.0")


@mcp.tool(name="fs_glob", description="Search the filesystem for matching paths.")
async def fs_glob_tool(pattern: str, root: str | None = None) -> list[str]:
    return await fs_glob(pattern, root)


@mcp.tool(name="fs_read", description="Read a file within the allow-list.")
async def fs_read_tool(path: str, max_bytes: int | None = None) -> Dict[str, Any]:
    content = await fs_read(path, max_bytes)
    return {"path": path, "content": content}


@mcp.tool(name="fs_write", description="Write a file after snapshotting the repo.")
async def fs_write_tool(path: str, content: str, mode: str = "w") -> Dict[str, Any]:
    return await fs_write(path, content, mode)


@mcp.tool(name="compose_cmd", description="Execute docker compose commands.")
async def compose_cmd_tool(
    cmd: str = "ps", service: str | None = None, flags: str | None = None
) -> Dict[str, Any]:
    return await compose_cmd(cmd, service, flags)


@mcp.tool(name="compose_logs", description="Fetch docker compose logs.")
async def compose_logs_tool(
    service: str, tail: int = 200, since: str | None = None
) -> Dict[str, Any]:
    return await compose_logs(service, tail, since)


@mcp.tool(name="container_exec", description="Run a command inside a service container.")
async def container_exec_tool(
    service: str,
    cmd: str,
    workdir: str = "/srv/mark",
    timeout: int = 300,
) -> Dict[str, Any]:
    return await container_exec(service, cmd, workdir, timeout)


@mcp.tool(name="tests_run", description="Run tests inside the requested service container.")
async def tests_run_tool(
    service: str, cmd: str = "pytest -q", report_out: str = "/data/mark/reports"
) -> Dict[str, Any]:
    del report_out  # Managed by backend.
    return await tests_run(service, cmd)


@mcp.tool(name="memory_search", description="Search episodic memory.")
async def memory_search_tool(query: str, limit: int = 10) -> Dict[str, Any]:
    return await memory_search(query, limit)


@mcp.tool(name="memory_upsert", description="Store a new memory episode.")
async def memory_upsert_tool(text: str, metadata: dict | None = None) -> Dict[str, Any]:
    return await memory_upsert(text, metadata or {})


@mcp.tool(name="repo_snapshot", description="Create a tarball snapshot of the repository.")
async def repo_snapshot_tool(label: str | None = None) -> Dict[str, Any]:
    return await repo_snapshot("/srv/mark", label)


@mcp.tool(name="git_local_commit", description="Create a commit in the repo.")
async def git_local_commit_tool(message: str) -> Dict[str, Any]:
    return await git_local_commit("/srv/mark", message)


@mcp.tool(name="search", description="Search memory and the filesystem for a query.")
async def search_tool(query: str, limit: int = 10) -> Dict[str, Any]:
    """Aggregate both memory search and a filesystem glob for quick discovery."""

    memory_results = await memory_search(query, limit)
    fs_results = await fs_glob(f"**/*{query}*", "/srv/mark")
    file_hits = fs_results[:limit]
    return {
        "query": query,
        "memory_results": memory_results,
        "file_results": file_hits,
        "total_found": memory_results.get("total", 0) + len(file_hits),
    }
