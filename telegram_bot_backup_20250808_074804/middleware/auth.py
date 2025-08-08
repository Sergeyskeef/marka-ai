"""
Middleware для авторизации и проверки прав
"""

from functools import wraps
from typing import Callable
import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..config import bot_config

logger = logging.getLogger(__name__)


def check_admin(func: Callable) -> Callable:
    """
    Декоратор для проверки админских прав
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        
        if not user:
            return
        
        if user.id not in bot_config.ADMIN_USERS:
            logger.warning(f"Unauthorized admin access attempt by user {user.id} ({user.username})")
            
            message = "⛔ Эта команда доступна только администраторам."
            
            if update.message:
                await update.message.reply_text(message)
            elif update.callback_query:
                await update.callback_query.answer(message, show_alert=True)
            
            return
        
        # Пользователь - админ, выполняем функцию
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def require_private_chat(func: Callable) -> Callable:
    """
    Декоратор для команд, которые работают только в приватном чате
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "🔒 Эта команда доступна только в приватном чате с ботом."
            )
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper