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
import nest_asyncio

# Применяем nest_asyncio для решения проблем с event loop в Docker
nest_asyncio.apply()

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

# Используем абсолютные импорты
from telegram_bot.config import bot_config
from telegram_bot.middleware import RateLimiter, log_message
from telegram_bot.handlers.start import start_command
from telegram_bot.handlers.chat import handle_text_message, handle_chat_mode_callback
from telegram_bot.handlers.memory import (
    handle_memory_menu, handle_memory_search, 
    handle_memory_add, handle_memory_stats
)
from telegram_bot.services import ChatService

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, bot_config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarkBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.config = bot_config
        self.app: Optional[Application] = None
        self.chat_service: Optional[ChatService] = None
        self.rate_limiter = RateLimiter()
    
    async def setup(self):
        """Инициализация бота"""
        # Проверяем конфигурацию
        self.config.validate()
        
        # Создаем сервисы
        self.chat_service = ChatService()
        
        # Создаем приложение
        self.app = (
            ApplicationBuilder()
            .token(self.config.BOT_TOKEN)
            .build()
        )
        
        # Сохраняем сервисы в bot_data для доступа из обработчиков
        self.app.bot_data['chat_service'] = self.chat_service
        
        # Регистрируем обработчики
        self._register_handlers()
        
        # Устанавливаем команды бота
        await self._set_bot_commands()
        
        # Логируем режим работы
        if self.config.DEV_MODE:
            logger.warning("🔧 Bot running in DEV MODE - all users are admins!")
        else:
            logger.info("🔒 Bot running in PRODUCTION MODE - admin checks enabled")
        
        logger.info("✅ Bot initialized successfully")
    
    def _register_handlers(self):
        """Регистрация всех обработчиков"""
        if not self.app:
            return
        
        # Middleware для логирования
        self.app.add_handler(
            MessageHandler(filters.ALL, log_message),
            group=-1  # Выполняется первым
        )
        
        # Rate limiter как pre-handler
        # Будет вызываться перед основными обработчиками
        
        # Команды
        self.app.add_handler(CommandHandler("start", start_command))
        self.app.add_handler(CommandHandler("help", self._help_command))
        
        # Текстовые сообщения (основной чат)
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        )
        
        # Callback queries (кнопки)
        self.app.add_handler(CallbackQueryHandler(handle_memory_menu, pattern="^memory:"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_search, pattern="^search:"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_add, pattern="^add_memory:"))
        self.app.add_handler(CallbackQueryHandler(handle_memory_stats, pattern="^stats:"))
        self.app.add_handler(CallbackQueryHandler(handle_chat_mode_callback, pattern="^mode:"))
        
        logger.info("📝 Handlers registered")
    
    async def _set_bot_commands(self):
        """Установка команд бота в меню"""
        commands = [
            BotCommand("start", "🏠 Главное меню"),
            BotCommand("help", "❓ Справка"),
            BotCommand("chat", "💬 Начать диалог"),
            BotCommand("memory", "🧠 Управление памятью"),
            BotCommand("learn", "📚 Запустить обучение"),
            BotCommand("settings", "⚙️ Настройки"),
            BotCommand("cancel", "❌ Отменить действие"),
        ]
        
        await self.app.bot.set_my_commands(commands)
        logger.info("📋 Bot commands set")
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🤖 **Марк - AI Ассистент**

**Основные команды:**
• /start - Главное меню
• /help - Эта справка
• /chat - Начать новый диалог
• /memory - Работа с памятью
• /learn - Запустить обучение
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
        
        await update.message.reply_text(
            help_text,
            parse_mode="Markdown"
        )
    
    async def run(self):
        """Запуск бота"""
        if not self.app:
            await self.setup()
        
        # Запускаем polling
        logger.info("🚀 Starting bot polling...")
        await self.app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
    
    async def stop(self):
        """Остановка бота"""
        if self.app:
            await self.app.stop()
            logger.info("🛑 Bot stopped")


# Точка входа
async def main():
    """Главная функция"""
    bot = MarkBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("⌨️ Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await bot.stop()


if __name__ == "__main__":
    # Запускаем event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")