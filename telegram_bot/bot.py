#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот «Марк» v2.1  (фикс передачи chat_id + упрощённый API)

• /start       – приветствие
• /sync        – копировать проект в /sandbox
• !<cmd>       – shell-команда в /sandbox
• текст        – вопрос Марку  (POST /chat/ask → ответ + запись в Memory)
"""

from __future__ import annotations
import asyncio, logging, os, textwrap
from typing import Final

import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters,
)

BOT_TOKEN: Final[str | None] = os.getenv("BOT_TOKEN")
APP_HOST:  Final[str]       = os.getenv("APP_HOST", "http://app:8000")
TIMEOUT:   Final[int]       = int(os.getenv("BOT_TIMEOUT", "40"))

if not BOT_TOKEN:
    raise SystemExit("❌  BOT_TOKEN отсутствует в .env – бот остановлен")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
_http = httpx.AsyncClient(timeout=TIMEOUT)

# ────────── helpers ──────────────────────────────────────────────────
async def _post(url: str, payload: dict | None = None) -> httpx.Response:
    r = await _http.post(url, json=payload)
    r.raise_for_status()
    return r

async def _chat_ask(question: str, chat_id: int) -> str | None:
    """Один вызов: и ответ, и запись в Memory."""
    try:
        r = await _post(
            f"{APP_HOST}/chat/ask",
            {"question": question, "chat_id": chat_id},
        )
        return r.json()["answer"].strip()
    except Exception as e:
        logging.error("ask error: %s", e, exc_info=True)
        return None

async def _sandbox_sync() -> bool:
    try:
        await _post(f"{APP_HOST}/sandbox/sync")
        return True
    except Exception as e:
        logging.error("sync error: %s", e)
        return False

async def _sandbox_exec(cmd: str) -> str:
    try:
        r = await _post(f"{APP_HOST}/sandbox/exec", {"command": cmd})
        d = r.json()
        return textwrap.dedent(f"""\
            🖥️ *sandbox exec*
            `$ {d['cmd']}`
            _exit {d['returncode']}_

            ```stdout
            {d['stdout'] or '(пусто)'}
            ```

            ```stderr
            {d['stderr'] or '(пусто)'}
            ```
        """)[:4000]
    except Exception as e:
        logging.error("run error: %s", e)
        return f"⚠️ run error: {e}"

# ────────── Telegram callbacks ───────────────────────────────────────
async def start_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Я — Марк (MVP).")

async def sync_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    ok = await _sandbox_sync()
    await update.message.reply_text(
        "✅ Скопировал проект в /sandbox" if ok else "⚠️ sync error (см. логи)"
    )

async def text_msg(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    if text.startswith("!"):                          # shell-команда
        out = await _sandbox_exec(text[1:].strip())
        await update.message.reply_markdown_v2(out)
        return

    chat_id = update.effective_chat.id
    answer = await _chat_ask(text, chat_id)
    if answer is None:
        await update.message.reply_text("⚠️ Нет ответа — проверь логи `bot`/`app`")
        return
    await update.message.reply_text(answer)

# ────────── entrypoint ───────────────────────────────────────────────
def main() -> None:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .read_timeout(TIMEOUT)
        .write_timeout(TIMEOUT)
        .build()
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("sync",  sync_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))

    logging.info("🤖 Bot started, polling…")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()

