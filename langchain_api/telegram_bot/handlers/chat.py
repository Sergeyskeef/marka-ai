"""
Обработчик чата - основная функциональность
"""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from .base import BaseHandler
from ..keyboards import get_feedback_keyboard
from ..services import ChatService
from ..middleware.logging import log_error
from telegram.helpers import escape_markdown

logger = logging.getLogger(__name__)


class ChatHandler(BaseHandler):
    """Обработчик текстовых сообщений и чата"""
    
    def __init__(self, chat_service: ChatService):
        super().__init__(chat_service)
        self.chat_service = chat_service
    
    @log_error
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка текстового сообщения"""
        message = update.message
        if not message or not message.text:
            return
        
        user = update.effective_user
        text = message.text.strip()
        
        # Пропускаем команды
        if text.startswith('/'):
            return
        
        # Показываем индикатор набора
        await self.send_typing_action(update)
        
        # Получаем режим чата
        chat_mode = self.get_chat_mode(context)
        
        # Отправляем запрос в API
        response = await self.chat_service.ask_question(
            question=text,
            user_id=str(user.id),
            chat_id=message.chat_id,
            mode=chat_mode
        )
        
        # Форматируем ответ
        formatted_response = self.chat_service.format_response(response)
        # Экранируем Markdown для предотвращения BadRequest: Can't parse entities
        # Используем MarkdownV2 как более строгий вариант
        safe_response = escape_markdown(formatted_response, version=2)
        
        # Разбиваем длинный ответ на части
        message_parts = self.split_long_message(safe_response)
        
        # Отправляем ответ
        sent_messages = []
        for i, part in enumerate(message_parts):
            # Добавляем клавиатуру обратной связи только к последней части
            if i == len(message_parts) - 1:
                sent_message = await message.reply_text(
                    part,
                    parse_mode="MarkdownV2",
                    reply_markup=get_feedback_keyboard(message.message_id)
                )
            else:
                sent_message = await message.reply_text(
                    part,
                    parse_mode="MarkdownV2"
                )
            sent_messages.append(sent_message)
        
        # Сохраняем ID последнего сообщения для обратной связи
        if sent_messages:
            self.set_user_data(context, f"response_{message.message_id}", sent_messages[-1].message_id)
        
        # Логируем
        tool_calls = response.get('tool_calls') if isinstance(response, dict) else None
        tools_used_count = len(tool_calls) if isinstance(tool_calls, list) else 0
        logger.info(
            f"Chat response sent to user {user.id}: "
            f"mode={chat_mode}, tools_used={tools_used_count}"
        )
    
    async def handle_mode_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка изменения режима чата"""
        query = update.callback_query
        await query.answer()
        
        # Извлекаем новый режим из callback_data
        # Формат: chat:mode:{mode}
        parts = query.data.split(':')
        if len(parts) >= 3:
            new_mode = parts[2]
            self.set_chat_mode(context, new_mode)
            
            mode_names = {
                "chat": "💬 Обычный чат",
                "task": "📋 Режим задач",
                "analysis": "🔍 Анализ"
            }
            
            await query.edit_message_text(
                f"✅ Режим изменен на: {mode_names.get(new_mode, new_mode)}\n\n"
                f"Теперь я буду отвечать в соответствии с выбранным режимом.",
                parse_mode="Markdown"
            )
            
            logger.info(f"User {query.from_user.id} changed chat mode to {new_mode}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Функция для регистрации в боте"""
    # Получаем или создаем chat_service
    if not hasattr(context.bot_data, 'chat_service'):
        context.bot_data['chat_service'] = ChatService()
    
    handler = ChatHandler(context.bot_data['chat_service'])
    await handler.handle(update, context)


async def handle_chat_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка callback для изменения режима"""
    if not hasattr(context.bot_data, 'chat_service'):
        context.bot_data['chat_service'] = ChatService()
    
    handler = ChatHandler(context.bot_data['chat_service'])
    await handler.handle_mode_change(update, context)