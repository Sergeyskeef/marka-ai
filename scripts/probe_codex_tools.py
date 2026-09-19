#!/usr/bin/env python3
"""Verify the provider's real outgoing tool inventory, without authentication.

Run after `pip install -e .`: python scripts/probe_codex_tools.py --binary codex
The temporary loopback server rejects inference after inspecting the request.
No credentials, Telegram connection, cloud model, or active Codex home is used.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import http.server
import json
from pathlib import Path
import tempfile
import threading
import struct
import zlib

from marka.provider import CodexProvider, ProviderError, REASONING_EFFORTS


async def probe(binary: str, timeout: float = 45, images: int = 0, *, reasoning_effort: str | None = None) -> dict:
    captured: list[dict] = []
    if type(images) is not int or not 0 <= images <= 2:
        raise ValueError("Probe supports zero, one or two synthetic images")
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
    synthetic = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    synthetic += chunk(b"IDAT", zlib.compress(b"\0\xff\0\0")) + chunk(b"IEND", b"")
    expected_image = "data:image/png;base64," + base64.b64encode(synthetic).decode("ascii")

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
                pictures = [part.get("image_url") for item in request.get("input", []) if isinstance(item, dict)
                            for part in item.get("content", []) if isinstance(part, dict) and part.get("type") == "input_image"]
                captured.append({"path": self.path, "tools": request.get("tools", []),
                                 "tools_field": "present" if "tools" in request else "omitted",
                                 "images": len(pictures), "images_exact": pictures == [expected_image] * images,
                                 "schema": request.get("text", {}).get("format", {}).get("type") == "json_schema",
                                 "reasoning_effort": request.get("reasoning", {}).get("effort"),
                                 "authorization_present": bool(self.headers.get("Authorization"))})
            except (ValueError, UnicodeError, AttributeError, TypeError):
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
            provider = CodexProvider(binary=binary, home=home, model="gpt-5.6-sol", timeout=timeout,
                                     reasoning_effort=reasoning_effort)
            env = provider._environment(work)
            executable = await provider._check_cli(work, env)
            version = provider._version
            (work / "schema.json").write_text(json.dumps({
                "type": "object", "properties": {"reply": {"type": "string"}},
                "required": ["reply"], "additionalProperties": False,
            }), encoding="utf-8")
            image_paths = []
            for index in range(images):
                target = work / f"synthetic-{index}.png"
                target.write_bytes(synthetic)
                image_paths.append(target)
            args = provider._arguments(executable, work, image_paths)
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
    ok = bool(response_requests) and all(row.get("tools") == [] and row.get("images_exact") and row.get("schema")
                                        and (reasoning_effort is None or row.get("reasoning_effort") == reasoning_effort)
                                        and not row.get("authorization_present") for row in response_requests)
    return {
        "ok": ok, "version": version, "requests": len(response_requests),
        "tool_counts": [len(row["tools"]) if isinstance(row.get("tools"), list) else None
                        for row in response_requests],
        "tools_fields": [row.get("tools_field") for row in response_requests],
        "image_counts": [row["images"] for row in response_requests],
        "synthetic_image_sha256": hashlib.sha256(synthetic).hexdigest() if images else None,
        "schema_preserved": all(row.get("schema") for row in response_requests),
        "reasoning_effort_requested": reasoning_effort,
        "reasoning_efforts_observed": [row.get("reasoning_effort") for row in response_requests],
        "authorization_present": any(row.get("authorization_present") for row in response_requests),
        "error": None if ok else "Expected no tools or authorization, exact synthetic images, structured schema, and explicit reasoning effort (when requested) in every Responses request.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="codex")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--images", type=int, choices=(0, 1, 2), default=0,
                        help="Verify native PNG image parts as well as the empty tool inventory")
    parser.add_argument("--reasoning-effort", choices=sorted(REASONING_EFFORTS),
                        help="Verify the explicit reasoning effort in the actual Responses request")
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 120:
        parser.error("--timeout must be between 0 and 120 seconds")
    result = asyncio.run(probe(args.binary, args.timeout, args.images, reasoning_effort=args.reasoning_effort))
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
