"""Bounded code runner for a dedicated networkless, private-PID Docker container.

Ordinary local interpreter execution is disabled. Files cross a bounded base64
protocol; the container never mounts the owner's workspace, database or auth.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

MAX_WIRE_BYTES = 3 * 1024 * 1024
MAX_FILES = 200
MAX_FILE_BYTES = 512 * 1024
MAX_INPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
_ALLOWED = {"python": "/opt/venv/bin/python", "python3": "/opt/venv/bin/python",
            "node": "/usr/bin/node", "bash": "/bin/bash"}
_RESERVED = {"con", "prn", "aux", "nul", "clock$", *[f"com{i}" for i in range(1, 10)],
             *[f"lpt{i}" for i in range(1, 10)], *[prefix + digit for prefix in ("com", "lpt") for digit in "¹²³"]}


class SandboxCleanupError(RuntimeError):
    """Fail closed: stop the container if a child cannot be removed."""


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > 600:
        raise ValueError("Invalid artifact name")
    if any(char in '\\:<>"|?*' or ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in name):
        raise ValueError("Unsafe artifact path")
    parts = name.split("/")
    if any(not part or part.startswith(".") or part.endswith((".", " "))
           or part.split(".")[0].casefold() in _RESERVED for part in parts):
        raise ValueError("Unsafe artifact path")
    return name


def _decode_files(files: dict[str, str] | None, total_limit=MAX_INPUT_BYTES) -> dict[str, bytes]:
    if files is None:
        return {}
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise ValueError("Artifact input must be a map of at most 200 files")
    result: dict[str, bytes] = {}
    names: set[str] = set()
    total = 0
    for name, encoded in files.items():
        _safe_name(name)
        normalized = name.casefold()
        if normalized in names or any(normalized.startswith(other + "/") or other.startswith(normalized + "/") for other in names):
            raise ValueError("Artifact paths collide")
        names.add(normalized)
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_FILE_BYTES + 2) // 3):
            raise ValueError("Artifact exceeds 512 KiB per-file limit")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Artifact is not valid base64") from None
        if len(decoded) > MAX_FILE_BYTES:
            raise ValueError("Artifact exceeds 512 KiB per-file limit")
        total += len(decoded)
        if total > total_limit:
            raise ValueError(f"Artifacts exceed {total_limit // 1024} KiB total limit")
        result[name] = decoded
    return result


def _validate_command(argv, timeout):
    if not isinstance(argv, list) or not 1 <= len(argv) <= 30 or any(
        not isinstance(item, str) or len(item) > 12000 or "\0" in item for item in argv
    ):
        raise ValueError("Invalid argv")
    if argv[0] not in _ALLOWED or type(timeout) is not int or not 1 <= timeout <= 60:
        raise ValueError("Runner allows python, python3, node, bash; timeout 1–60 seconds")


def _require_container() -> None:
    # Host/shared PID containers and ordinary host processes cannot enter cleanup.
    if (sys.platform != "linux" or os.getpid() != 1
            or os.environ.get("MARKA_SANDBOX_CONTAINER") != "1"
            or not Path("/.dockerenv").is_file()):
        raise RuntimeError("Runner requires PID 1 in its dedicated Linux Docker container")
    if os.readlink("/proc/1/ns/pid") != os.readlink("/proc/self/ns/pid"):
        raise RuntimeError("Runner requires its own mounted PID namespace")


def _reap_children() -> None:
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _kill_other_processes() -> None:
    """Kill adopted/daemonized children, not only the original process group."""
    _require_container()
    deadline = time.monotonic() + 3
    while True:
        _reap_children()
        others = [int(path.name) for path in Path("/proc").iterdir()
                  if path.name.isdecimal() and int(path.name) != os.getpid()]
        if not others:
            return
        for pid in others:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                raise SandboxCleanupError("Runner could not terminate all child processes") from exc
        _reap_children()
        if time.monotonic() >= deadline:
            raise SandboxCleanupError("Runner child cleanup exceeded its deadline")
        time.sleep(0.01)


def _external_peer(sock) -> bool:
    # Peers outside our private PID namespace map to PID zero. Code subprocesses
    # have visible PIDs and must not recursively enqueue unbudgeted executions.
    credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, _, _ = struct.unpack("3i", credentials)
    return pid == 0


def run_client(socket_path: str, argv: list[str], timeout=30,
               files: dict[str, str] | None = None) -> dict:
    if not socket_path:
        raise ValueError("Code runner is not enabled. Start the sandbox service with Docker Compose.")
    if not hasattr(socket, "AF_UNIX"):
        raise ValueError("This host lacks Unix sockets; run the code runner through Linux Docker Compose")
    _validate_command(argv, timeout)
    _decode_files(files)
    request = json.dumps({"argv": argv, "timeout": timeout, "files": files or {}},
                         ensure_ascii=False).encode("utf-8") + b"\n"
    if len(request) > MAX_WIRE_BYTES:
        raise ValueError("Runner request exceeds 3 MiB limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout + 10)
        client.connect(socket_path)
        client.sendall(request)
        response = bytearray()
        while b"\n" not in response:
            chunk = client.recv(65536)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_WIRE_BYTES:
                raise ValueError("Runner response exceeds 3 MiB limit")
    if not response.endswith(b"\n"):
        raise ValueError("Runner response was interrupted")
    result = json.loads(response)
    if not isinstance(result, dict):
        raise ValueError("Invalid runner response")
    _decode_files(result.get("_files"), MAX_OUTPUT_BYTES)
    return result


def _collect_files(workspace: Path, original: dict[str, bytes]) -> dict[str, str]:
    changed: dict[str, str] = {}
    names: set[str] = set()
    total = visited = 0
    pending = [workspace]
    while pending:
        # Stream directory entries so a tree with many empty files cannot make
        # os.walk materialize an unbounded list before the entry budget applies.
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                visited += 1
                if visited > 1000:
                    raise ValueError("Output contains too many filesystem entries")
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    continue
                path = Path(entry.path)
                relative = _safe_name(path.relative_to(workspace).as_posix())
                normalized = relative.casefold()
                if normalized in names:
                    raise ValueError("Output artifact paths collide")
                names.add(normalized)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("Output contains a non-regular artifact")
                if info.st_size > MAX_FILE_BYTES:
                    raise ValueError("Output artifact exceeds 512 KiB per-file limit")
                data = path.read_bytes()
                if data == original.get(relative):
                    continue
                if len(changed) >= MAX_FILES:
                    raise ValueError("Output exceeds 200 changed files")
                total += len(data)
                if total > MAX_OUTPUT_BYTES:
                    raise ValueError("Output artifacts exceed 2048 KiB total limit")
                changed[relative] = base64.b64encode(data).decode("ascii")
    return changed


# A fresh isolated interpreter sets limits before exec. Avoid preexec_fn in a
# multithreaded asyncio server, where running Python after fork can deadlock.
_LIMIT_WRAPPER = """
import os, resource, sys
limit = int(sys.argv[1])
resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.execv(sys.argv[2], sys.argv[2:])
"""


def execute(argv, timeout, workspace: Path, files: dict[str, str] | None = None) -> dict:
    """Run in a fresh temporary directory under the container's private tmpfs."""
    _require_container()
    _validate_command(argv, timeout)
    original = _decode_files(files)
    workspace = Path(workspace)
    if workspace.is_symlink():
        raise ValueError("Runner temporary root must not be a symlink")
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="job-", dir=workspace) as temporary:
        job_root = Path(temporary)
        work, home, scratch = job_root / "files", job_root / "home", job_root / "tmp"
        for path in (work, home, scratch):
            path.mkdir()
        for name, content in original.items():
            target = work.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        with tempfile.TemporaryFile(dir=scratch) as output:
            process = None
            timed_out = False
            try:
                process = subprocess.Popen(
                    [sys.executable, "-I", "-c", _LIMIT_WRAPPER, str(timeout), _ALLOWED[argv[0]], *argv[1:]],
                    cwd=work, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=True,
                    env={"PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin", "HOME": str(home),
                         "TMPDIR": str(scratch), "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
            finally:
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                _kill_other_processes()
            output.seek(0)
            data = output.read(32001)
        result = {"exit_code": process.returncode, "timed_out": timed_out,
                  "output": data[:32000].decode("utf-8", errors="replace"), "truncated": len(data) > 32000}
        try:
            result["_files"] = _collect_files(work, original)
        except ValueError as exc:
            result["error"] = str(exc)
            result["_files"] = {}
        return result


async def serve(path: str, workspace: Path):
    _require_container()
    socket_path = Path(path)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    lock = asyncio.Lock()

    async def handle(reader, writer):
        try:
            if not _external_peer(writer.get_extra_info("socket")):
                raise ValueError("Runner requests from its execution namespace are forbidden")
            payload = await asyncio.wait_for(reader.readline(), 5)
            if len(payload) > MAX_WIRE_BYTES:
                raise ValueError("Runner request exceeds 3 MiB limit")
            if not payload.endswith(b"\n"):
                raise ValueError("Runner request was interrupted")
            request = json.loads(payload)
            if not isinstance(request, dict) or set(request) - {"argv", "timeout", "files"}:
                raise ValueError("Invalid runner request")
            async with lock:
                result = await asyncio.to_thread(execute, request["argv"], request.get("timeout", 30),
                                                 workspace, request.get("files"))
        except SandboxCleanupError:
            # Exiting PID 1 makes the kernel stop every process in this namespace.
            os._exit(70)
        except ValueError as exc:
            result = {"error": str(exc)[:1000], "_files": {}}
        except Exception:
            result = {"error": "Runner rejected or failed the request", "_files": {}}
        payload = json.dumps(result, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_WIRE_BYTES:
            payload = b'{"error":"Runner response exceeds 3 MiB limit","_files":{}}\n'
        writer.write(payload)
        try:
            await asyncio.wait_for(writer.drain(), 5)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, str(socket_path), limit=MAX_WIRE_BYTES + 1)
    socket_path.chmod(0o660)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve(os.environ.get("MARKA_SANDBOX_SOCKET", "/run/marka/runner.sock"), Path("/workspace")))
