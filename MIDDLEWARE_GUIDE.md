# 📚 Руководство по Middleware в Telegram Боте

## 🎯 Что такое Middleware?

Middleware - это промежуточные обработчики, которые выполняются **до** или **после** основных обработчиков команд. Они позволяют:

- 🛡️ Проверять права доступа
- 📊 Логировать действия
- 🚦 Ограничивать частоту запросов
- 🔧 Обрабатывать ошибки
- 📝 Модифицировать данные

## 🏗️ Реализованные Middleware

### 1. **Rate Limiter** (`middleware/rate_limiter.py`)

Ограничивает количество запросов от пользователя за определенный период.

**Особенности:**
- 30 запросов в минуту для обычных пользователей
- 90 запросов в минуту для админов (x3)
- Автоматическая очистка старых запросов
- Информативные сообщения о превышении лимита

**Использование:**
```python
# В main.py
rate_limiter = RateLimiter()

# Оборачиваем обработчик
self.app.add_handler(
    MessageHandler(
        filters.TEXT,
        self._rate_limited_handler(handle_text_message)
    )
)

def _rate_limited_handler(self, handler):
    async def wrapper(update, context):
        if await self.rate_limiter(update, context):
            await handler(update, context)
    return wrapper
```

### 2. **Auth Middleware** (`middleware/auth.py`)

Проверяет права доступа пользователей.

**Декораторы:**

#### `@check_admin`
Проверяет, является ли пользователь администратором:

```python
from telegram_bot.middleware.auth import check_admin

@check_admin
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Эта команда доступна только админам"""
    await update.message.reply_text("Секретная админская информация!")
```

#### `@require_private_chat`
Требует, чтобы команда использовалась только в приватном чате:

```python
from telegram_bot.middleware.auth import require_private_chat

@require_private_chat
async def private_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Работает только в приватном чате"""
    await update.message.reply_text("Это сообщение видно только в приватном чате")
```

### 3. **Logging Middleware** (`middleware/logging.py`)

Логирует все входящие сообщения и ошибки.

**Функции:**

#### `log_message`
Автоматически логирует все сообщения:

```python
# Регистрируется первым с group=-1
self.app.add_handler(
    MessageHandler(filters.ALL, log_message),
    group=-1
)
```

**Логируемые данные:**
- Timestamp
- User ID и username
- Chat ID и тип чата
- Тип сообщения (text, photo, callback)
- Первые 100 символов текста

#### `@log_error`
Декоратор для автоматического логирования и обработки ошибок:

```python
from telegram_bot.middleware.logging import log_error

@log_error
async def some_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ошибки будут автоматически залогированы"""
    # Если произойдет ошибка, пользователь получит дружелюбное сообщение
    result = 10 / 0  # Ошибка!
```

## 🔧 Конфигурация

Настройки middleware находятся в `telegram_bot/config.py`:

```python
# Rate limiting
RATE_LIMIT_REQUESTS: int = 30  # Запросов
RATE_LIMIT_WINDOW: int = 60    # За 60 секунд

# Админы (Telegram ID)
ADMIN_USERS: List[int] = [123456789, 987654321]

# Логирование
LOG_USER_MESSAGES: bool = True  # Логировать сообщения
```

## 📝 Создание собственного Middleware

### Пример: Middleware для проверки времени работы

```python
# middleware/working_hours.py
from datetime import datetime, time

class WorkingHoursMiddleware:
    def __init__(self, start_hour=9, end_hour=18):
        self.start = time(start_hour, 0)
        self.end = time(end_hour, 0)
    
    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        current_time = datetime.now().time()
        
        if not (self.start <= current_time <= self.end):
            await update.message.reply_text(
                "🕐 Бот работает с 9:00 до 18:00.\n"
                "Попробуйте позже!"
            )
            return False
        
        return True
```

### Использование:

```python
# В main.py
working_hours = WorkingHoursMiddleware(9, 18)

# Применяем к обработчику
async def handle_with_hours_check(update, context):
    if await working_hours(update, context):
        await actual_handler(update, context)
```

## 🎯 Best Practices

### 1. **Порядок выполнения**
```python
# Логирование - первым (group=-1)
app.add_handler(MessageHandler(filters.ALL, log_message), group=-1)

# Rate limiting - вторым (обертка)
app.add_handler(MessageHandler(filters.TEXT, rate_limited_handler))

# Основной обработчик - последним
```

### 2. **Комбинирование middleware**
```python
@check_admin
@require_private_chat
@log_error
async def secure_admin_command(update, context):
    """Команда с тройной защитой"""
    pass
```

### 3. **Кастомные сообщения об ошибках**
```python
def custom_error_handler(message="Произошла ошибка"):
    def decorator(func):
        async def wrapper(update, context):
            try:
                return await func(update, context)
            except Exception as e:
                await update.message.reply_text(f"❌ {message}")
                logger.error(f"Error: {e}")
        return wrapper
    return decorator
```

## 📊 Мониторинг

### Получение статистики rate limiter:

```python
# Добавить команду в бота
@check_admin
async def rate_limit_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(context.args[0]) if context.args else update.effective_user.id
    
    stats = await bot.rate_limiter.get_user_stats(user_id)
    
    message = f"""
📊 Rate Limit статистика:
• Текущие запросы: {stats['current_requests']}/{stats['limit']}
• Осталось: {stats['remaining']}
• Окно: {stats['window_seconds']}с
• Админ: {'✅' if stats['is_admin'] else '❌'}
"""
    await update.message.reply_text(message)
```

## 🚀 Примеры использования в проекте

### 1. **Защищенная админская команда:**
```python
@check_admin
@log_error
async def reset_user_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс памяти пользователя (только для админов)"""
    if not context.args:
        await update.message.reply_text("Использование: /reset_memory <user_id>")
        return
    
    user_id = context.args[0]
    # ... логика сброса памяти
```

### 2. **Rate-limited API запрос:**
```python
async def handle_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Rate limiter уже применен через обертку в main.py
    
    # Показываем индикатор набора
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    # Делаем запрос к AI
    response = await chat_service.ask_question(
        question=update.message.text,
        user_id=str(update.effective_user.id)
    )
    
    await update.message.reply_text(response)
```

### 3. **Логирование с контекстом:**
```python
@log_error
async def process_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка файла с автоматическим логированием ошибок"""
    document = update.message.document
    
    logger.info(f"Processing file: {document.file_name} from user {update.effective_user.id}")
    
    # Если произойдет ошибка, она будет залогирована
    # и пользователь получит дружелюбное сообщение
    file = await context.bot.get_file(document.file_id)
    # ... обработка файла
```

## 🎉 Преимущества использования Middleware

1. **Разделение ответственности** - бизнес-логика отделена от проверок
2. **Переиспользование** - один middleware для многих обработчиков
3. **Чистый код** - обработчики содержат только основную логику
4. **Безопасность** - централизованные проверки прав
5. **Мониторинг** - единая точка для логирования
6. **Масштабируемость** - легко добавлять новые middleware

## 🔗 Связанные файлы

- `/workspace/telegram_bot/middleware/` - Все middleware
- `/workspace/telegram_bot/config.py` - Конфигурация
- `/workspace/telegram_bot/main.py` - Регистрация middleware
- `/workspace/telegram_bot/handlers/` - Использование в обработчиках