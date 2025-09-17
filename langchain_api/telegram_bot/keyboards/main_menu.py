"""
Главное меню бота
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Optional


def get_main_menu_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """
    Получить клавиатуру главного меню
    
    Args:
        user_id: ID пользователя для персонализации
        
    Returns:
        Клавиатура главного меню
    """
    keyboard = [
        [
            InlineKeyboardButton("💬 Новый чат", callback_data="menu:chat:new"),
        ],
        [
            InlineKeyboardButton("🧭 Режим", callback_data="menu:mode"),
            InlineKeyboardButton("🧠 Память", callback_data="menu:memory"),
            InlineKeyboardButton("📚 Обучение", callback_data="menu:learning"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="menu:settings"),
            InlineKeyboardButton("❓ Помощь", callback_data="menu:help"),
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_chat_mode_keyboard(current_mode: str = "chat") -> InlineKeyboardMarkup:
    """
    Клавиатура выбора режима чата
    
    Args:
        current_mode: Текущий режим
        
    Returns:
        Клавиатура выбора режима
    """
    modes = [
        ("chat", "💬 Обычный чат", "Дружеская беседа"),
        ("task", "📋 Режим задач", "Помощь в задачах"),
        ("analysis", "🔍 Анализ", "Глубокий анализ"),
    ]
    
    keyboard = []
    
    for mode_id, mode_name, mode_desc in modes:
        # Отмечаем текущий режим
        if mode_id == current_mode:
            button_text = f"✅ {mode_name}"
        else:
            button_text = mode_name
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"chat:mode:{mode_id}"
            )
        ])
    
    # Кнопка назад
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="menu:main")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = [[
        InlineKeyboardButton("❌ Отмена", callback_data="action:cancel")
    ]]
    return InlineKeyboardMarkup(keyboard)