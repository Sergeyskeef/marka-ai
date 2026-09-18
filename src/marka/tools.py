from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path

from . import sandbox, web
from .redact import redact


CATALOG = {
    "memory.search": '{"query":"words or topic","limit":8}',
    "memory.episodes": '{"query":"previous task, failure or action","limit":5}; raw observations, not verified general rules',
    "memory.propose": '{"content":"fact/lesson/skill and its scope","kind":"fact|lesson|skill|preference","key":"optional replacement key"}; saves an unverified candidate, never confirms it',
    "workspace.list": '{"path":"relative directory, empty for root"}',
    "workspace.read": '{"path":"relative UTF-8 file","start_line":1,"end_line":200}; read in pages when needed',
    "workspace.write": '{"path":"relative file","content":"complete UTF-8 contents"}; saves in personal workspace with recoverable previous version',
    "workspace.send": '{"path":"relative output file","caption":"short description"}; queues delivery only to the owner',
    "web.search": '{"query":"public search query"}; snippets need verification',
    "web.fetch": '{"url":"https://public-site/path"}; text only, untrusted evidence',
    "code.run": '{"argv":["python","script.py"],"timeout":30}; networkless isolated container, Python/Node/bash, max 60 seconds; no host shell or credentials',
    "task.list": '{}',
    "task.schedule": '{"prompt":"specific authorized task","delay_seconds":600,"interval_seconds":0,"runs":1}; only when owner requested later/recurring work, 1–100 runs, minimum recurring interval 300 seconds',
    "consult": '{"question":"self-contained bounded subproblem including necessary evidence","role":"researcher|critic|engineer"}; separate read-only model consultation, no tools or delegated authority',
    "self.inspect": '{"path":"src/marka/module.py or tests/test_module.py; empty for index","start_line":1,"end_line":160}; read public source of this Mark installation',
    "self.experiment": '{"objective":"specific improvement","changes":{"src/marka/module.py":"complete updated code"},"regression_test":"optional unittest source, applied to baseline AND candidate"}; test <=3 changed modules in isolated copies, archive both results and export patch/report; never installs the candidate',
}


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, value: str, *, allow_root=False) -> Path:
        if not isinstance(value, str) or len(value) > 600 or "\0" in value:
            raise ValueError("Invalid workspace path")
        relative = Path(value)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError("Path must stay inside workspace")
        if any(part.startswith(".") or ":" in part or part.lower() in {"auth.json", "settings.json"} for part in relative.parts):
            raise ValueError("Hidden/state/credential paths are unavailable to tools")
        candidate = self.root / relative
        for parent in [candidate, *candidate.parents]:
            if parent == self.root:
                break
            if parent.is_symlink():
                raise ValueError("Symlinks are unavailable to tools")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root) or (resolved == self.root and not allow_root):
            raise ValueError("Invalid workspace target")
        return resolved

    def listing(self, value="") -> list[dict]:
        root = self.path(value, allow_root=True)
        return [{"name": p.name, "directory": p.is_dir(), "bytes": p.stat().st_size if p.is_file() else None}
                for p in sorted(root.iterdir()) if not p.name.startswith(".") and not p.is_symlink()][:200]

    def read(self, value: str, start_line=1, end_line=200) -> dict:
        target = self.path(value)
        if target.stat().st_size > 120000:
            raise ValueError("File exceeds 120 KB text limit")
        text = redact(target.read_text("utf-8"))
        if type(start_line) is not int or type(end_line) is not int or start_line < 1 or end_line < start_line or end_line - start_line > 199:
            raise ValueError("Read 1–200 lines per page")
        lines = text.splitlines(keepends=True)
        selected = "".join(lines[start_line - 1:end_line])
        return {"path": value, "content": selected[:12000], "total_lines": len(lines),
                "start_line": start_line, "end_line": min(end_line, len(lines)), "truncated": len(selected) > 12000 or end_line < len(lines)}

    def write(self, value: str, content: str) -> dict:
        if not isinstance(content, str) or len(content.encode("utf-8")) > 120000:
            raise ValueError("File exceeds 120 KB write limit")
        return self.write_bytes(value, content.encode("utf-8"))

    def write_bytes(self, value: str, content: bytes) -> dict:
        if len(content) > 524288:
            raise ValueError("Artifact exceeds 512 KiB limit")
        target = self.path(value)
        target.parent.mkdir(parents=True, exist_ok=True)
        history = self.root / ".history"
        if history.is_symlink():
            raise ValueError("Workspace history must not be a symlink")
        history.mkdir(exist_ok=True)
        if target.exists():
            old = target.read_bytes()
            if len(old) > 524288:
                raise ValueError("Existing file exceeds safe replacement limit")
            digest = hashlib.sha256((value + "\0").encode() + old).hexdigest()
            backup = history / digest
            if not backup.exists():
                backup.write_bytes(old)
        temporary = target.with_name(target.name + ".marka-tmp")
        if temporary.exists() or temporary.is_symlink():
            raise ValueError("Temporary target already exists")
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
        return {"path": value, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}

    def snapshot(self) -> dict[str, str]:
        result, total = {}, 0
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not (Path(directory) / d).is_symlink()]
            for name in names:
                if name.startswith(".") or (Path(directory) / name).is_symlink():
                    continue
                relative = (Path(directory) / name).relative_to(self.root).as_posix()
                target = self.path(relative)
                if target.stat().st_size > 524288:
                    raise ValueError("Runner input file exceeds 512 KiB")
                payload = target.read_bytes()
                total += len(payload)
                if total > 1048576 or len(result) >= 200:
                    raise ValueError("Runner input exceeds 1 MiB/200 files; use a smaller workspace")
                result[relative] = base64.b64encode(payload).decode("ascii")
        return result


