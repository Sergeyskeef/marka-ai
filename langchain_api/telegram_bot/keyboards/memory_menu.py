"""
Меню управления памятью
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Optional, List, Dict


def get_memory_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Главное меню управления памятью
    """
    keyboard = [
        [
            InlineKeyboardButton("🔍 Поиск", callback_data="memory:search"),
            InlineKeyboardButton("➕ Добавить", callback_data="memory:add"),
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="memory:stats"),
            InlineKeyboardButton("🗑️ Очистить", callback_data="memory:clear"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="menu:main")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_memory_type_keyboard() -> InlineKeyboardMarkup:
    """
    Выбор типа памяти для добавления
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Факт", callback_data="memory:add:fact"),
            InlineKeyboardButton("📖 Эпизод", callback_data="memory:add:episode"),
        ],
        [
            InlineKeyboardButton("🎯 Навык", callback_data="memory:add:skill"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="menu:memory")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_memory_search_results_keyboard(
    results: List[Dict],
    page: int = 0,
    per_page: int = 5
) -> InlineKeyboardMarkup:
    """
    Клавиатура с результатами поиска
    
    Args:
        results: Список результатов
        page: Текущая страница
        per_page: Результатов на страницу
    """
    keyboard = []
    
    # Добавляем кнопки для каждого результата
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(results))
    
    for i in range(start_idx, end_idx):
        result = results[i]
        # Сокращаем текст для кнопки
        text = result.get("text", "")[:30] + "..."
        callback_data = f"memory:view:{result.get('id', '')}"
        
        keyboard.append([
            InlineKeyboardButton(text, callback_data=callback_data)
        ])
    
    # Навигация по страницам
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=f"memory:search:page:{page-1}")
        )
    
    nav_buttons.append(
        InlineKeyboardButton(f"{page+1}/{(len(results)-1)//per_page + 1}", callback_data="noop")
    )
    
    if end_idx < len(results):
        nav_buttons.append(
            InlineKeyboardButton("➡️", callback_data=f"memory:search:page:{page+1}")
        )
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка назад
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="menu:memory")
    ])
    
    return InlineKeyboardMarkup(keyboard)