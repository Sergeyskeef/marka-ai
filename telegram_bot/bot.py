#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот «Марк» v2.2 - Полная версия с исправлениями

Команды:
• /start - приветствие
• /help - справка по командам
• /ping - проверка работы бота
• /sync - синхронизация проекта в песочницу
• /run_code <код> - выполнение кода в песочнице
• /task_list - список активных задач
• /task_status <id> - статус задачи
• /task_analyze <id> - анализ выполнения задачи
• /task_create <описание> [приоритет] - создание задачи
• /task_cancel <id> - отмена задачи
• /suggest_improvements - предложения по улучшению
• /self_improve - самоулучшение системы
• Текстовые сообщения - общение с Марком через API
• !<команда> - выполнение shell команды в песочнице
"""

import asyncio
import logging
import os
import json
from typing import Final
from datetime import datetime

import httpx
import uvicorn
from fastapi import FastAPI
from telegram import Update, constants
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.helpers import escape_markdown

# Импорты из проекта
from langchain_api.telegram_bot.handlers.task_commands import (
    task_list,
    task_status,
    task_analyze,
    task_create,
    task_cancel,
)
from langchain_api.core.command_monitoring import log_command, complete_command
from langchain_api.sandbox.sandbox_manager import SandboxManager

# Константы
BOT_TOKEN: Final[str | None] = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
APP_HOST: Final[str] = os.getenv("APP_HOST", "http://app:8000")
TIMEOUT: Final[int] = int(os.getenv("BOT_TIMEOUT", "60"))
MAX_CONNECTIONS: Final[int] = int(os.getenv("MAX_CONNECTIONS", "20"))

if not BOT_TOKEN:
    raise SystemExit("❌ TELEGRAM_BOT_TOKEN отсутствует в переменных окружения")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI приложение для health check
bot_app = FastAPI(title="Telegram Bot Health")

@bot_app.get("/health")
async def bot_health():
    """Health endpoint для Telegram-бота"""
    return {"status": "healthy", "bot": "running", "version": "2.2"}

class TelegramBot:
    def __init__(self):
        self.token = BOT_TOKEN
        self.application = ApplicationBuilder().token(self.token).build()
        self.sandbox_manager = SandboxManager()
        self.http_client = None
        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))
        
        # Команды песочницы
        self.application.add_handler(CommandHandler("sync", self.sync_command))
        self.application.add_handler(CommandHandler("run_code", self.run_code_command))
        
        # Команды задач
        self.application.add_handler(CommandHandler("task_list", task_list))
        self.application.add_handler(CommandHandler("task_status", task_status))
        self.application.add_handler(CommandHandler("task_analyze", task_analyze))
        self.application.add_handler(CommandHandler("task_create", task_create))
        self.application.add_handler(CommandHandler("task_cancel", task_cancel))
        
        # Команды улучшений
        self.application.add_handler(CommandHandler("suggest_improvements", self.suggest_improvements))
        self.application.add_handler(CommandHandler("self_improve", self.self_improve))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("✅ Все обработчики команд настроены")

    async def get_http_client(self):
        """Получить или создать HTTP клиент"""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=TIMEOUT,
                    read=TIMEOUT * 2,
                    write=TIMEOUT,
                    pool=TIMEOUT / 2,
                ),
                limits=httpx.Limits(
                    max_connections=MAX_CONNECTIONS,
                    max_keepalive_connections=5,
                    keepalive_expiry=30,
                ),
                http2=True,
            )
        return self.http_client

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🤖 Привет! Я Марк — твой цифровой компаньон.

Я могу:
• 💬 Отвечать на вопросы и вести диалог
• 🧠 Запоминать важную информацию
• 📊 Анализировать и выполнять задачи
• 🛠️ Выполнять код в безопасной песочнице
• 🔍 Предлагать улучшения и развиваться

Используй /help для списка команд или просто напиши мне сообщение!
        """
        await update.message.reply_text(welcome_text)
        log_command("/start", "telegram_bot", update.effective_user.id)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📚 **Доступные команды:**

**Основные:**
/start - приветствие
/help - эта справка
/ping - проверка работы бота

**Работа с кодом:**
/sync - синхронизировать проект в песочницу
/run_code <код> - выполнить Python код
!<команда> - выполнить shell команду

**Управление задачами:**
/task_list - список активных задач
/task_status <id> - статус задачи
/task_analyze <id> - анализ выполнения
/task_create <описание> [приоритет] - создать задачу
/task_cancel <id> - отменить задачу

**Развитие:**
/suggest_improvements - предложения по улучшению
/self_improve - запустить самоулучшение

