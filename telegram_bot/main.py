#!/usr/bin/env python3
"""
Telegram Bot - Марк v3.0
Модульная архитектура с интеграцией продвинутых возможностей
"""

import logging
import asyncio
from typing import Optional

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

from config import bot_config
from middleware import RateLimiter, log_message
from handlers.start import start_command
from handlers.chat import handle_text_message, handle_chat_mode_callback
from handlers.memory import (
    handle_memory_menu, handle_memory_search, 
    handle_memory_add, handle_memory_stats
)
from services import ChatService

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
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._rate_limited_handler(handle_text_message)
            )
        )
        
        # Callback queries
        self.app.add_handler(
            CallbackQueryHandler(
                handle_chat_mode_callback,
                pattern="^chat:mode:"
            )
        )
        
        # Memory callbacks
        self.app.add_handler(
            CallbackQueryHandler(handle_memory_menu, pattern="^menu:memory$")
        )
        self.app.add_handler(
            CallbackQueryHandler(handle_memory_search, pattern="^memory:search$")
        )
        self.app.add_handler(
            CallbackQueryHandler(handle_memory_add, pattern="^memory:add$")
        )
        self.app.add_handler(
            CallbackQueryHandler(handle_memory_stats, pattern="^memory:stats$")
        )
        
        # Обработчик ошибок
        self.app.add_error_handler(self._error_handler)
        
        logger.info("📋 Handlers registered")
    
    def _rate_limited_handler(self, handler):
        """Обертка для добавления rate limiting к обработчику"""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # Проверяем rate limit
            if await self.rate_limiter(update, context):
                # Если проверка пройдена, вызываем обработчик
                await handler(update, context)
        
        return wrapper
    
    async def _set_bot_commands(self):
        """Установка команд бота в UI Telegram"""
        commands = [
            BotCommand("start", "🚀 Начать работу с ботом"),
            BotCommand("help", "❓ Показать справку"),
            BotCommand("chat", "💬 Начать новый диалог"),
            BotCommand("memory", "🧠 Управление памятью"),
            BotCommand("learn", "📚 Запустить обучение"),
            BotCommand("settings", "⚙️ Настройки"),
            BotCommand("cancel", "❌ Отменить текущее действие"),
        ]
        
        await self.app.bot.set_my_commands(commands)
        logger.info("✅ Bot commands set")
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📖 *Справка по боту*

*Основные команды:*
• /start - начать работу с ботом
• /help - показать эту справку
• /chat - начать новый диалог
• /memory - управление памятью
• /learn - запустить обучение
• /settings - настройки бота

*Как использовать:*
1. Просто отправьте мне сообщение, и я отвечу
2. Используйте кнопки меню для навигации
3. Выберите режим чата для разных задач

*Режимы чата:*
• 💬 Обычный - дружеская беседа
• 📋 Задачи - помощь в выполнении задач
• 🔍 Анализ - глубокий анализ темы

*Обратная связь:*
Используйте кнопки 👍/👎 под ответами, чтобы помочь мне улучшаться!
"""
        
        await update.message.reply_text(
            help_text,
            parse_mode="Markdown"
        )
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Отправляем сообщение пользователю
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "😔 Произошла ошибка при обработке вашего запроса.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
    
    async def run(self):
        """Запуск бота"""
        if not self.app:
            await self.setup()
        
        logger.info("🚀 Starting bot...")
        
        # Запускаем polling
        await self.app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Shutting down bot...")
        
        # Закрываем сервисы
        if self.chat_service:
            await self.chat_service.close()
        
        # Останавливаем приложение
        if self.app:
            await self.app.shutdown()
        
        logger.info("✅ Bot shutdown complete")


async def main():
    """Главная функция"""
    bot = MarkBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())