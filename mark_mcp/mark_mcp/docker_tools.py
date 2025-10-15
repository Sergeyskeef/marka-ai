"""Helpers for delegating docker-compose commands to the backend service."""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Dict, Optional

import httpx

from .metrics import track_tool_call


def _project_root() -> str:
    return "/srv/mark"


async def _call_backend(endpoint: str, data: Dict[str, object]) -> Dict[str, object]:
    """Invoke the backend API that wraps docker-compose commands."""

    backend_url = os.getenv("MCP_BACKEND_URL", "http://mcp-backend:8088")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{backend_url}/{endpoint}", json=data, timeout=600
            )
        except Exception as exc:  # pragma: no cover - network issues in runtime
            return {"error": f"Backend connection failed: {exc}"}

    if response.status_code != 200:
        return {
            "error": f"Backend error: {response.status_code}",
            "details": response.text,
        }

    return response.json()


def _compose_subprocess_args(
    cmd: str,
    service: Optional[str],
    flags: Optional[str],
) -> list[str]:
    args = ["docker", "compose"]
    if flags:
        args.extend(shlex.split(flags))
    args.append(cmd)
    if service:
        args.append(service)
    return args


def _run_subprocess(args: list[str], cwd: str, timeout: int) -> Dict[str, object]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "rc": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {"rc": 1, "error": f"Fallback failed: {exc}"}


@track_tool_call("compose_cmd")
async def compose_cmd(
    cmd: str,
    service: Optional[str] = None,
    flags: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> Dict[str, object]:
    """Execute ``docker compose`` commands via the backend or a local fallback."""

    payload: Dict[str, object] = {
        "cmd": cmd,
        "project_dir": project_dir or _project_root(),
        "project_name": os.getenv("COMPOSE_PROJECT_NAME", "marka"),
    }
    if service:
        payload["service"] = service
    if flags:
        payload["flags"] = flags

    result = await _call_backend("compose_cmd", payload)
    if "error" in result:
        return _run_subprocess(
            _compose_subprocess_args(cmd, service, flags),
            cwd=project_dir or _project_root(),
            timeout=600,
        )

    return {
        "rc": result.get("exit_code", 0),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "duration_ms": result.get("duration_ms", 0),
        "meta": result.get("meta", {}),
    }


@track_tool_call("compose_logs")
async def compose_logs(
    service: str,
    tail: int = 200,
    since: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> Dict[str, object]:
    """Fetch service logs from the backend with a subprocess fallback."""

    payload: Dict[str, object] = {
        "service": service,
        "tail": tail,
        "project_dir": project_dir or _project_root(),
        "project_name": os.getenv("COMPOSE_PROJECT_NAME", "marka"),
    }
    if since:
        payload["since"] = since

    result = await _call_backend("compose_logs", payload)
    if "error" in result:
        args = ["docker", "compose", "logs", service, "--tail", str(tail)]
        if since:
            args.extend(["--since", since])
        fallback = _run_subprocess(args, cwd=project_dir or _project_root(), timeout=600)
        if "logs" not in fallback:
            fallback["logs"] = fallback.get("stdout", "")
        return fallback

    stdout = result.get("stdout", "")
    return {
        "rc": result.get("exit_code", 0),
        "stdout": stdout,
        "stderr": result.get("stderr", ""),
        "duration_ms": result.get("duration_ms", 0),
        "meta": result.get("meta", {}),
        "logs": stdout,
    }


@track_tool_call("container_exec")
async def container_exec(
    service: str,
    cmd: str,
    workdir: str = "/srv/mark",
    timeout: int = 300,
    project_dir: Optional[str] = None,
) -> Dict[str, object]:
    """Run a command inside a container via the backend or subprocess."""

    payload: Dict[str, object] = {
        "service": service,
        "cmd": cmd,
        "workdir": workdir,
        "timeout": timeout,
        "project_dir": project_dir or _project_root(),
    }

    result = await _call_backend("container_exec", payload)
    if "error" in result:
        args = ["docker", "compose", "exec", "-T", service, "sh", "-lc", cmd]
        fallback = _run_subprocess(args, cwd=project_dir or _project_root(), timeout=timeout)
        fallback["ok"] = fallback.get("rc", 1) == 0
        fallback.setdefault("output", fallback.get("stdout", ""))
        fallback.setdefault("exit_code", fallback.get("rc", 1))
        return fallback

    stdout = result.get("stdout", "")
    exit_code = result.get("exit_code", 1)
    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "rc": exit_code,
        "stdout": stdout,
        "stderr": result.get("stderr", ""),
        "duration_ms": result.get("duration_ms", 0),
        "meta": result.get("meta", {}),
        "output": stdout,
    }


async def tests_run(
    service: str,
    cmd: str = "pytest -q",
    report_out: str = "/data/mark/reports",
) -> Dict[str, object]:
    """Convenience wrapper that proxies to :func:`container_exec`."""

    del report_out  # Report path is managed by the backend for now.
    return await container_exec(service, cmd, workdir=_project_root())
