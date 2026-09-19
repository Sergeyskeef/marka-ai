from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from . import sandbox, web
from .redact import redact
from .scheduling import clock_context, schedule_due


class ToolInputError(ValueError):
    """Input rejected before the requested operation has any side effect."""


CATALOG = {
    "memory.search": '{"query":"words or topic","limit":8}',
    "memory.episodes": '{"query":"previous task, failure or action","limit":5}; raw observations, not verified general rules',
    "memory.read": '{"id":12,"offset":0,"limit":4000}; exact knowledge page, origin and evidence IDs',
    "memory.source": '{"event_id":12,"offset":0,"limit":4000,"memory_id":0}; full original event page; optional memory_id reads its saved evidence snapshot',
    "memory.related": '{"event_id":12,"limit":8}; related task/conversation evidence, not inferred facts',
    "memory.entities": '{"query":"project or person","limit":12}; links supported by source mentions, not accepted relationships',
    "memory.propose": '{"content":"fact/lesson/skill and its scope","kind":"fact|lesson|skill|preference","key":"optional replacement key"}; saves an unverified candidate, never confirms it',
    "workspace.list": '{"path":"relative directory, empty for root"}',
    "workspace.read": '{"path":"relative UTF-8 file","start_line":1,"end_line":200,"offset":0}; omit offset for line selection; next_offset reads the next 12000-character page including long lines; <=512 KiB file',
    "workspace.write": '{"path":"relative file","content":"complete UTF-8 contents"}; saves in personal workspace with recoverable previous version',
    "workspace.replace": '{"path":"relative file","old":"exact unique text","new":"replacement text","expected_sha256":"optional hash of current file"}; precise edit with conflict check and saved previous version',
    "workspace.find": '{"query":"literal text","path":"optional subdirectory"}; search bounded working files with line numbers',
    "workspace.send": '{"path":"relative output file","caption":"short description"}; queues delivery only to the owner',
    "web.search": '{"query":"public search query"}; snippets need verification',
    "web.fetch": '{"url":"https://public-site/path","offset":0,"expected_sha256":"optional previous page hash"}; 14000-character pages, links and fetch time; pin hash when continuing a source',
    "code.run": '{"argv":["python","script.py"],"timeout":30,"inputs":["script.py"]}; select relevant input files to avoid copying old artifacts; inputs=[] for no files, omitted copies bounded workspace; networkless Python/Node/bash, max 60 seconds',
    "skill.save": '{"name":"ascii-slug","description":"when this script helps and its limitations","event_id":12}; capture current task successful code.run inputs and exact command as versioned reusable code; use observed event ID',
    "skill.search": '{"query":"task or capability","limit":5}; find previously executed scripts with source and input evidence',
    "skill.inspect": '{"name":"ascii-slug"}; inspect saved command, input manifest, code excerpts and validation limits',
    "skill.run": '{"name":"ascii-slug","parameters":["optional replacement script arguments"],"inputs":{"data.csv":"relative current workspace data.csv"}}; runs saved code only in isolated runner; omit options to replay exact case; new arguments/data require a new result check',
    "task.list": '{}',
    "task.plan": '{"steps":[{"title":"step","status":"pending|running|completed|blocked","evidence":"source or artifact"}],"summary":"current progress"}; persist <=12 steps for the current task; completion still requires observed outcomes',
    "task.progress": '{"id":"optional current task id"}; durable plan, checks, artifacts and remaining budget',
    "task.schedule": '{"prompt":"specific authorized task","delay_seconds":600,"interval_seconds":0,"runs":1}; alternatively replace delay_seconds with due_at="2026-10-01T09:00:00+03:00"; exactly one time form, explicit offset for due_at; owner-requested only, 1–100 runs, minimum recurring interval 300 seconds',
    "consult": '{"question":"self-contained bounded subproblem including necessary evidence","role":"researcher|critic|engineer"}; separate read-only model consultation, no tools or delegated authority',
    "self.inspect": '{"path":"src/marka/module.py or tests/test_module.py; empty for index","start_line":1,"end_line":160}; read public source of this Mark installation',
    "self.experiment": '{"objective":"specific improvement","changes":{"src/marka/module.py":"complete updated code"},"regression_test":"optional unittest source, applied to baseline AND candidate"}; test <=3 changed modules in isolated copies, archive both results and export patch/report; never installs the candidate',
    "self.history": '{"limit":8}; read prior improvement experiment outcomes and identifiers from the original archive',
    "self.read_experiment": '{"id":"experiment ID","artifact":"report|patch|candidate|baseline","path":"optional source path for candidate/baseline","offset":0,"limit":8000}; paged original evidence for reusing an experiment; no installation',
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

    def read(self, value: str, start_line=1, end_line=200, *, offset=None) -> dict:
        target = self.path(value)
        if target.stat().st_size > 524288:
            raise ValueError("File exceeds 512 KiB text limit")
        payload = target.read_bytes()
        text = redact(payload.decode("utf-8-sig"))
        if type(start_line) is not int or type(end_line) is not int or start_line < 1 or end_line < start_line or end_line - start_line > 199:
            raise ValueError("Read 1–200 lines per page")
        lines = text.splitlines(keepends=True)
        if offset is not None:
            if type(offset) is not int or offset < 0:
                raise ValueError("Read offset must be a nonnegative character position")
            begin = min(offset, len(text))
            selected = text[begin:begin + 12000]
        else:
            begin = sum(map(len, lines[:start_line - 1]))
            selected = "".join(lines[start_line - 1:end_line])[:12000]
        end = begin + len(selected)
        return {"path": value, "content": selected, "total_lines": len(lines),
                "start_line": start_line, "end_line": min(end_line, len(lines)),
                "offset": begin, "next_offset": end if end < len(text) else None,
                "total_chars": len(text), "sha256": hashlib.sha256(payload).hexdigest(), "truncated": end < len(text)}

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

    def replace(self, value: str, old: str, new: str, expected_sha256="") -> dict:
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ToolInputError("Provide a nonempty exact old text and replacement")
        target = self.path(value)
        if target.stat().st_size > 120000:
            raise ValueError("File exceeds 120 KB text limit")
        data = target.read_bytes()
        if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ToolInputError("File changed since inspection; read it again before editing")
        text = data.decode("utf-8")
        if text.count(old) != 1:
            raise ToolInputError("Replacement must match exactly once; inspect the file and add context")
        return self.write(value, text.replace(old, new, 1))

    def find(self, query: str, value="") -> dict:
        if not isinstance(query, str) or not 1 <= len(query) <= 300:
            raise ValueError("Search text must contain 1–300 characters")
        root = self.path(value, allow_root=True)
        candidates = [root] if root.is_file() else root.rglob("*")
        results, scanned, total = [], 0, 0
        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            name = candidate.relative_to(self.root).as_posix()
            if any(part.startswith(".") for part in Path(name).parts):
                continue
            try:
                path = self.path(name)
                if path.stat().st_size > 120000:
                    continue
                payload = path.read_bytes()
                total += len(payload)
                scanned += 1
                if total > 1048576 or scanned > 100:
                    return {"matches": results, "scanned": scanned - 1, "truncated": True}
                text = payload.decode("utf-8")
            except (UnicodeError, ValueError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if query.casefold() in line.casefold():
                    results.append({"path": name, "line": number, "text": redact(line[:500])})
                    if len(results) >= 30:
                        return {"matches": results, "scanned": scanned, "truncated": True}
        return {"matches": results, "scanned": scanned, "truncated": False}

    def snapshot(self, paths=None) -> dict[str, str]:
        result, total = {}, 0
        if paths is not None:
            if not isinstance(paths, list) or len(paths) > 200 or not all(isinstance(p, str) for p in paths):
                raise ValueError("Runner inputs must be a list of up to 200 relative files")
            for name in dict.fromkeys(paths):
                target = self.path(name)
                if not target.is_file() or target.stat().st_size > 524288:
                    raise ValueError("Each runner input must be a file up to 512 KiB")
                payload = target.read_bytes()
                total += len(payload)
                if total > 1048576:
                    raise ValueError("Selected inputs exceed 1 MiB")
                result[name] = base64.b64encode(payload).decode("ascii")
            return result
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
    def __init__(self, settings, store, queue, *, consultation=None, semantic=None):
        self.settings, self.store, self.queue = settings, store, queue
        self.workspace = Workspace(settings.workspace)
        self.consultation = consultation
        self.semantic = semantic

    async def search(self, query, limit=8, *, episodes=False):
        limit = max(1, min(int(limit), 12))
        lookup = self.store.recall_events if episodes else self.store.search
        rows = await asyncio.to_thread(lookup, query, limit=limit)
        if self.semantic and self.semantic.available() and query.strip():
            try:
                from .semantic import hybrid
                extra = await asyncio.to_thread(self.semantic.search, query, kind="event" if episodes else "memory", limit=limit)
                rows = hybrid(rows, extra, limit)
            except (ImportError, ValueError, OSError, RuntimeError, sqlite3.Error):
                # A derived index failure must not hide canonical lexical results.
                pass
        if not episodes:
            from .learning import Learning
            rows = Learning(self.store).filter_context(rows)
        return rows

    async def call(self, name: str, args: dict, job: dict, sources: list[int], step: int | str):
        if not isinstance(args, dict):
            raise ToolInputError("Tool arguments must be an object")
        if name in {"workspace.read", "workspace.write", "workspace.replace", "workspace.send"}:
            try:
                self.workspace.path(args["path"])
                if name == "workspace.write" and (not isinstance(args.get("content"), str) or len(args["content"].encode("utf-8")) > 120000):
                    raise ValueError("File exceeds 120 KB write limit or has invalid text")
            except (ValueError, KeyError, TypeError) as exc:
                raise ToolInputError(str(exc)) from None
        if name == "memory.search":
            return await self.search(str(args.get("query", ""))[:1000], args.get("limit", 8))
        if name == "memory.episodes":
            return await self.search(str(args.get("query", ""))[:1000], args.get("limit", 5), episodes=True)
        if name == "memory.read":
            return self.store.get_memory(int(args["id"]), offset=int(args.get("offset", 0)), limit=int(args.get("limit", 4000))) or {"not_found": True}
        if name == "memory.source":
            options = {"offset": int(args.get("offset", 0)), "limit": int(args.get("limit", 4000))}
            if args.get("memory_id"):
                return self.store.get_memory(int(args["memory_id"]), source_id=int(args["event_id"]), **options) or {"not_found": True}
            return self.store.get_event(int(args["event_id"]), **options) or {"not_found": True}
        if name == "memory.related":
            return self.store.related_events(int(args["event_id"]), limit=min(12, int(args.get("limit", 8))))
        if name == "memory.entities":
            return self.store.entity_links(str(args.get("query", "")), limit=min(20, int(args.get("limit", 12))))
        if name == "memory.propose":
            identifier = self.store.remember(str(args["content"])[:6000], kind=args.get("kind", "fact"), sources=sources,
                                             key=args.get("key"), actor="model", status="candidate", level=2 if args.get("kind") in {"lesson", "skill"} else 1)
            return {"id": identifier, "status": "candidate", "review": f"/accept {identifier}"}
        if name == "workspace.list":
            return self.workspace.listing(args.get("path", ""))
        if name == "workspace.read":
            return self.workspace.read(args["path"], args.get("start_line", 1), args.get("end_line", 200), offset=args.get("offset"))
        if name == "workspace.write":
            return self.workspace.write(args["path"], args["content"])
        if name == "workspace.replace":
            return self.workspace.replace(args["path"], args["old"], args["new"], args.get("expected_sha256", ""))
        if name == "workspace.find":
            return self.workspace.find(args["query"], args.get("path", ""))
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
            return await asyncio.to_thread(web.fetch, str(args["url"]), offset=args.get("offset", 0), expected_sha256=args.get("expected_sha256", ""))
        if name == "code.run":
            timeout = args.get("timeout", 30)
            if not isinstance(timeout, int) or not 1 <= timeout <= 60:
                raise ToolInputError("Code timeout must be 1–60 seconds")
            try:
                sandbox._validate_command(args["argv"], timeout)
                inputs = self.workspace.snapshot(args.get("inputs"))
            except (ValueError, KeyError, TypeError) as exc:
                raise ToolInputError(str(exc)) from None
            return await self._run_code(args["argv"], timeout, inputs)
        if name.startswith("skill."):
            from .skills import SkillLibrary
            library = SkillLibrary(self.settings, self.store, self.queue)
            if name == "skill.save":
                return library.save(args["name"], args["description"], args["event_id"], job["id"])
            if name == "skill.search":
                return await asyncio.to_thread(library.search, args.get("query", ""), limit=args.get("limit", 5))
            if name == "skill.inspect":
                return library.inspect(args["name"])
            if name == "skill.run":
                prepared = library.prepare(args["name"])
                inputs, argv = dict(prepared["files"]), list(prepared["argv"])
                try:
                    if "parameters" in args:
                        parameters = args["parameters"]
                        if (not isinstance(parameters, list) or len(parameters) > 20
                                or not all(isinstance(item, str) and len(item) <= 2000 for item in parameters)
                                or len(argv) < 2 or argv[1] not in inputs):
                            raise ValueError("Parameters need a saved file-based script and up to 20 short string arguments")
                        argv = argv[:2] + parameters
                    replacements = args.get("inputs", {})
                    if not isinstance(replacements, dict) or len(replacements) > 16:
                        raise ValueError("Skill input overrides must map up to 16 saved data files to workspace paths")
                    for path, current_path in replacements.items():
                        if (path not in inputs or path in argv[:2] or Path(path).suffix.casefold() not in {".csv", ".tsv", ".json", ".jsonl", ".txt", ".md", ".yaml", ".yml"}):
                            raise ValueError("Override a recorded data file only; saved executable code is immutable")
                        inputs[path] = self.workspace.snapshot([current_path])[current_path]
                    sandbox._validate_command(argv, prepared["timeout"])
                    sandbox._decode_files(inputs)
                except (ValueError, KeyError, TypeError) as exc:
                    raise ToolInputError(str(exc)) from None
                result = await self._run_code(argv, prepared["timeout"], inputs)
                return result | {"skill": prepared["name"], "version": prepared["version"],
                                 "source_event": prepared["event_id"], "modified_inputs_or_arguments": bool(replacements) or "parameters" in args,
                                 "limitations": prepared["limitations"]}
        if name == "task.list":
            return self.queue.list()
        if name == "task.progress":
            return self.queue.progress(args.get("id") or job["id"])
        if name == "task.plan":
            if not self.queue.save_plan(job["id"], args["steps"], lease=job["lease"], summary=args.get("summary", "")):
                raise ValueError("Task is no longer active")
            return self.queue.progress(job["id"])
        if name == "task.schedule":
            now = time.time()
            if job["chat_id"] <= 0:
                raise ToolInputError("Scheduled tasks require Telegram ownership")
            if job.get("kind") == "scheduled":
                raise ToolInputError("A scheduled job cannot create more schedules")
            source = f"schedule:{job['id']}:{step}"
            existing = self.queue.get_by_source(source)
            if existing:
                if existing["chat_id"] != job["chat_id"] or existing["kind"] != "scheduled":
                    raise ToolInputError("Existing schedule ownership does not match")
                return self._schedule_receipt(existing, now)
            try:
                due = schedule_due(args, now=now)
            except ValueError as exc:
                raise ToolInputError(str(exc)) from None
            if not isinstance(args.get("prompt"), str):
                raise ToolInputError("Scheduled task prompt must be text")
            interval = args.get("interval_seconds", 0)
            if type(interval) is not int or not (interval == 0 or 300 <= interval <= 366 * 86400):
                raise ToolInputError("Recurring interval must be an integer: 300 seconds–366 days, or 0")
            # Validate the configured timezone before any queue mutation.
            clock_context(self.settings.timezone, now=due)
            try:
                identifier = self.queue.enqueue(args["prompt"], job["chat_id"], kind="scheduled",
                                                source=source, due=due,
                                                interval_seconds=interval, runs=args.get("runs", 1))
            except ValueError as exc:
                raise ToolInputError(str(exc)) from None
            saved = self.queue.get(identifier)
            return self._schedule_receipt(saved, now)
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
            if name == "self.history":
                return evolution.history(args.get("limit", 8))
            if name == "self.read_experiment":
                return evolution.read_experiment(args["id"], args.get("artifact", "report"), path=args.get("path", ""),
                                                 offset=args.get("offset", 0), limit=args.get("limit", 8000))
        raise ValueError("Unknown or unavailable tool")

    def _schedule_receipt(self, saved, now):
        timing = clock_context(self.settings.timezone, now=saved["due"])
        return {"task_id": saved["id"], "delay_seconds": max(0, saved["due"] - now), "status": saved["state"],
                "due_at": timing["utc"], "local_time": timing["local"], "timezone": timing["timezone"],
                "interval_seconds": saved["interval_seconds"], "runs_left": saved["runs_left"]}

    async def _run_code(self, argv, timeout, inputs):
        manifest = {}
        for path, encoded in inputs.items():
            payload = base64.b64decode(encoded, validate=True)
            manifest[path] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        result = await asyncio.to_thread(sandbox.run_client, self.settings.sandbox_socket, argv, timeout, inputs)
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
        result["execution_status"] = "failed" if result.get("error") or result.get("timed_out") or result.get("exit_code") != 0 else "process_succeeded"
        result["input_manifest"] = manifest
        result["argv"] = argv
        return result
