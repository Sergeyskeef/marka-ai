"""
Обработчик команды /start
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from .base import BaseHandler
from ..keyboards import get_main_menu_keyboard
from ..middleware.logging import log_error

logger = logging.getLogger(__name__)


class StartHandler(BaseHandler):
    """Обработчик команды /start"""
    
    @log_error
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /start"""
        user = update.effective_user
        
        # Приветственное сообщение
        welcome_text = f"""
🤖 *Привет, {user.first_name}!*

Я — Марк, твой персональный AI-ассистент с продвинутой системой памяти и самообучения.

*Что я умею:*
• 💬 Вести дружескую беседу и помогать с задачами
• 🧠 Запоминать важную информацию о тебе
• 📚 Учиться на нашем взаимодействии
• 🔍 Искать информацию в своей памяти
• 📊 Анализировать и улучшать свои навыки

*Основные команды:*
/help - подробная справка
/chat - начать новый диалог
/memory - управление памятью
/learn - запустить обучение

Выбери действие из меню ниже или просто напиши мне сообщение!
"""
        
        # Сохраняем информацию о пользователе
        self.set_user_data(context, "user_id", str(user.id))
        self.set_user_data(context, "username", user.username)
        self.set_user_data(context, "first_name", user.first_name)
        
        # Устанавливаем режим чата по умолчанию
        self.set_chat_mode(context, "chat")
        
        # Отправляем приветствие с клавиатурой
        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard(user.id)
        )
        
        logger.info(f"User {user.id} ({user.username}) started the bot")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Функция для регистрации в боте"""
    handler = StartHandler()
    await handler.handle(update, context)