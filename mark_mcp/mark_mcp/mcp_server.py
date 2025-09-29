from typing import Any

from mcp.server.fastmcp import FastMCP

from .fs_tools import fs_glob, fs_read, fs_write
from .docker_tools import compose_cmd, compose_logs, container_exec, tests_run
from .memory_tools import memory_search, memory_upsert
from .repo_tools import repo_snapshot, git_local_commit

mcp = FastMCP("mark-mcp", version="1.0.0")


@mcp.tool()
async def fs_glob_tool(pattern: str, root: str = None):
	return await fs_glob(pattern, root)


@mcp.tool()
async def fs_read_tool(path: str, max_bytes: int = None):
	content = await fs_read(path, max_bytes)
	return {"path": path, "content": content}


@mcp.tool()
async def fs_write_tool(path: str, content: str, mode: str = "w"):
	return await fs_write(path, content, mode)


@mcp.tool()
async def compose_cmd_tool(cmd: str = "ps", service: str = None, flags: str = None):
	return await compose_cmd(cmd, service, flags)


@mcp.tool()
async def compose_logs_tool(service: str, tail: int = 200, since: str = None):
	return await compose_logs(service, tail, since)


@mcp.tool()
async def container_exec_tool(service: str, cmd: str, workdir: str = "/srv/mark", timeout: int = 300):
	return await container_exec(service, cmd, workdir, timeout)


@mcp.tool()
async def tests_run_tool(service: str, cmd: str = "pytest -q", report_out: str = "/data/mark/reports"):
	return await tests_run(service, cmd, report_out)


@mcp.tool()
async def memory_search_tool(query: str, limit: int = 10):
	return await memory_search(query, limit)


@mcp.tool()
async def memory_upsert_tool(text: str, metadata: dict = None):
	return await memory_upsert(text, metadata or {})


@mcp.tool()
async def repo_snapshot_tool(label: str = None):
	return await repo_snapshot("/srv/mark", label)


@mcp.tool()
async def git_local_commit_tool(message: str):
	return await git_local_commit("/srv/mark", message)


@mcp.tool()
async def search_tool(query: str, limit: int = 10):
	"""
	Search through memory and file system for relevant information.
	This tool is required by ChatGPT's MCP specification.
	"""
	try:
		# First try memory search
		memory_results = await memory_search(query, limit)
		
		# Then try file system search using fs_glob
		file_results = await fs_glob(f"**/*{query}*", "/srv/mark")
		
		return {
			"memory_results": memory_results,
			"file_results": file_results[:limit],
			"query": query,
			"total_found": len(memory_results) + len(file_results)
		}
	except Exception as e:
		return {
			"error": str(e),
			"query": query,
			"memory_results": [],
			"file_results": [],
			"total_found": 0
		}