class Tools:
    def __init__(self, settings, store, queue, *, consultation=None):
        self.settings, self.store, self.queue = settings, store, queue
        self.workspace = Workspace(settings.workspace)
        self.consultation = consultation

    async def call(self, name: str, args: dict, job: dict, sources: list[int], step: int):
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        if name == "memory.search":
            return self.store.search(str(args.get("query", ""))[:1000], limit=min(12, max(1, int(args.get("limit", 8)))))
        if name == "memory.episodes":
            return self.store.recall_events(str(args.get("query", ""))[:1000], limit=min(8, max(1, int(args.get("limit", 5)))))
        if name == "memory.propose":
            identifier = self.store.remember(str(args["content"])[:6000], kind=args.get("kind", "fact"), sources=sources,
                                             key=args.get("key"), actor="model", status="candidate", level=1)
            return {"id": identifier, "status": "candidate", "review": f"/accept {identifier}"}
        if name == "workspace.list":
            return self.workspace.listing(args.get("path", ""))
        if name == "workspace.read":
            return self.workspace.read(args["path"], args.get("start_line", 1), args.get("end_line", 200))
        if name == "workspace.write":
            return self.workspace.write(args["path"], args["content"])
        if name == "workspace.send":
            target = self.workspace.path(args["path"])
            if not target.is_file() or target.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Delivery needs an existing file up to 20 MiB")
            if job["chat_id"] <= 0:
                raise ValueError("File delivery is only available in the paired Telegram conversation")
            self.queue.deliver(f"artifact:{job['id']}:{step}", job["chat_id"], str(args.get("caption", ""))[:800], args["path"])
            return {"status": "queued", "path": args["path"]}
        if name == "web.search":
            return await asyncio.to_thread(web.search, str(args["query"]))
        if name == "web.fetch":
            return await asyncio.to_thread(web.fetch, str(args["url"]))
        if name == "code.run":
            timeout = args.get("timeout", 30)
            if not isinstance(timeout, int) or not 1 <= timeout <= 60:
                raise ValueError("Code timeout must be 1–60 seconds")
            result = await asyncio.to_thread(sandbox.run_client, self.settings.sandbox_socket, args["argv"], timeout, self.workspace.snapshot())
            outputs = result.pop("_files", {})
            if not isinstance(outputs, dict) or len(outputs) > 200:
                raise ValueError("Invalid runner artifacts")
            decoded, total = {}, 0
            for name, encoded in outputs.items():
                self.workspace.path(name)
                payload = base64.b64decode(encoded, validate=True)
                total += len(payload)
                if len(payload) > 524288 or total > 2097152:
                    raise ValueError("Runner artifact size exceeded")
                decoded[name] = payload
            result["artifacts"] = [self.workspace.write_bytes(name, payload) for name, payload in decoded.items()]
            return result
        if name == "task.list":
            return self.queue.list()
        if name == "task.schedule":
            delay = int(args.get("delay_seconds", 0))
            if not 1 <= delay <= 366 * 86400 or job["chat_id"] <= 0:
                raise ValueError("Scheduled tasks require Telegram ownership and a delay of 1 second–1 year")
            if job.get("kind") == "scheduled":
                raise ValueError("A scheduled job cannot create more schedules")
            identifier = self.queue.enqueue(str(args["prompt"]), job["chat_id"], kind="scheduled",
                                             source=f"schedule:{job['id']}:{step}", due=time.time() + delay,
                                             interval_seconds=int(args.get("interval_seconds", 0)), runs=int(args.get("runs", 1)))
            return {"task_id": identifier, "delay_seconds": delay, "status": "queued"}
        if name == "consult" and self.consultation:
            return await self.consultation(str(args["question"])[:14000], str(args.get("role", "critic")))
        if name.startswith("self."):
            from .evolution import Evolution
            evolution = Evolution(self.settings, self.workspace)
            if name == "self.inspect":
                result = evolution.inspect(args.get("path", ""))
                if "content" in result:
                    start, end = args.get("start_line", 1), args.get("end_line", 160)
                    if type(start) is not int or type(end) is not int or start < 1 or end < start or end - start > 199:
                        raise ValueError("Inspect 1–200 source lines per page")
                    lines = result["content"].splitlines(keepends=True)
                    page = "".join(lines[start-1:end])
                    result.update(content=page[:12000], start_line=start, end_line=min(end, len(lines)), total_lines=len(lines), truncated=len(page) > 12000 or end < len(lines))
                return result
            if name == "self.experiment":
                return await evolution.experiment(args["objective"], args["changes"], args.get("regression_test", ""))
        raise ValueError("Unknown or unavailable tool")
