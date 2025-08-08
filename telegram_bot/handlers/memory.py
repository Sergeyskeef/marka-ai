"""
Обработчик команд памяти
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from .base import BaseHandler
from ..keyboards import get_memory_menu_keyboard, get_memory_type_keyboard
from ..middleware.logging import log_error

logger = logging.getLogger(__name__)


class MemoryHandler(BaseHandler):
    """Обработчик команд работы с памятью"""
    
    @log_error
    async def handle_memory_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать меню памяти"""
        query = update.callback_query
        await query.answer()
        
        text = """
🧠 **Управление памятью**

Здесь вы можете:
• 🔍 Искать информацию в памяти
• ➕ Добавить новые знания
• 📊 Посмотреть статистику
• 🗑️ Очистить устаревшие данные

Выберите действие:
"""
        
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_memory_menu_keyboard()
        )
    
    @log_error
    async def handle_memory_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка поиска в памяти"""
        query = update.callback_query
        await query.answer()
        
        # Устанавливаем режим ожидания ввода
        context.user_data["awaiting_memory_search"] = True
        
        await query.edit_message_text(
            "🔍 **Поиск в памяти**\n\n"
            "Отправьте мне текст для поиска, и я найду всю связанную информацию.\n\n"
            "Например:\n"
            "• _Мои предпочтения_\n"
            "• _Что я говорил о Python_\n"
            "• _Наши прошлые разговоры_",
            parse_mode="Markdown"
        )
    
    @log_error
    async def handle_memory_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать меню добавления в память"""
        query = update.callback_query
        await query.answer()
        
        text = """
➕ **Добавить в память**

Выберите тип информации:
• 📝 **Факт** - конкретная информация (имя, дата, предпочтение)
• 📖 **Эпизод** - событие или опыт
• 🎯 **Навык** - умение или способность

Что вы хотите сохранить?
"""
        
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_memory_type_keyboard()
        )
    
    @log_error
    async def handle_memory_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать статистику памяти"""
        query = update.callback_query
        await query.answer()
        
        # Отправляем запрос на получение статистики
        if hasattr(context.bot_data, 'chat_service'):
            response = await context.bot_data['chat_service'].ask_question(
                question="Покажи статистику моей памяти",
                user_id=str(query.from_user.id),
                mode="analysis"
            )
            
            stats_text = context.bot_data['chat_service'].format_response(response)
        else:
            stats_text = "📊 Статистика памяти временно недоступна"
        
        await query.edit_message_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=get_memory_menu_keyboard()
        )
    
    @log_error
    async def process_memory_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка текстового ввода для памяти"""
        if not update.message or not update.message.text:
            return
        
        user_data = context.user_data
        text = update.message.text
        
        # Проверяем режим ожидания
        if user_data.get("awaiting_memory_search"):
            # Выполняем поиск
            await self.send_typing_action(update)
            
            if hasattr(context.bot_data, 'chat_service'):
                response = await context.bot_data['chat_service'].ask_question(
                    question=f"Найди в памяти: {text}",
                    user_id=str(update.effective_user.id),
                    mode="analysis"
                )
                
                result = context.bot_data['chat_service'].format_response(response)
            else:
                result = "🔍 Поиск временно недоступен"
            
            await update.message.reply_text(
                result,
                parse_mode="Markdown",
                reply_markup=get_memory_menu_keyboard()
            )
            
            # Сбрасываем режим
            user_data["awaiting_memory_search"] = False
        
        elif user_data.get("awaiting_memory_add"):
            memory_type = user_data.get("memory_type", "fact")
            
            # Сохраняем в память
            await self.send_typing_action(update)
            
            if hasattr(context.bot_data, 'chat_service'):
                if memory_type == "fact":
                    question = f"Запомни факт: {text}"
                elif memory_type == "episode":
                    question = f"Запомни эпизод: {text}"
                else:
                    question = f"Создай навык: {text}"
                
                response = await context.bot_data['chat_service'].ask_question(
                    question=question,
                    user_id=str(update.effective_user.id),
                    mode="task"
                )
                
                result = "✅ Сохранено в памяти!"
            else:
                result = "💾 Сохранение временно недоступно"
            
            await update.message.reply_text(
                result,
                parse_mode="Markdown",
                reply_markup=get_memory_menu_keyboard()
            )
            
            # Сбрасываем режим
            user_data["awaiting_memory_add"] = False
            user_data["memory_type"] = None


# Функции для регистрации в боте
async def handle_memory_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback для меню памяти"""
    handler = MemoryHandler()
    await handler.handle_memory_menu(update, context)


async def handle_memory_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback для поиска"""
    handler = MemoryHandler()
    await handler.handle_memory_search(update, context)


async def handle_memory_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback для добавления"""
    handler = MemoryHandler()
    await handler.handle_memory_add(update, context)


async def handle_memory_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback для статистики"""
    handler = MemoryHandler()
    await handler.handle_memory_stats(update, context)