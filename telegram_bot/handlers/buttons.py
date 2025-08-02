import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from langchain_api.core.memory.prefs import upsert_user_pref, get_user_pref

logger = logging.getLogger(__name__)

class PreferenceButtons:
    """Обработчики для inline-кнопок предпочтений пользователей"""
    
    @staticmethod
    def create_style_keyboard() -> InlineKeyboardMarkup:
        """Создает клавиатуру для выбора стиля ответа"""
        keyboard = [
            [
                InlineKeyboardButton("🎯 Кратко", callback_data="pref:style:brief"),
                InlineKeyboardButton("📝 Подробно", callback_data="pref:style:detailed")
            ],
            [
                InlineKeyboardButton("🎨 Креативно", callback_data="pref:style:creative"),
                InlineKeyboardButton("🔬 Аналитично", callback_data="pref:style:analytical")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_detail_level_keyboard() -> InlineKeyboardMarkup:
        """Создает клавиатуру для выбора уровня детализации"""
        keyboard = [
            [
                InlineKeyboardButton("⚡ Быстро", callback_data="pref:detail_level:quick"),
                InlineKeyboardButton("📊 Средне", callback_data="pref:detail_level:medium")
            ],
            [
                InlineKeyboardButton("🔍 Детально", callback_data="pref:detail_level:detailed"),
                InlineKeyboardButton("📚 Полно", callback_data="pref:detail_level:comprehensive")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_feedback_keyboard() -> InlineKeyboardMarkup:
        """Создает клавиатуру для обратной связи"""
        keyboard = [
            [
                InlineKeyboardButton("👍 Хорошо", callback_data="feedback:positive"),
                InlineKeyboardButton("👎 Плохо", callback_data="feedback:negative")
            ],
            [
                InlineKeyboardButton("🔄 Повторить", callback_data="feedback:retry"),
                InlineKeyboardButton("📝 Уточнить", callback_data="feedback:clarify")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_preferences_menu_keyboard() -> InlineKeyboardMarkup:
        """Создает главное меню предпочтений"""
        keyboard = [
            [
                InlineKeyboardButton("🎨 Стиль ответа", callback_data="menu:style"),
                InlineKeyboardButton("📊 Уровень детализации", callback_data="menu:detail_level")
            ],
            [
                InlineKeyboardButton("📈 Статистика", callback_data="menu:stats"),
                InlineKeyboardButton("🔄 Сбросить", callback_data="menu:reset")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

async def handle_preference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-запросов для предпочтений"""
    query = update.callback_query
    await query.answer()  # Убираем "часики" у кнопки
    
    user_id = str(query.from_user.id)
    data = query.data
    
    try:
        if data.startswith("pref:"):
            # Обработка предпочтений
            _, key, value = data.split(":")
            success = upsert_user_pref(user_id, key, value)
            
            if success:
                await query.edit_message_text(
                    f"✅ Предпочтение сохранено!\n"
                    f"**{key}**: {value}",
                    parse_mode='Markdown'
                )
                logger.info(f"Пользователь {user_id} установил предпочтение {key}={value}")
            else:
                await query.edit_message_text(
                    "❌ Ошибка сохранения предпочтения. Попробуйте позже.",
                    parse_mode='Markdown'
                )
                
        elif data.startswith("feedback:"):
            # Обработка обратной связи
            _, feedback_type = data.split(":")
            await handle_feedback(query, user_id, feedback_type)
            
        elif data.startswith("menu:"):
            # Обработка меню
            _, menu_type = data.split(":")
            await handle_menu(query, user_id, menu_type)
            
    except Exception as e:
        logger.error(f"Ошибка обработки callback {data}: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка. Попробуйте позже.",
            parse_mode='Markdown'
        )

async def handle_feedback(query, user_id: str, feedback_type: str):
    """Обработка обратной связи"""
    feedback_messages = {
        "positive": "👍 Спасибо за положительную оценку!",
        "negative": "👎 Спасибо за обратную связь. Я постараюсь улучшиться.",
        "retry": "🔄 Попробую ответить по-другому.",
        "clarify": "📝 Пожалуйста, уточните ваш вопрос."
    }
    
    message = feedback_messages.get(feedback_type, "Спасибо за обратную связь!")
    
    # Сохраняем обратную связь в предпочтениях
    upsert_user_pref(user_id, "last_feedback", feedback_type)
    
    await query.edit_message_text(message, parse_mode='Markdown')
    logger.info(f"Пользователь {user_id} оставил обратную связь: {feedback_type}")

async def handle_menu(query, user_id: str, menu_type: str):
    """Обработка меню предпочтений"""
    if menu_type == "style":
        keyboard = PreferenceButtons.create_style_keyboard()
        await query.edit_message_text(
            "🎨 Выберите стиль ответа:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
    elif menu_type == "detail_level":
        keyboard = PreferenceButtons.create_detail_level_keyboard()
        await query.edit_message_text(
            "📊 Выберите уровень детализации:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
    elif menu_type == "stats":
        await show_preferences_stats(query, user_id)
        
    elif menu_type == "reset":
        await reset_preferences(query, user_id)

async def show_preferences_stats(query, user_id: str):
    """Показывает статистику предпочтений пользователя"""
    from langchain_api.core.memory.prefs import get_all_user_prefs
    
    prefs = get_all_user_prefs(user_id)
    
    if not prefs:
        await query.edit_message_text(
            "📈 У вас пока нет сохраненных предпочтений.\n"
            "Используйте кнопки выше, чтобы настроить стиль общения!",
            parse_mode='Markdown'
        )
        return
    
    stats_text = "📈 **Ваши предпочтения:**\n\n"
    for key, value in prefs.items():
        if key != "last_feedback":  # Не показываем технические данные
            stats_text += f"• **{key}**: {value}\n"
    
    keyboard = PreferenceButtons.create_preferences_menu_keyboard()
    await query.edit_message_text(
        stats_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def reset_preferences(query, user_id: str):
    """Сбрасывает все предпочтения пользователя"""
    from langchain_api.core.memory.prefs import get_all_user_prefs, delete_user_pref
    
    prefs = get_all_user_prefs(user_id)
    deleted_count = 0
    
    for key in prefs.keys():
        if delete_user_pref(user_id, key):
            deleted_count += 1
    
    await query.edit_message_text(
        f"🔄 Сброшено {deleted_count} предпочтений.\n"
        "Все настройки вернулись к значениям по умолчанию.",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user_id} сбросил {deleted_count} предпочтений")

def get_preference_handlers():
    """Возвращает список обработчиков для предпочтений"""
    return [
        CallbackQueryHandler(handle_preference_callback, pattern="^(pref:|feedback:|menu:)")
    ]

# Функции для интеграции с основным ботом
def add_preference_buttons_to_bot(application):
    """Добавляет обработчики предпочтений к боту"""
    handlers = get_preference_handlers()
    for handler in handlers:
        application.add_handler(handler)

def create_preferences_command():
    """Создает команду /preferences для бота"""
    async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /preferences"""
        keyboard = PreferenceButtons.create_preferences_menu_keyboard()
        await update.message.reply_text(
            "⚙️ **Настройки предпочтений**\n\n"
            "Здесь вы можете настроить стиль общения со мной:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    return preferences_command 