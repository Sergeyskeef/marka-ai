"""
Клавиатура обратной связи
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Optional


def get_feedback_keyboard(message_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для обратной связи по ответу
    
    Args:
        message_id: ID сообщения для привязки обратной связи
        
    Returns:
        Клавиатура обратной связи
    """
    # Базовые данные для callback
    base_data = f"feedback:{message_id}" if message_id else "feedback"
    
    keyboard = [[
        InlineKeyboardButton("👍", callback_data=f"{base_data}:like"),
        InlineKeyboardButton("👎", callback_data=f"{base_data}:dislike"),
        InlineKeyboardButton("💡 Улучшить", callback_data=f"{base_data}:improve"),
    ]]
    
    return InlineKeyboardMarkup(keyboard)


def get_detailed_feedback_keyboard(
    message_id: Optional[int] = None,
    feedback_type: str = "dislike"
) -> InlineKeyboardMarkup:
    """
    Детальная клавиатура для уточнения обратной связи
    
    Args:
        message_id: ID сообщения
        feedback_type: Тип обратной связи (like/dislike/improve)
        
    Returns:
        Клавиатура с вариантами
    """
    base_data = f"feedback_detail:{message_id}:{feedback_type}"
    
    if feedback_type == "dislike":
        keyboard = [
            [InlineKeyboardButton("❌ Неверный ответ", callback_data=f"{base_data}:wrong")],
            [InlineKeyboardButton("🐌 Слишком медленно", callback_data=f"{base_data}:slow")],
            [InlineKeyboardButton("😕 Непонятный ответ", callback_data=f"{base_data}:unclear")],
            [InlineKeyboardButton("🔄 Не по теме", callback_data=f"{base_data}:offtopic")],
        ]
    elif feedback_type == "improve":
        keyboard = [
            [InlineKeyboardButton("📝 Больше деталей", callback_data=f"{base_data}:details")],
            [InlineKeyboardButton("🎯 Более точный ответ", callback_data=f"{base_data}:accuracy")],
            [InlineKeyboardButton("💬 Другой стиль", callback_data=f"{base_data}:style")],
            [InlineKeyboardButton("🔗 Добавить ссылки", callback_data=f"{base_data}:links")],
        ]
    else:
        keyboard = []
    
    # Добавляем кнопку назад
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data=f"feedback:{message_id}")
    ])
    
    return InlineKeyboardMarkup(keyboard)