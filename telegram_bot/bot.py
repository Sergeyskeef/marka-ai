import asyncio
import logging
import os
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from fastapi import FastAPI
import uvicorn

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
    return {"status": "healthy", "bot": "running"}

class TelegramBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
        
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("ping", self.ping))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("run_code", self.run_code))
        
    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping"""
        await update.message.reply_text("pong")
        
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🤖 **Доступные команды:**

/ping - проверить работу бота
/help - показать эту справку
/run_code <код> - выполнить код в песочнице

Пример: `/run_code print("Hello, World!")`
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
        
    async def run_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /run_code"""
        # Получить код из сообщения
        if not context.args:
            await update.message.reply_text("❌ Укажите код для выполнения\nПример: `/run_code print('Hello')`", parse_mode='Markdown')
            return
            
        code = ' '.join(context.args)
        
        try:
            # Отправить сообщение о начале выполнения
            status_message = await update.message.reply_text("🔄 Выполняю код...")
            
            # Выполнить код в песочнице
            result = await self._execute_code(code)
            
            # Отправить результат
            await status_message.edit_text(f"✅ **Результат выполнения:**\n```\n{result}\n```", parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ **Ошибка выполнения:**\n```\n{str(e)}\n```", parse_mode='Markdown')
    
    async def _execute_code(self, code: str) -> str:
        """Выполнение кода в песочнице"""
        try:
            # Простое выполнение кода (заглушка)
            # TODO: Интеграция с TaskExecutor
            exec_result = {}
            exec(code, exec_result)
            
            # Получить результат (если есть print)
            if 'print' in exec_result:
                return "Код выполнен успешно"
            else:
                return "Код выполнен без вывода"
                
        except Exception as e:
            raise Exception(f"Ошибка выполнения кода: {str(e)}")
    
    async def start(self):
        """Запуск бота"""
        logger.info("Запуск Telegram-бота...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram-бот запущен")
        
    async def stop(self):
        """Остановка бота"""
        logger.info("Остановка Telegram-бота...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Telegram-бот остановлен")

# Глобальный экземпляр бота
bot = None

async def start_bot():
    """Запуск бота и FastAPI сервера"""
    global bot
    
    # Создаем экземпляр бота
    bot = TelegramBot()
    
    # Запускаем бота в отдельной задаче
    bot_task = asyncio.create_task(bot.start())
    
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