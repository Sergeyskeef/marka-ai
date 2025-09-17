#!/usr/bin/env python3
"""
Telegram Bot - Марк v3.0
Модульная архитектура с интеграцией продвинутых возможностей
"""

import logging
import asyncio
import sys
import os
from typing import Optional

# Добавляем путь к корню проекта для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from telegram_bot.config import bot_config
from telegram_bot.middleware import RateLimiter, log_message
from telegram_bot.handlers.start import start_command
from telegram_bot.handlers.chat import handle_text_message, handle_chat_mode_callback
from telegram_bot.handlers.memory import (
    handle_memory_menu, handle_memory_search, 
    handle_memory_add, handle_memory_stats
)
from telegram_bot.services import ChatService

logging.basicConfig(
    level=getattr(logging, bot_config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


class MarkBot:
    def __init__(self):
        self.config = bot_config
        self.app: Optional[Application] = None
        self.chat_service: Optional[ChatService] = None
        self.rate_limiter = RateLimiter()
    
    async def setup(self):
        self.config.validate()
        self.chat_service = ChatService()
        self.app = (
            ApplicationBuilder()
            .token(self.config.BOT_TOKEN)
            .build()
        )
        self.app.bot_data['chat_service'] = self.chat_service
        self._register_handlers()
        await self._set_bot_commands()
        if self.config.DEV_MODE:
            logger.warning("🔧 Bot running in DEV MODE - all users are admins!")
        else:
            logger.info("🔒 Bot running in PRODUCTION MODE - admin checks enabled")
        logger.info("✅ Bot initialized successfully")
    
    def _register_handlers(self):
        if not self.app:
            return
        self.app.add_handler(
            MessageHandler(filters.ALL, log_message),
            group=-1
        )
        self.app.add_handler(CommandHandler("start", start_command))
        self.app.add_handler(CommandHandler("help", self._help_command))
        self.app.add_handler(CommandHandler("learn", self._learn_command))
        self.app.add_handler(CommandHandler(["debug", "debag"], self._debug_command))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        )
        from telegram_bot.handlers.menu import handle_menu_callback
        self.app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^menu:"))
        # Переключение режима чата (chat:mode:<id>)
        self.app.add_handler(CallbackQueryHandler(handle_chat_mode_callback, pattern="^chat:mode:"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_menu, pattern="^memory:($|menu|search|add|stats|clear|view|add:|search:page:)"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_search, pattern="^memory:search$"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_add, pattern="^memory:add$|^memory:add:(fact|episode|skill)$"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_stats, pattern="^memory:stats$"))
        logger.info("📝 Handlers registered")
    
    async def _set_bot_commands(self, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
        commands = [
            BotCommand("start", "🏠 Главное меню"),
            BotCommand("help", "❓ Справка"),
            BotCommand("chat", "💬 Начать диалог"),
            BotCommand("memory", "🧠 Управление памятью"),
            BotCommand("learn", "📚 Запустить обучение"),
            BotCommand("debug", "🛠 Диагностика последнего ответа"),
            BotCommand("settings", "⚙️ Настройки"),
            BotCommand("cancel", "❌ Отменить действие"),
        ]
        await self.app.bot.set_my_commands(commands)
        logger.info("📋 Bot commands set")
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🤖 **Марк - AI Ассистент**

**Основные команды:**
• /start - Главное меню
• /help - Эта справка
• /chat - Начать новый диалог
• /memory - Работа с памятью
• /learn - Запустить обучение
• /debug - Краткая диагностика последнего ответа (тайминги, токены, шаги)
• /settings - Настройки
• /cancel - Отменить текущее действие

**Режимы чата:**
• 💬 Обычный - стандартный диалог
• 📝 Задачи - планирование и выполнение
• 🔍 Анализ - глубокий анализ темы

**Возможности:**
• 🧠 Долговременная память
• 🎯 25+ инструментов
• 📚 Самообучение (REAP)
• 🔄 Контекстные диалоги

Просто отправьте сообщение для начала диалога!
        """
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def _debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать отладочную информацию по последнему ответу."""
        try:
            last = context.user_data.get("last_response") or {}
            if not last:
                # Фолбэк: запросить с API последний debug
                try:
                    assert self.chat_service is not None
                    r = await self.chat_service.client.get("/api/chat/debug/last")
                    if r.status_code == 200:
                        data = r.json()
                        last = data.get("debug") or {}
                    else:
                        await update.message.reply_text("Отладочной информации пока нет.")
                        return
                except Exception:
                    await update.message.reply_text("Отладочной информации пока нет.")
                    return
            meta = last.get("metadata") or {}
            parts = ["🛠 Debug"]
            # timings
            t = meta.get("timings") or {}
            if t:
                keys = ["pre_llm_ms","llm_first_call_ms","llm_call_ms","tools_phase_ms","agent_total_ms","total_ms"]
                tm = ", ".join(f"{k}={int(t[k])}ms" for k in keys if isinstance(t.get(k), (int, float)))
                if tm:
                    parts.append("⏱ " + tm)
            # progress
            p = meta.get("progress") or {
                "rounds": meta.get("rounds"),
                "tool_calls": meta.get("tool_calls_count"),
                "llm_calls": meta.get("llm_calls"),
            }
            pr = ", ".join(f"{k}={v}" for k, v in p.items() if v is not None)
            if pr:
                parts.append("📊 " + pr)
            # tokens
            if meta.get("tokens_used"):
                parts.append(f"🔢 tokens_used={meta['tokens_used']}")
            # sizes
            s = meta.get("sizes") or {}
            if s:
                line = ", ".join(
                    f"{k}={s[k]}" for k in ("message_chars","est_tokens_before","est_tokens_after") if s.get(k) is not None
                )
                if line:
                    parts.append("📦 " + line)
            # tool calls
            tools = last.get("tool_calls") or []
            if tools:
                tool_names = ", ".join(sorted({(tc.get("name") or "unknown") for tc in tools}))
                parts.append("🔧 tools: " + tool_names)
            await update.message.reply_text("\n".join(parts))
        except Exception as e:
            await update.message.reply_text(f"Ошибка /debug: {e}")

    async def _learn_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск REAP цикла обучения по команде /learn."""
        try:
            msg = await update.message.reply_text("📚 Запускаю обучение (REAP)…")
            chat_id = msg.chat_id
            message_id = msg.message_id

            async def _run():
                try:
                    from app.learning.reap_cycle import reap_cycle
                    res = await reap_cycle.run_learning_cycle(auto_mode=False)
                    ref = res.get("reflection", {})
                    kn = res.get("knowledge", {})
                    app = res.get("application", {})
                    txt = (
                        "✅ Обучение завершено\n"
                        f"Эпизод: {res.get('episode_id','—')}\n"
                        f"Инсайтов: {ref.get('insights', 0)}; Паттернов: {ref.get('patterns_found', 0)}\n"
                        f"Фактов: {kn.get('facts_extracted', 0)}; Навыков к обновлению: {kn.get('skills_to_update', 0)}; Уроков: {kn.get('lessons_learned', 0)}\n"
                        f"Применение: {app if isinstance(app, str) else app.get('facts_saved',0)} фактов сохранено"
                    )
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=txt)
                except Exception as e:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"❌ Ошибка обучения: {e}")

            import asyncio
            asyncio.create_task(_run())
        except Exception as e:
            await update.message.reply_text(f"❌ Не удалось запустить обучение: {e}")


async def main():
    bot = MarkBot()
    try:
        await bot.setup()
        logger.info("🚀 Starting bot polling...")
        assert bot.app is not None
        app = bot.app
        # Ручной жизненный цикл, чтобы не трогать внешний event loop
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        logger.info("✅ Bot polling started")
        # Блокируемся навсегда; остановка через SIGTERM/SIGINT контейнера
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("⌨️ Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")