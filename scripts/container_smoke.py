#!/usr/bin/env python3
"""Verify the networkless runner from a separate Compose client container.

Run only in an isolated verification project, with its sandbox service running:
docker compose -p marka-verify run --rm --no-deps --entrypoint python mark scripts/container_smoke.py
No model login, bot token, host mount or external service is required.
"""

import base64
import json
import os
from pathlib import Path
import secrets
import time

from marka.sandbox import run_client


def main() -> int:
    socket_path = os.environ.get("MARKA_SANDBOX_SOCKET", "/run/marka/runner.sock")
    deadline = time.monotonic() + 20
    while not Path(socket_path).exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("Runner socket did not become ready")
        time.sleep(0.1)
    checks = []

    def python(code, timeout=10, files=None):
        result = run_client(socket_path, ["python", "-c", code], timeout, files)
        if result.get("error") or result.get("exit_code") != 0 or result.get("timed_out"):
            # Static failure text: never print runner output which may contain a fixture secret.
            raise RuntimeError("Container smoke command did not complete successfully")
        return result

    result = python(
        "from pathlib import Path; assert Path('input.txt').read_text()=='hello'; "
        "Path('answer.txt').write_text('verified'); print('PYTHON_OK')",
        files={"input.txt": base64.b64encode(b"hello").decode()},
    )
    assert base64.b64decode(result["_files"]["answer.txt"]) == b"verified"
    assert "input.txt" not in result["_files"]
    checks.append("artifact_roundtrip")

    node = run_client(socket_path, ["node", "-e", "require('fs').writeFileSync('node.txt','NODE_OK')"], 10)
    assert node.get("exit_code") == 0
    assert base64.b64decode(node["_files"]["node.txt"]) == b"NODE_OK"
    bash = run_client(socket_path, ["bash", "-c", "printf BASH_OK"], 10)
    assert bash.get("exit_code") == 0 and bash["output"] == "BASH_OK"
    checks.append("python_node_bash")

    private = Path(os.environ.get("MARKA_DATA", "/state")) / ("smoke-private-" + secrets.token_hex(8))
    private.write_text("private fixture - must not cross to the runner", encoding="utf-8")
    try:
        paths = [str(private), "/root/.hermes/auth.json", "/root/.codex/auth.json",
                 "/state/codex/auth.json", "/var/run/docker.sock"]
        python("from pathlib import Path; import os; "
               f"assert all(not os.access(p, os.R_OK) for p in {paths!r}); "
               "assert not any(k in os.environ for k in ['TELEGRAM_BOT_TOKEN','CODEX_HOME','OPENAI_API_KEY']); "
               "print('PRIVATE_STATE_INACCESSIBLE')")
    finally:
        private.unlink(missing_ok=True)
    checks.append("private_state_auth_and_host_socket_inaccessible")

    network = python(
        "import socket,json\n"
        "try:\n socket.create_connection(('1.1.1.1',443),timeout=1); result=False\n"
        "except OSError:\n result=True\n"
        "print(json.dumps({'network_denied':result}))\n"
    )
    assert json.loads(network["output"])["network_denied"] is True
    checks.append("outbound_network_denied")

    python(
        "import socket,json\n"
        f"s=socket.socket(socket.AF_UNIX);s.settimeout(2);s.connect({socket_path!r})\n"
        "s.sendall(json.dumps({'argv':['python','-c','print(1)'],'timeout':1,'files':{}}).encode()+b'\\n')\n"
        "response=json.loads(s.recv(8192));s.close()\n"
        "assert 'forbidden' in response.get('error','');print('RECURSIVE_REQUEST_DENIED')\n"
    )
    checks.append("recursive_runner_access_denied")

    leaked = "/tmp/marka-detached-" + secrets.token_hex(8)
    child_code = (
        "import time;from pathlib import Path;time.sleep(0.4);"
        f"Path({leaked!r}).write_text('leaked');time.sleep(30)"
    )
    detached = python(
        "import subprocess,sys;"
        f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}],start_new_session=True);"
        "print(child.pid)"
    )
    child_pid = int(detached["output"].strip())
    time.sleep(0.6)
    python("from pathlib import Path;"
           f"assert not Path({leaked!r}).exists();assert not Path('/proc/{child_pid}').exists();"
           "print('DETACHED_CHILD_REMOVED')")
    checks.append("detached_descendant_cleanup")

    bounded = python("print('x'*60000)")
    assert bounded["truncated"] and len(bounded["output"].encode()) <= 32000
    checks.append("output_limit")

    started = time.monotonic()
    timed = run_client(socket_path, ["python", "-c", "import time;time.sleep(30)"], 1)
    assert timed.get("timed_out") is True and time.monotonic() - started < 7
    checks.append("timeout_and_cleanup")

    oversized = run_client(socket_path, ["python", "-c", "from pathlib import Path;Path('large.txt').write_bytes(b'x'*600000)"], 5)
    assert oversized.get("error") and not oversized.get("_files")
    checks.append("artifact_size_limit")
    python("print('RUNNER_STILL_HEALTHY')")
    checks.append("runner_healthy_after_rejections")
    print(json.dumps({"ok": True, "checks": checks, "count": len(checks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
