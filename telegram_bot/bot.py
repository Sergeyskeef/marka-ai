import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import ReplyKeyboardMarkup, KeyboardButton

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
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("ping", self.ping))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("run_code", self.run_code))
        self.application.add_handler(CommandHandler("tools", self.tools))
        self.application.add_handler(CommandHandler("ask", self.ask))
        self.application.add_handler(CommandHandler("mode", self.mode))
        
        # Обработчик для обычных текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        # Записываем метрику
        self._record_bot_metric("start", "success")
        
        welcome_text = """
🚀 **Добро пожаловать в Mark!**

Я — ваш осознанный цифровой компаньон с памятью, инструментами и способностью к планированию.

**Что я умею:**
• 🧠 Помню все наши разговоры
• 🛠️ Выполняю код в безопасной песочнице
• 📝 Планирую задачи и проекты
• 💬 Общаюсь в разных режимах

**Начните с команды /help для получения справки**

Используйте кнопки ниже для быстрого доступа к функциям!
        """
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=self._create_main_keyboard()
        )

    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping"""
        # Записываем метрику
        self._record_bot_metric("ping", "success")
        await update.message.reply_text("pong")

    def _create_main_keyboard(self):
        """Создает главную клавиатуру"""
        keyboard = [
            [KeyboardButton("💬 Chat"), KeyboardButton("👨‍💻 Code"), KeyboardButton("📝 Plan")],
            [KeyboardButton("🛠️ Tools")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        # Записываем метрику
        self._record_bot_metric("help", "success")
        
        help_text = """
🤖 **Доступные команды:**

/ping - проверить работу бота
/help - показать эту справку
/run_code <код> - выполнить код в песочнице
/tools - показать доступные инструменты
/ask <вопрос> - задать вопрос с использованием памяти
/mode [режим] - переключить режим работы

**Режимы работы:**
• chat - обычное общение
• code - анализ кода
• plan - планирование задач

**Примеры:**
• `/run_code print("Hello, World!")`
• `/ask Как меня зовут?`
• `/mode code` - переключить на режим анализа кода
• `/tools`

