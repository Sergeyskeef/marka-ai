"""
Middleware для логирования
"""

import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..config import bot_config

logger = logging.getLogger(__name__)


async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Логирует входящие сообщения если включено в конфигурации
    """
    if not bot_config.LOG_USER_MESSAGES:
        return
    
    user = update.effective_user
    chat = update.effective_chat
    
    # Базовая информация
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "chat_id": chat.id if chat else None,
        "chat_type": chat.type if chat else None,
    }
    
    # Определяем тип update
    if update.message:
        log_data["type"] = "message"
        log_data["text"] = update.message.text[:100] if update.message.text else None
        log_data["has_photo"] = bool(update.message.photo)
        log_data["has_document"] = bool(update.message.document)
    
    elif update.callback_query:
        log_data["type"] = "callback_query"
        log_data["data"] = update.callback_query.data
    
    elif update.inline_query:
        log_data["type"] = "inline_query"
        log_data["query"] = update.inline_query.query[:50]
    
    # Логируем
    logger.info(f"User activity: {log_data}")


def log_error(func):
    """
    Декоратор для логирования ошибок в обработчиках.
    Корректно работает как для функций, так и для методов класса
    (первый аргумент может быть `self`).
    """

    async def wrapper(*args, **kwargs):
        # Определяем `update` и `context` независимо от того, метод это или функция
        update: Update | None = kwargs.get("update")  # type: ignore[assignment]
        context: ContextTypes.DEFAULT_TYPE | None = kwargs.get("context")  # type: ignore[assignment]

        # Поиск по позиционным аргументам
        if update is None:
            for arg in args:
                if isinstance(arg, Update):
                    update = arg
                    break
        if context is None:
            for arg in args:
                # У контекста как правило есть атрибуты `bot` и `application`
                if hasattr(arg, "bot") and hasattr(arg, "application"):
                    context = arg  # type: ignore[assignment]
                    break

        try:
            return await func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            # Безопасно собираем дополнительные поля
            user_id = None
            chat_id = None
            try:
                if update is not None:
                    user_id = update.effective_user.id if update.effective_user else None
                    chat_id = update.effective_chat.id if update.effective_chat else None
            except Exception:
                pass

            logger.error(
                f"Error in {func.__name__}: {str(e)}",
                exc_info=True,
                extra={
                    "user_id": user_id,
                    "chat_id": chat_id,
                },
            )

            # Пытаемся уведомить пользователя, если это возможно
            try:
                error_message = (
                    "😔 Произошла ошибка при обработке вашего запроса.\n"
                    "Попробуйте еще раз или обратитесь к администратору."
                )
                if update and getattr(update, "message", None):
                    await update.message.reply_text(error_message)  # type: ignore[union-attr]
                elif update and getattr(update, "callback_query", None):
                    await update.callback_query.answer(error_message, show_alert=True)  # type: ignore[union-attr]
            except Exception:
                # Игнорируем ошибки нотификации пользователя
                pass

            # Перебрасываем исключение дальше для глобальной обработки
            raise

    return wrapper