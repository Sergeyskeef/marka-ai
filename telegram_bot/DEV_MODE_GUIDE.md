# 🔧 Режим разработки для Telegram бота

## 🎯 Что такое Dev Mode?

**Dev Mode (Режим разработки)** - это специальный режим работы бота, который отключает все ограничения для удобства разработки и тестирования.

## ✅ Что отключается в Dev Mode?

1. **Проверка админских прав** - все пользователи считаются админами
2. **Rate limiting** - все получают увеличенный лимит (90 запросов/мин вместо 30)
3. **Ограничения команд** - доступны все команды без проверок

## 🚀 Как включить/выключить?

### Способ 1: Через переменную окружения
```bash
# Включить Dev Mode (по умолчанию)
export BOT_DEV_MODE=true

# Выключить Dev Mode (production)
export BOT_DEV_MODE=false
```

### Способ 2: В .env файле
```env
# .env
BOT_DEV_MODE=true  # для разработки
# BOT_DEV_MODE=false  # для production
```

### Способ 3: В docker-compose.yml
```yaml
services:
  bot:
    environment:
      - BOT_DEV_MODE=true  # для разработки
```

## 🔍 Как проверить текущий режим?

При запуске бота в логах будет сообщение:
```
🔧 Bot running in DEV MODE - all users are admins!
```

Или для production:
```
🔒 Bot running in PRODUCTION MODE - admin checks enabled
```

## 📝 Что изменилось в коде?

### 1. **Конфигурация** (`telegram_bot/config.py`)
```python
# Новый параметр
DEV_MODE: bool = os.getenv("BOT_DEV_MODE", "true").lower() == "true"
```

### 2. **Auth Middleware** (`telegram_bot/middleware/auth.py`)
```python
# Проверка режима
if bot_config.DEV_MODE:
    # Все пользователи - админы
    logger.debug(f"Admin access granted - DEV MODE")
else:
    # Обычная проверка прав
    if user.id not in bot_config.ADMIN_USERS:
        # Отказ в доступе
```

### 3. **Rate Limiter** (`telegram_bot/middleware/rate_limiter.py`)
```python
def get_limit_for_user(self, user_id: int) -> int:
    # В Dev Mode все получают админский лимит
    if bot_config.DEV_MODE:
        return self.default_limit * self.admin_multiplier
    
    # В production - обычная логика
    if user_id in bot_config.ADMIN_USERS:
        return self.default_limit * self.admin_multiplier
    return self.default_limit
```

## ⚠️ Важно для Production!

Перед деплоем в production **обязательно**:

1. Установите `BOT_DEV_MODE=false`
2. Добавьте реальные Telegram ID админов в `ADMIN_USERS`
3. Проверьте rate limits
4. Протестируйте ограничения доступа

## 🎯 Пример настройки для production

### .env.production
```env
# Отключаем Dev Mode
BOT_DEV_MODE=false

# Указываем админов (Telegram User ID)
ADMIN_USERS=123456789,987654321

# Включаем логирование для безопасности
LOG_USER_MESSAGES=true

# Устанавливаем токен
BOT_TOKEN=your_production_bot_token
```

## 🔒 Безопасность

1. **Никогда** не используйте `DEV_MODE=true` в production
2. **Всегда** проверяйте настройки перед деплоем
3. **Логируйте** все админские действия
4. **Мониторьте** использование команд

## 📊 Отладка

В Dev Mode в логах будут сообщения:
- `Admin access granted to user XXX - DEV MODE`
- `User XXX gets admin rate limit - DEV MODE`

Это помогает отслеживать, что режим разработки активен.

## 🎉 Преимущества

1. **Удобство разработки** - не нужно добавлять свой ID в админы
2. **Быстрое тестирование** - нет ограничений rate limit
3. **Безопасность** - легко переключиться в production режим
4. **Прозрачность** - видно в логах что работает Dev Mode

---

**Помните**: Dev Mode - только для разработки! В production всегда используйте `BOT_DEV_MODE=false`!