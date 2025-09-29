import asyncio
import os
import httpx
import shlex
from pathlib import Path
from typing import Optional
from .metrics import track_tool_call

# docker SDK не используем (всё через backend/subprocess), чтобы не зависеть от окружения


def _project_root() -> str:
	return "/srv/mark"


def _compose_base_cmd() -> list[str]:
	return ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.override.yml"]


async def _call_backend(endpoint: str, data: dict) -> dict:
	"""Вызов backend API для Docker операций"""
	backend_url = os.getenv("MCP_BACKEND_URL", "http://mcp-backend:8088")
	async with httpx.AsyncClient() as client:
		try:
			response = await client.post(f"{backend_url}/{endpoint}", json=data, timeout=600)
			if response.status_code == 200:
				return response.json()
			else:
				return {"error": f"Backend error: {response.status_code}", "details": response.text}
		except Exception as e:
			return {"error": f"Backend connection failed: {str(e)}"}


@track_tool_call("compose_cmd")
async def compose_cmd(cmd: str, service: Optional[str] = None, flags: Optional[str] = None, project_dir: Optional[str] = None) -> dict:
	"""Использует backend для compose команд"""
	data = {"cmd": cmd}
	if service:
		data["service"] = service
	if flags:
		data["flags"] = flags
	data["project_dir"] = project_dir or _project_root()
	data["project_name"] = os.getenv("COMPOSE_PROJECT_NAME", "marka")
	
	result = await _call_backend("compose_cmd", data)
	if "error" in result:
		# Fallback к subprocess
		import subprocess
		try:
			argv = ["docker", "compose"]
			if flags:
				argv += shlex.split(flags)
			argv.append(cmd)
			if service:
				argv.append(service)
			
			process = subprocess.run(argv, cwd=project_dir or _project_root(), capture_output=True, text=True, timeout=600)
			return {
				"rc": process.returncode,
				"stdout": process.stdout,
				"stderr": process.stderr
			}
		except Exception as e:
			return {"rc": 1, "error": f"Fallback failed: {str(e)}"}
	
	# Преобразуем результат backend в унифицированный формат
	return {
		"rc": result.get("exit_code", 0),
		"stdout": result.get("stdout", ""),
		"stderr": result.get("stderr", ""),
		"duration_ms": result.get("duration_ms", 0),
		"meta": result.get("meta", {})
	}


@track_tool_call("compose_logs")
async def compose_logs(service: str, tail: int = 200, since: Optional[str] = None, project_dir: Optional[str] = None) -> dict:
	"""Использует backend для получения логов"""
	data = {"service": service, "tail": tail}
	if since:
		data["since"] = since
	data["project_dir"] = project_dir or _project_root()
	data["project_name"] = os.getenv("COMPOSE_PROJECT_NAME", "marka")
	
	result = await _call_backend("compose_logs", data)
	if "error" in result:
		# Fallback к subprocess
		import subprocess
		try:
			argv = ["docker", "compose", "logs", service, "--tail", str(tail)]
			if since:
				argv += ["--since", since]
			
			process = subprocess.run(argv, cwd=project_dir or _project_root(), capture_output=True, text=True, timeout=600)
			return {
				"rc": process.returncode,
				"logs": process.stdout,
				"stderr": process.stderr
			}
		except Exception as e:
			return {"rc": 1, "error": f"Fallback failed: {str(e)}"}
	
	# Преобразуем результат backend в унифицированный формат с обратной совместимостью
	return {
		"rc": result.get("exit_code", 0),
		"stdout": result.get("stdout", ""),  # новый единый ключ
		"stderr": result.get("stderr", ""),
		"duration_ms": result.get("duration_ms", 0),
		"meta": result.get("meta", {}),
		"logs": result.get("stdout", "")     # алиас для обратной совместимости
	}


@track_tool_call("container_exec")
async def container_exec(service: str, cmd: str, workdir: str = "/srv/mark", timeout: int = 300, project_dir: Optional[str] = None) -> dict:
	"""Использует backend для выполнения команд в контейнере"""
	data = {
		"service": service,
		"cmd": cmd,
		"workdir": workdir,
		"timeout": timeout,
		"project_dir": project_dir or _project_root()
	}
	
	result = await _call_backend("container_exec", data)
	if "error" in result:
		# Fallback к subprocess
		import subprocess
		try:
			argv = ["docker", "compose", "exec", "-T", service, "sh", "-lc", cmd]
			process = subprocess.run(argv, cwd=project_dir or _project_root(), capture_output=True, text=True, timeout=timeout)
			return {
				"ok": process.returncode == 0,
				"exit_code": process.returncode,
				"output": process.stdout,
				"stderr": process.stderr
			}
		except Exception as e:
			return {"ok": False, "error": f"Fallback failed: {str(e)}"}
	
	# Преобразуем результат backend в унифицированный формат с обратной совместимостью
	return {
		"ok": result.get("exit_code", 1) == 0,
		"exit_code": result.get("exit_code", 1),
		"rc": result.get("exit_code", 1),      # новый единый ключ
		"stdout": result.get("stdout", ""),    # новый единый ключ
		"stderr": result.get("stderr", ""),
		"duration_ms": result.get("duration_ms", 0),
		"meta": result.get("meta", {}),
		"output": result.get("stdout", "")     # алиас для обратной совместимости
	}


async def tests_run(service: str, cmd: str = "pytest -q", report_out: str = "/data/mark/reports") -> dict:
	return await container_exec(service, cmd, workdir="/srv/mark")