**💡 Используйте кнопки ниже для быстрого доступа!**
        """
        await update.message.reply_text(
            help_text, 
            parse_mode='Markdown',
            reply_markup=self._create_main_keyboard()
        )

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
            # Предварительная обработка кода
            processed_code = self._preprocess_code(code)
            
            # Выполнение через API
            import requests
            
            response = requests.post(
                "http://app:8000/tools/execute/run_code",
                json={"code": processed_code},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    output = data.get("output", "(пусто)")
                    execution_time = data.get("execution_time", 0)
                    return f"Результат:\n{output}\n\n⏱️ Время выполнения: {execution_time:.2f}с"
                else:
                    return f"Ошибка выполнения:\n{data.get('output', 'Неизвестная ошибка')}"
            else:
                return f"Ошибка API: {response.status_code}"

        except Exception as e:
            raise Exception(f"Ошибка выполнения кода: {str(e)}")
    
    def _preprocess_code(self, code: str) -> str:
        """Предварительная обработка кода для исправления распространенных ошибок"""
        # Заменяем символы умножения
        code = code.replace('×', '*')
        code = code.replace('÷', '/')
        code = code.replace('−', '-')  # длинное тире на обычный минус
        
        # Заменяем кавычки на стандартные
        code = code.replace('"', '"').replace('"', '"')
        code = code.replace(''', "'").replace(''', "'")
        
        # Исправляем print без скобок (для Python 2 совместимости)
        if 'print ' in code and '(' not in code.split('print ')[1][:10]:
            # Это сложная логика, лучше оставить как есть
            pass
        
        return code

    async def tools(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /tools"""
        # Записываем метрику
        self._record_bot_metric("tools", "success")
        
        try:
            import requests
            
            # Получаем список инструментов от API
            response = requests.get("http://app:8000/tools", timeout=10)
            if response.status_code == 200:
                data = response.json()
                tools = data.get("tools", [])
                
                if tools:
                    tools_text = "🛠️ **Доступные инструменты:**\n\n"
                    for tool in tools:
                        tools_text += f"• **{tool['name']}** ({tool['category']})\n"
                        tools_text += f"  _{tool['description']}_\n\n"
                else:
                    tools_text = "📭 Инструменты не найдены"
            else:
                tools_text = "❌ Ошибка получения инструментов"
                
            await update.message.reply_text(tools_text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ask для вопросов с памятью"""
        # Записываем метрику
        self._record_bot_metric("ask", "success")
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите вопрос\nПример: `/ask Как меня зовут?`", 
                parse_mode='Markdown'
            )
            return

        question = ' '.join(context.args)
        chat_id = update.effective_user.id
        
        # Получаем режим пользователя
        user_id = update.effective_user.id
        mode = getattr(self, 'user_modes', {}).get(user_id, "chat")
        
        try:
            import requests
            
            # Отправляем вопрос в API с сохранением в память и режимом
            response = requests.post(
                "http://app:8000/chat/ask",
                json={
                    "question": question,
                    "chat_id": chat_id,
                    "mode": mode
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "Нет ответа")
                context_used = data.get("context_used", False)
                memory_added = data.get("memory_added", False)
                
                # Формируем ответ
                response_text = f"🤖 **Ответ:**\n{answer}\n\n"
                if context_used:
                    response_text += "📚 Использован контекст из памяти\n"
                if memory_added:
                    response_text += "💾 Сохранено в память\n"
                    
            else:
                response_text = f"❌ Ошибка API: {response.status_code}"
                
            await update.message.reply_text(response_text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    def _record_bot_metric(self, command: str, status: str):
        """Запись метрики бота"""
        try:
            import requests
            requests.post(
                "http://app:8000/metrics/record",
                json={
                    "name": "bot_messages_total",
                    "value": 1.0,
                    "labels": {
                        "command": command,
                        "status": status
                    }
                },
                timeout=5
            )
        except Exception as e:
            logger.warning(f"Не удалось записать метрику бота: {e}")

    def set_user_mode(self, user_id: int, mode: str) -> bool:
        """Установка режима пользователя"""
        if not hasattr(self, 'user_modes'):
            self.user_modes = {}
        self.user_modes[user_id] = mode
        return True

    async def send_mode_ack(self, update: Update, mode: str):
        """Отправка подтверждения смены режима"""
        await update.message.reply_text(f"✅ Режим изменен на: **{mode}**", parse_mode='Markdown')

    async def mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /mode для переключения режимов"""
        if not context.args:
            # Показываем доступные режимы
            modes_text = "🎭 **Доступные режимы:**\n\n"
            modes_text += "• **chat** - обычное общение\n"
            modes_text += "• **code** - анализ кода\n"
            modes_text += "• **plan** - планирование задач\n\n"
            modes_text += "Использование: `/mode <режим>`\n"
            modes_text += "Пример: `/mode code`"
            
            await update.message.reply_text(modes_text, parse_mode='Markdown')
            return

        mode = context.args[0].lower()
        valid_modes = ["chat", "code", "plan"]
        
        if mode not in valid_modes:
            await update.message.reply_text(
                f"❌ Неизвестный режим: {mode}\n"
                f"Доступные: {', '.join(valid_modes)}"
            )
            return
        
        # Сохраняем режим в контексте пользователя
        user_id = update.effective_user.id
        self.set_user_mode(user_id, mode)
        await self.send_mode_ack(update, mode)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик обычных текстовых сообщений"""
        # Записываем метрику
        self._record_bot_metric("text_message", "success")
        
        question = update.message.text
        chat_id = update.effective_user.id
        
        # Получаем режим пользователя
        user_id = update.effective_user.id
        mode = getattr(self, 'user_modes', {}).get(user_id, "chat")
        
        try:
            import requests
            
            # Проверяем, не является ли сообщение командой смены режима
            if question.lower() in ["💬 chat", "👨‍💻 code", "📝 plan"]:
                mode_map = {
                    "💬 chat": "chat",
                    "👨‍💻 code": "code", 
                    "📝 plan": "plan"
                }
                new_mode = mode_map[question.lower()]
                self.set_user_mode(user_id, new_mode)
                await self.send_mode_ack(update, new_mode)
                return
            
            # Проверяем, не является ли сообщение командой Tools
            if question.lower() == "🛠️ tools":
                await self.tools(update, context)
                return
            
            # Если режим code - выполняем код
            if mode == "code":
                await self._execute_code_message(update, question)
                return
            
            # Обычный чат
            response = requests.post(
                "http://app:8000/chat/ask",
                json={
                    "question": question,
                    "chat_id": chat_id,
                    "mode": mode
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "Нет ответа")
                context_used = data.get("context_used", False)
                
                # Формируем ответ (убираем "💾 Сохранено в память")
                response_text = f"🤖 {answer}"
                if context_used:
                    response_text += "\n\n📚 Использован контекст из памяти"
                    
            else:
                response_text = f"❌ Ошибка API: {response.status_code}"
                
            await update.message.reply_text(response_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Ошибка обработки текстового сообщения: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def _execute_code_message(self, update: Update, code: str):
        """Выполнение кода в режиме code"""
        try:
            # Отправить сообщение о начале выполнения
            status_message = await update.message.reply_text("🔄 Выполняю код...")

            # Выполнить код в песочнице
            result = await self._execute_code(code)

            # Отправить результат
            await status_message.edit_text(f"✅ **Результат выполнения:**\n```\n{result}\n```", parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ **Ошибка выполнения:**\n```\n{str(e)}\n```", parse_mode='Markdown')

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