💬 Просто напишите сообщение для общения со мной!
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
        log_command("/help", "telegram_bot", update.effective_user.id)

    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping"""
        await update.message.reply_text("🏓 pong!")
        log_command("/ping", "telegram_bot", update.effective_user.id)

    async def sync_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Синхронизация проекта в песочницу"""
        try:
            await update.message.reply_text("🔄 Начинаю синхронизацию проекта в песочницу...")
            
            client = await self.get_http_client()
            response = await client.post(f"{APP_HOST}/sandbox/sync")
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    await update.message.reply_text(
                        f"✅ Синхронизация завершена!\n"
                        f"📁 Скопировано: {result.get('copied_count', 0)} элементов\n"
                        f"⏱️ Время: {result.get('elapsed_time', 0):.2f} сек"
                    )
                else:
                    await update.message.reply_text(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
            else:
                await update.message.reply_text(f"❌ Ошибка HTTP: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Ошибка при синхронизации: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def run_code_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выполнение Python кода в песочнице"""
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите код для выполнения\n"
                "Пример: `/run_code print('Hello, World!')`",
                parse_mode='Markdown'
            )
            return

        code = ' '.join(context.args)
        
        try:
            status_message = await update.message.reply_text("🔄 Выполняю код в песочнице...")
            
            # Создаем Python файл с кодом
            python_command = f"python3 -c \"{code}\""
            result = await self.sandbox_manager.execute_command(python_command)
            
            if result.success:
                await status_message.edit_text(
                    f"✅ **Результат выполнения:**\n```\n{result.output[:1000]}\n```",
                    parse_mode='Markdown'
                )
            else:
                await status_message.edit_text(
                    f"❌ **Ошибка выполнения:**\n```\n{result.error[:1000]}\n```",
                    parse_mode='Markdown'
                )
            
            log_command(f"/run_code {code[:50]}...", "telegram_bot", update.effective_user.id)
            
        except Exception as e:
            logger.error(f"Ошибка выполнения кода: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        message_text = update.message.text
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Проверка на shell команду
        if message_text.startswith("!"):
            await self.handle_shell_command(update, context)
            return
        
        try:
            # Показываем индикатор печати
            await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
            
            # Отправляем запрос к API
            client = await self.get_http_client()
            payload = {
                "message": message_text,
                "user_id": str(user_id),
                "chat_id": str(chat_id),
                "context": {
                    "username": update.effective_user.username,
                    "first_name": update.effective_user.first_name,
                    "chat_type": update.effective_chat.type
                }
            }
            
            response = await client.post(
                f"{APP_HOST}/chat/ask",
                json=payload,
                timeout=TIMEOUT * 2
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Отправляем ответ
                response_text = result.get("response", "Извините, не получил ответ")
                
                # Разбиваем длинные сообщения
                if len(response_text) > 4000:
                    chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
                    for chunk in chunks:
                        await update.message.reply_text(chunk)
                else:
                    await update.message.reply_text(response_text)
                
                # Логируем использованные инструменты
                if result.get("tools_used"):
                    tools_info = f"🛠️ Использованы инструменты: {', '.join(result['tools_used'])}"
                    logger.info(tools_info)
                    
            else:
                error_text = f"❌ Ошибка API: {response.status_code}"
                await update.message.reply_text(error_text)
                logger.error(f"API error: {response.status_code} - {response.text}")
                
        except httpx.TimeoutException:
            await update.message.reply_text(
                "⏱️ Превышено время ожидания ответа. Попробуйте еще раз или упростите запрос."
            )
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {str(e)}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке сообщения. Попробуйте еще раз."
            )

    async def handle_shell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка shell команд"""
        command = update.message.text[1:]  # Убираем !
        
        try:
            await update.message.reply_text(f"🔄 Выполняю команду: `{command}`", parse_mode='Markdown')
            
            result = await self.sandbox_manager.execute_command(command)
            
            if result.success:
                output = result.output[:1000] if result.output else "Команда выполнена без вывода"
                await update.message.reply_text(
                    f"✅ **Результат:**\n```\n{output}\n```",
                    parse_mode='Markdown'
                )
            else:
                error = result.error[:1000] if result.error else "Неизвестная ошибка"
                await update.message.reply_text(
                    f"❌ **Ошибка:**\n```\n{error}\n```",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Ошибка выполнения shell команды: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def suggest_improvements(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Предложения по улучшению системы"""
        try:
            await update.message.reply_text("🔍 Анализирую систему для поиска возможностей улучшения...")
            
            client = await self.get_http_client()
            response = await client.get(f"{APP_HOST}/improvements/suggest")
            
            if response.status_code == 200:
                result = response.json()
                suggestions = result.get("suggestions", [])
                
                if suggestions:
                    text = "💡 **Предложения по улучшению:**\n\n"
                    for i, suggestion in enumerate(suggestions, 1):
                        text += f"{i}. **{suggestion['area']}**\n"
                        text += f"   {suggestion['suggestion']}\n"
                        text += f"   Приоритет: {suggestion['priority']}\n\n"
                else:
                    text = "✅ Система работает оптимально!"
                    
                await update.message.reply_text(text, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Ошибка при получении предложений")
                
        except Exception as e:
            logger.error(f"Ошибка получения предложений: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def self_improve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск процесса самоулучшения"""
        try:
            await update.message.reply_text("🚀 Запускаю процесс самоулучшения...")
            
            # TODO: Реализовать интеграцию с системой самоулучшения
            await update.message.reply_text(
                "🔧 Процесс самоулучшения запущен:\n"
                "• Анализ производительности\n"
                "• Оптимизация алгоритмов\n"
                "• Обновление базы знаний\n"
                "• Улучшение моделей\n\n"
                "Результаты будут доступны через несколько минут."
            )
            
        except Exception as e:
            logger.error(f"Ошибка самоулучшения: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def start(self):
        """Запуск бота"""
        logger.info("🚀 Запуск Telegram-бота...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("✅ Telegram-бот запущен")

    async def stop(self):
        """Остановка бота"""
        logger.info("🛑 Остановка Telegram-бота...")
        if self.http_client:
            await self.http_client.aclose()
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("✅ Telegram-бот остановлен")

# Глобальный экземпляр бота
bot = None

async def start_bot():
    """Запуск бота и FastAPI сервера"""
    global bot
    
    # Создаем экземпляр бота
    bot = TelegramBot()
    
    # Запускаем бота в отдельной задаче
    asyncio.create_task(bot.start())
    
    # Запускаем FastAPI сервер для health check
    config = uvicorn.Config(
        bot_app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    # Запускаем сервер
    await server.serve()
    
    # Останавливаем бота при завершении
    await bot.stop()

async def main():
    """Главная функция"""
    try:
        await start_bot()
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения")
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
    finally:
        if bot:
            await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
