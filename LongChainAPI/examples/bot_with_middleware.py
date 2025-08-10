#!/usr/bin/env python3
"""
Пример простого бота с использованием middleware
"""

import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Импортируем middleware
from telegram_bot.middleware import RateLimiter, check_admin, log_error
from telegram_bot.middleware.logging import log_message

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем rate limiter
rate_limiter = RateLimiter(
    default_limit=10,      # 10 запросов
    window_seconds=60,     # за минуту
    admin_multiplier=5     # админы могут делать в 5 раз больше
)

# ID админов (замените на свои)
ADMIN_IDS = [123456789]


# === ОБЫЧНЫЕ КОМАНДЫ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот с middleware. Попробуй:\n"
        "• /help - справка\n"
        "• /admin - админская команда\n"
        "• Напиши что-нибудь - я отвечу!"
    )


@log_error
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help с автоматической обработкой ошибок"""
    help_text = """
📚 **Доступные команды:**

/start - Начать
/help - Эта справка
/admin - Только для админов
/error - Тестовая ошибка
/stats - Статистика rate limit

**Rate limit:** 10 сообщений в минуту
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')


# === АДМИНСКИЕ КОМАНДЫ ===

@check_admin
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда только для админов"""
    await update.message.reply_text(
        "🔐 Секретная админская информация!\n"
        "Ты видишь это, потому что ты админ."
    )


@check_admin
@log_error
async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика пользователя (админская команда)"""
    # Получаем user_id из аргументов или берем текущего пользователя
    if context.args:
        try:
            user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя")
            return
    else:
        user_id = update.effective_user.id
    
    # Получаем статистику
    stats = await rate_limiter.get_user_stats(user_id)
    
    message = f"""
📊 **Rate Limit статистика для {user_id}:**

• Текущие запросы: {stats['current_requests']}/{stats['limit']}
• Осталось: {stats['remaining']}
• Лимит обновится через: {int(stats['window_seconds'])}с
• Статус: {'👑 Админ' if stats['is_admin'] else '👤 Пользователь'}
    """
    
    await update.message.reply_text(message, parse_mode='Markdown')


# === ОБРАБОТКА СООБЩЕНИЙ ===

async def echo_with_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Эхо-бот с rate limiting"""
    # Rate limiter применяется через обертку (см. main)
    
    # Показываем, что печатаем
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    # Отвечаем
    text = update.message.text
    await update.message.reply_text(
        f"Ты написал: _{text}_\n\n"
        f"Это твое сообщение №{await _get_message_count(update.effective_user.id)}",
        parse_mode='Markdown'
    )


# === ТЕСТИРОВАНИЕ ОШИБОК ===

@log_error
async def test_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тестирования обработки ошибок"""
    await update.message.reply_text("Сейчас произойдет ошибка...")
    
    # Генерируем ошибку
    result = 10 / 0  # ZeroDivisionError
    
    # Эта строка не выполнится
    await update.message.reply_text("Ты не увидишь это сообщение")


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def _get_message_count(user_id: int) -> int:
    """Получить количество сообщений пользователя"""
    stats = await rate_limiter.get_user_stats(user_id)
    return stats['current_requests']


def create_rate_limited_handler(handler):
    """Обертка для добавления rate limiting"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Проверяем rate limit
        if await rate_limiter(update, context):
            # Если проверка пройдена, вызываем обработчик
            await handler(update, context)
    return wrapper


# === ГЛАВНАЯ ФУНКЦИЯ ===

def main():
    """Запуск бота"""
    # Получаем токен из переменной окружения
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("Установите BOT_TOKEN!")
        return
    
    # Создаем приложение
    app = Application.builder().token(token).build()
    
    # === РЕГИСТРАЦИЯ MIDDLEWARE ===
    
    # 1. Логирование всех сообщений (выполняется первым)
    app.add_handler(
        MessageHandler(filters.ALL, log_message),
        group=-1
    )
    
    # === РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ===
    
    # Команды без rate limit
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", user_stats))
    app.add_handler(CommandHandler("error", test_error))
    
    # Обработчик текста с rate limit
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            create_rate_limited_handler(echo_with_rate_limit)
        )
    )
    
    # Обработчик ошибок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок"""
        logger.error(f"Exception: {context.error}")
    
    app.add_error_handler(error_handler)
    
    # Устанавливаем админов в конфиг
    app.bot_data['admin_ids'] = ADMIN_IDS
    
    # Запускаем бота
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()