#!/usr/bin/env python3
"""Verify the provider's real outgoing tool inventory, without authentication.

Run after `pip install -e .`: python scripts/probe_codex_tools.py --binary codex
The temporary loopback server rejects inference after inspecting the request.
No credentials, Telegram connection, cloud model, or active Codex home is used.
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import json
from pathlib import Path
import tempfile
import threading

from marka.provider import CodexProvider, ProviderError


async def probe(binary: str, timeout: float = 45) -> dict:
    captured: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"data":[]}')

        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            if length < 0 or length > 1_048_576:
                self.send_error(413)
                return
            try:
                request = json.loads(self.rfile.read(length))
                captured.append({"path": self.path, "tools": request.get("tools", []),
                                 "tools_field": "present" if "tools" in request else "omitted"})
            except (ValueError, UnicodeError, AttributeError):
                captured.append({"error": "unreadable_request"})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"type":"invalid_request_error","message":"tool contract probe complete"}}')

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    version = None
    try:
        with tempfile.TemporaryDirectory(prefix="marka-tools-contract-") as temporary:
            directory = Path(temporary)
            home = directory / "codex"
            home.mkdir()
            work = directory / "work"
            work.mkdir()
            provider = CodexProvider(binary=binary, home=home, model="gpt-5.6-sol", timeout=timeout)
            env = provider._environment(work)
            executable = await provider._check_cli(work, env)
            version = provider._version
            (work / "schema.json").write_text(json.dumps({
                "type": "object", "properties": {"reply": {"type": "string"}},
                "required": ["reply"], "additionalProperties": False,
            }), encoding="utf-8")
            args = provider._arguments(executable, work)
            args.pop()  # stdin marker follows the probe-specific config below
            for setting in (
                'model_provider="marka_contract_probe"',
                'model_providers.marka_contract_probe.name="Marka tool contract probe"',
                f'model_providers.marka_contract_probe.base_url="http://127.0.0.1:{server.server_port}/v1"',
                'model_providers.marka_contract_probe.wire_api="responses"',
                "model_providers.marka_contract_probe.requires_openai_auth=false",
                "model_providers.marka_contract_probe.request_max_retries=0",
            ):
                args.extend(["-c", setting])
            args.extend(["--disable", "enable_request_compression", "-"])
            await provider._run(args, cwd=work, env=env, prompt=b'Return {"reply":"OK"}.')
    except ProviderError as exc:
        return {"ok": False, "version": version, "error": str(exc), "requests": len(captured)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    response_requests = [row for row in captured if row.get("path", "").endswith("/responses")]
    ok = bool(response_requests) and all(row.get("tools") == [] for row in response_requests)
    return {
        "ok": ok, "version": version, "requests": len(response_requests),
        "tool_counts": [len(row["tools"]) if isinstance(row.get("tools"), list) else None
                        for row in response_requests],
        "tools_fields": [row.get("tools_field") for row in response_requests],
        "error": None if ok else "Expected no tools in every Responses request (omitted or an empty array).",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="codex")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 120:
        parser.error("--timeout must be between 0 and 120 seconds")
    result = asyncio.run(probe(args.binary, args.timeout))
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
