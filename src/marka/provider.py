"""Use the official Codex CLI as a bounded, structured inference provider.

Authentication stays with Codex. This module never opens or copies auth.json.
The tool-free profile was verified against codex-cli 0.144.1 by inspecting its
actual Responses request: no tools (omitted or []). Re-run that contract probe
after upgrades.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile


class ProviderError(RuntimeError):
    """A safe, user-visible provider failure; never includes raw CLI output."""


_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "remote_plugin",
    "browser_use", "computer_use", "image_generation", "multi_agent",
    "hooks", "memories", "goals", "code_mode", "code_mode_host",
    "workspace_dependencies", "tool_suggest",
)
_REQUIRED_FLAGS = (
    "--ignore-user-config", "--ignore-rules", "--ephemeral", "--output-schema",
)
_SAFE_ENV_KEYS = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC",
    "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "CODEX_CA_CERTIFICATE",
)
_NATIVE_TOOL_ITEMS = {
    "command_execution", "file_change", "mcp_tool_call", "web_search",
    "collab_tool_call", "image_generation", "computer_call", "tool_call",
}
_MAX_STREAM_BYTES = 1_048_576
_MAX_RESULT_BYTES = 262_144
_MAX_PROMPT_BYTES = 1_048_576


def _safe_failure(output: bytes, *, exit_code: int | None = None) -> ProviderError:
    """Classify errors without echoing content, paths, prompts or credentials."""
    lowered = output.lower()
    if any(word in lowered for word in (
        b"usage limit", b"rate limit", b"quota", b"429", b"usage_limit",
    )):
        return ProviderError("Codex usage limit reached. Wait for the account limit to reset.")
    if any(word in lowered for word in (
        b"unauthorized", b"401", b"not logged", b"authentication", b"refresh_token",
        b"invalid_grant", b"login required", b"please log in",
    )):
        return ProviderError("Codex authentication needs attention. Run marka login on the host.")
    if any(word in lowered for word in (b"not supported", b"unknown model", b"model_not_found")):
        return ProviderError("The selected model is unavailable for this Codex login.")
    if any(word in lowered for word in (b"stream disconnected", b"connection", b"timed out")):
        return ProviderError("Codex connection failed. Retry after checking host connectivity.")
    suffix = f" (exit {exit_code})" if exit_code is not None else ""
    return ProviderError("Codex could not complete the request" + suffix + ".")


class CodexProvider:
    """Serialize calls and keep all executable agent tools in the Python app.

    Supply a dedicated, persistent CODEX_HOME owned by the service account. The
    account must already have completed `codex login --device-auth` there. A
    normal existing CLI home can also be selected explicitly for a smoke test.
    """

    def __init__(
        self, binary: str = "codex", home: Path | None = None,
        model: str | None = None, timeout: float = 180,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.binary = binary
        selected_home = home if home is not None else Path(
            os.environ.get("CODEX_HOME") or Path.home() / ".codex"
        )
        self.home = Path(selected_home).expanduser().resolve()
        self.model = model
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._validated_binary: str | None = None
        self._version: str | None = None

    def _environment(self, temp_home: Path) -> dict[str, str]:
        env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
        env.update({
            "CODEX_HOME": str(self.home), "HOME": str(temp_home),
            "USERPROFILE": str(temp_home), "TMPDIR": str(temp_home),
            "TEMP": str(temp_home), "TMP": str(temp_home),
            "XDG_CONFIG_HOME": str(temp_home / "config"),
            "XDG_CACHE_HOME": str(temp_home / "cache"),
            "NO_COLOR": "1",
        })
        return env

    async def _terminate(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            await proc.communicate()
            return
        if os.name == "nt":
            # taskkill /T also stops descendant processes; no shell is involved.
            system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
            try:
                killer = await asyncio.create_subprocess_exec(
                    str(system / "System32" / "taskkill.exe"),
                    "/PID", str(proc.pid), "/T", "/F",
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), 5)
            except (OSError, asyncio.TimeoutError):
                pass
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        # Drain closed pipes too. wait() alone can hang if a bounded reader
        # stopped while the OS pipe was full (and leaks transports on Windows).
        await proc.communicate()

    async def _run(
        self, args: list[str], *, cwd: Path, env: dict[str, str],
        prompt: bytes = b"", timeout: float | None = None,
    ) -> tuple[int, bytes, bytes]:
        creation: dict = {}
        if os.name == "nt":
            creation["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            creation["start_new_session"] = True
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, cwd=str(cwd), env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, **creation,
            )
        except (OSError, ValueError):
            raise ProviderError("Cannot start Codex CLI. Check the configured executable.") from None

        async def read_bounded(stream: asyncio.StreamReader) -> bytes:
            chunks: list[bytes] = []
            size = 0
            while chunk := await stream.read(16_384):
                size += len(chunk)
                if size > _MAX_STREAM_BYTES:
                    raise ProviderError("Codex output exceeded the safety limit.")
                chunks.append(chunk)
            return b"".join(chunks)

        async def write_input() -> None:
            assert proc.stdin is not None
            try:
                proc.stdin.write(prompt)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                proc.stdin.close()

        assert proc.stdout is not None and proc.stderr is not None
        tasks = [
            asyncio.create_task(read_bounded(proc.stdout)),
            asyncio.create_task(read_bounded(proc.stderr)),
            asyncio.create_task(write_input()), asyncio.create_task(proc.wait()),
        ]

        async def stop() -> None:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._terminate(proc)

        joined = asyncio.gather(*tasks)
        try:
            result = await asyncio.wait_for(
                joined, timeout if timeout is not None else self.timeout,
            )
            return int(result[3]), result[0], result[1]
        except asyncio.TimeoutError:
            await asyncio.shield(stop())
            raise ProviderError("Codex request timed out; its process was stopped.") from None
        except BaseException:
            await asyncio.shield(stop())
            raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(joined, return_exceptions=True)

    async def _check_cli(self, cwd: Path, env: dict[str, str]) -> str:
        if self._validated_binary is not None:
            return self._validated_binary
        executable = shutil.which(self.binary)
        if executable is None:
            raise ProviderError("Codex CLI was not found. Install the pinned official Codex CLI.")
        executable = str(Path(executable).resolve())
        rc, out, err = await self._run([executable, "--version"], cwd=cwd, env=env, timeout=15)
        match = re.search(rb"codex-cli ((\d+)\.(\d+)\.(\d+)(?:-[^\s]+)?)", out)
        if rc or match is None or tuple(map(int, match.groups()[1:])) < (0, 144, 1):
            raise ProviderError("Codex CLI 0.144.1 or newer is required for isolated inference.")
        self._version = match.group(1).decode()
        rc, out, err = await self._run([executable, "exec", "--help"], cwd=cwd, env=env, timeout=15)
        if rc or any(flag.encode() not in out for flag in _REQUIRED_FLAGS):
            raise ProviderError("This Codex CLI lacks required isolation options.")
        rc, out, err = await self._run([executable, "features", "list"], cwd=cwd, env=env, timeout=15)
        features = {line.split(maxsplit=1)[0].decode() for line in out.splitlines() if line.strip()}
        if rc or not set(_DISABLED_FEATURES).issubset(features):
            raise ProviderError("This Codex CLI lacks required tool controls. Review the CLI version.")
        self._validated_binary = executable
        return executable

    def _arguments(self, binary: str, directory: Path) -> list[str]:
        args = [
            binary, "-a", "never", "exec", "--ignore-user-config", "--ignore-rules",
            "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--json", "--color", "never", "-C", str(directory),
            "--output-schema", str(directory / "schema.json"),
            "--output-last-message", str(directory / "response.json"),
        ]
        for setting in (
            'web_search="disabled"', "tools.view_image=false", "project_doc_max_bytes=0",
        ):
            args.extend(["-c", setting])
        for feature in _DISABLED_FEATURES:
            args.extend(["--disable", feature])
        if self.model:
            args.extend(["--model", self.model])
        args.append("-")
        return args

    async def status(self) -> dict:
        """Return non-secret metadata; does not force refresh or start inference."""
        async with self._lock:
            with tempfile.TemporaryDirectory(prefix="marka-codex-status-") as temporary:
                directory = Path(temporary)
                env = self._environment(directory)
                binary = await self._check_cli(directory, env)
                rc, out, err = await self._run(
                    [binary, "login", "status"], cwd=directory, env=env, timeout=15,
                )
                chatgpt = b"using chatgpt" in (out + err).lower()
                return {"version": self._version, "authenticated": rc == 0 and chatgpt,
                        "auth_method": "chatgpt" if rc == 0 and chatgpt else "unavailable"}

    async def complete(self, prompt: str, schema: dict) -> dict:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty text")
        encoded = prompt.encode("utf-8")
        if len(encoded) > _MAX_PROMPT_BYTES:
            raise ProviderError("Prompt exceeded the provider size limit.")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("schema must describe a JSON object")
        async with self._lock:
            with tempfile.TemporaryDirectory(prefix="marka-codex-") as temporary:
                directory = Path(temporary)
                env = self._environment(directory)
                binary = await self._check_cli(directory, env)
                # Never allow an API-key login to silently incur separate billing.
                rc, out, err = await self._run(
                    [binary, "login", "status"], cwd=directory, env=env, timeout=15,
                )
                if rc or b"using chatgpt" not in (out + err).lower():
                    raise ProviderError("ChatGPT login is required. Run marka login on the host.")
                (directory / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
                rc, out, err = await self._run(
                    self._arguments(binary, directory), cwd=directory, env=env, prompt=encoded,
                )
                if rc:
                    raise _safe_failure(out + err, exit_code=rc)
                for line in out.splitlines():
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    item = event.get("item")
                    if isinstance(item, dict) and item.get("type") in _NATIVE_TOOL_ITEMS:
                        raise ProviderError("Codex attempted a native tool; provider isolation check failed.")
                    if event.get("type") in {"turn.failed", "error"}:
                        raise _safe_failure(out + err)
                response = directory / "response.json"
                try:
                    with response.open("rb") as handle:
                        raw = handle.read(_MAX_RESULT_BYTES + 1)
                    if len(raw) > _MAX_RESULT_BYTES:
                        raise ProviderError("Codex response exceeded the size limit.")
                    result = json.loads(raw)
                except (OSError, ValueError, UnicodeError):
                    raise ProviderError("Codex returned no valid structured response.") from None
                if not isinstance(result, dict):
                    raise ProviderError("Codex response must be a JSON object.")
                return result
