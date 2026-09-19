from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from .app import Application, instance_lock, issue_pairing
from .config import Settings
from .engine import Engine
from .provider import CodexProvider, ProviderError
from .queue import Queue
from .store import Store
from .telegram import TelegramClient, TelegramError


def provider(settings) -> CodexProvider:
    if settings.bridge_socket:
        return settings.provider()
    return CodexProvider(settings.codex_binary, settings.codex_home, settings.model, settings.provider_timeout)


async def doctor(settings, live=False) -> bool:
    store = Store(settings.database)
    with store._connect() as connection:
        database_ok = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    result = {"database_ok": database_ok, "owner_paired": bool(store.get_meta("owner_id")),
              "telegram_token_configured": bool(settings.token), "protected_bridge": bool(settings.bridge_socket),
              "code_runner_socket": bool(settings.sandbox_socket and Path(settings.sandbox_socket).exists())}
    if settings.bridge_socket:
        from .bridge_client import bridge_status
        try:
            status = await bridge_status(settings.bridge_socket)
            result["bridge"] = status
            result["telegram_token_configured"] = bool(status.get("telegram_available"))
        except Exception:
            result["bridge"] = {"available": False}
    try:
        result["codex"] = await provider(settings).status()
    except ProviderError as exc:
        result["codex"] = {"authenticated": False, "error": str(exc)}
    if live and result["codex"].get("authenticated"):
        schema = {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"], "additionalProperties": False}
        if not store.claim_budget(settings.daily_calls):
            raise ValueError("Daily provider budget exhausted")
        value = await provider(settings).complete("Return reply MARKA_OK. No tools.", schema)
        result["codex_live_ok"] = value == {"reply": "MARKA_OK"}
    if settings.token or settings.bridge_socket:
        try:
            client = settings.telegram() if settings.bridge_socket else TelegramClient(settings.token)
            me = await client.get_me()
            hook = await client.call("getWebhookInfo", {})
            result["telegram"] = {"username": me.get("username"), "webhook_active": bool(hook.get("url"))}
        except TelegramError as exc:
            result["telegram"] = {"error": str(exc)}
    telegram = result.get("telegram", {})
    ready = (database_ok and bool(result["codex"].get("authenticated"))
             and result["telegram_token_configured"] and "error" not in telegram and not telegram.get("webhook_active", False)
             and (not live or result.get("codex_live_ok", False)))
    result["ready"] = ready
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return ready


def login(settings) -> int:
    if settings.bridge_socket:
        raise ValueError("Codex login belongs to the protected bridge; ask the operator to authenticate that single installation")
    # The official CLI owns the auth flow and refresh. No token parsing/copying.
    env = dict(os.environ)
    for key in list(env):
        if any(part in key.upper() for part in ("TOKEN", "API_KEY", "SECRET", "PASSWORD")):
            env.pop(key)
    env["CODEX_HOME"] = str(settings.codex_home)
    return subprocess.call([settings.codex_binary, "login", "--device-auth"], env=env)


def import_memory(settings, source: Path, accept=False) -> int:
    if source.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Import limit is 5 MiB; split larger archives first")
    payload = json.loads(source.read_text("utf-8"))
    if not isinstance(payload, list) or len(payload) > 1000:
        raise ValueError("Import expects a JSON list of up to 1000 content/kind/level/key records")
    # Validate every record before changing the store.
    for row in payload:
        if not isinstance(row, dict) or not isinstance(row.get("content"), str) or not row["content"].strip() or not 1 <= len(row["content"]) <= 6000:
            raise ValueError("Each record needs content of 1–6000 characters")
        default_level = 2 if row.get("kind") == "lesson" else 1
        if not isinstance(row.get("kind", "fact"), str) or row.get("kind", "fact") not in {"fact", "lesson", "skill", "preference"} or type(row.get("level", default_level)) is not int or row.get("level", default_level) not in {0, 1, 2}:
            raise ValueError("Invalid imported memory kind or level")
        if row.get("key") is not None and (not isinstance(row["key"], str) or not row["key"].strip()):
            raise ValueError("Invalid imported memory key")
        if row.get("source") is not None and (not isinstance(row["source"], str) or len(row["source"]) > 2000):
            raise ValueError("Imported source must be a string of at most 2000 characters")
        # Reject escaped unpaired Unicode surrogates before any earlier record is written.
        for value in (row["content"], row.get("key"), row.get("source")):
            if isinstance(value, str):
                value.encode("utf-8")
    store = Store(settings.database)
    for row in payload:
        source_id = store.event("user" if accept else "import", row["content"], session="import",
                                meta={"source": (row.get("source") or source.name)[:512],
                                      "import_file": source.name, "owner_reviewed": accept})
        store.remember(row["content"], kind=row.get("kind", "fact"), level=row.get("level", 2 if row.get("kind") == "lesson" else 1), key=row.get("key"),
                       sources=[source_id], status="accepted" if accept else "candidate", actor="owner" if accept else "import", evidence_kind="direct_fact" if accept else "third_party_claim")
    return len(payload)


async def chat(settings, text: str):
    store, queue = Store(settings.database), Queue(settings.database)
    # CLI chat uses its own state directory or the same exclusive lock as the gateway.
    with instance_lock(settings.data_dir / "gateway.lock"):
        if any(job["state"] in {"queued", "running"} for job in queue.list(10000)):
            raise ValueError("Use an idle or separate --data directory for CLI chat")
        identifier = queue.enqueue(text, 0)
        queue.configure_task(identifier, max_steps=settings.task_max_steps, max_model_calls=settings.task_max_calls,
                             max_seconds=settings.task_max_seconds)
        job = queue.claim()
        if job is None or job["id"] != identifier:
            raise ValueError("There are earlier queued tasks. Use a fresh --data directory for a CLI smoke test.")
        engine = Engine(settings, store, queue, provider(settings))
        while job is not None:
            result = await engine.run(job)
            current = queue.get(identifier)
            if current["state"] != "queued":
                print(result or current["result"] or current["error"])
                break
            job = queue.claim()
            if job is None or job["id"] != identifier:
                raise ValueError("Task continuation was not available; progress remains saved")


def models(settings, action, limit=64):
    from .semantic import SemanticIndex, install_model
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("Index limit must be 1–10000 source records")
    directory = settings.data_dir / "models" / "multilingual-minilm"
    if action == "install":
        with instance_lock(settings.data_dir / "index.lock"):
            return install_model(directory)
    index = SemanticIndex(Store(settings.database), directory)
    if action == "status":
        return index.stats()
    if action == "index":
        with instance_lock(settings.data_dir / "index.lock"):
            return index.update(max_sources=limit)
    raise ValueError("Unknown models action")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Марк: Telegram, память и автономные поручения через Codex")
    parser.add_argument("--data", help="Private persistent state directory (or MARKA_DATA)")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="Enter bot token privately and create pairing code")
    setup.add_argument("--model", help="Optional Codex model; omit to use CLI default")
    setup.add_argument("--timezone", help="Owner timezone: UTC+03:00 or installed IANA zone; default UTC")
    commands.add_parser("login", help="Sign in to Codex with device authentication")
    commands.add_parser("pair", help="Issue a new owner pairing code before first pairing")
    commands.add_parser("run", help="Run the Telegram gateway and durable worker")
    check = commands.add_parser("doctor", help="Read-only local/auth/Telegram checks, no Telegram messages")
    check.add_argument("--live", action="store_true", help="Make one minimal Codex inference request")
    backup = commands.add_parser("backup", help="Consistent SQLite backup; no credentials included")
    backup.add_argument("path", type=Path)
    importer = commands.add_parser("import-memory", help="Import private knowledge records from JSON")
    importer.add_argument("path", type=Path)
    importer.add_argument("--accept", action="store_true", help="Explicitly mark these owner-reviewed records accepted")
    archive_parser = commands.add_parser("import-archive", help="Import private JSONL history as unverified source events")
    archive_parser.add_argument("path", type=Path)
    archive_parser.add_argument("--source", required=True, help="Stable private archive source label for deduplication")
    model_parser = commands.add_parser("models", help="Install or inspect the optional local multilingual retrieval model")
    model_parser.add_argument("action", choices=("install", "status", "index"))
    model_parser.add_argument("--limit", type=int, default=64, help="Maximum sources to index in this invocation (1–10000)")
    chat_parser = commands.add_parser("chat", help="One CLI interaction without Telegram")
    chat_parser.add_argument("text")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings.load(args.data)
        if args.command == "setup":
            if settings.bridge_socket:
                raise ValueError("Protected installations are paired and configured by the operator's bridge setup")
            if args.timezone:
                from .scheduling import owner_timezone
                owner_timezone(args.timezone)
                settings.timezone = args.timezone
            token = settings.token or getpass.getpass("Токен нового Telegram-бота (ввод скрыт): ").strip()
            if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{25,}", token):
                raise ValueError("Некорректный формат токена Telegram")
            settings.token, settings.model = token, args.model or settings.model
            asyncio.run(TelegramClient(token).get_me())
            settings.save()
            store = Store(settings.database)
            if not store.get_meta("owner_id"):
                print("После запуска отправь новому боту только из своего личного чата:\n/start " + issue_pairing(store))
            print("Настройки сохранены вне репозитория. Затем: marka login; marka doctor --live; marka run")
        elif args.command == "pair":
            print("/start " + issue_pairing(Store(settings.database)))
        elif args.command == "login":
            raise SystemExit(login(settings))
        elif args.command == "doctor":
            raise SystemExit(0 if asyncio.run(doctor(settings, args.live)) else 1)
        elif args.command == "backup":
            print(Store(settings.database).backup(args.path))
        elif args.command == "import-memory":
            print(f"Imported records: {import_memory(settings, args.path, args.accept)}")
        elif args.command == "import-archive":
            from .archive import import_archive
            print(json.dumps(import_archive(Store(settings.database), args.path, args.source), ensure_ascii=False, indent=2))
        elif args.command == "models":
            print(json.dumps(models(settings, args.action, args.limit), ensure_ascii=False, indent=2))
        elif args.command == "chat":
            asyncio.run(chat(settings, args.text))
        elif args.command == "run":
            if not settings.token and not settings.bridge_socket:
                raise ValueError("Сначала выполни marka setup")
            asyncio.run(Application(settings).run())
    except KeyboardInterrupt:
        print("Марк остановлен. Состояние сохранено.")
    except (ValueError, ProviderError, TelegramError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
