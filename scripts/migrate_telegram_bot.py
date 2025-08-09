#!/usr/bin/env python3
"""
Скрипт миграции Telegram бота на новую архитектуру
"""

import os
import shutil
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backup_old_bot():
    """Создать резервную копию старого бота"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/workspace/telegram_bot_backup_{timestamp}"
    
    if os.path.exists("/workspace/telegram_bot/bot.py"):
        logger.info(f"Creating backup in {backup_dir}")
        shutil.copytree("/workspace/telegram_bot", backup_dir)
        return backup_dir
    else:
        logger.warning("Old bot.py not found, skipping backup")
        return None


def move_old_bot():
    """Переместить старый bot.py"""
    old_bot = "/workspace/telegram_bot/bot.py"
    if os.path.exists(old_bot):
        new_name = "/workspace/telegram_bot/bot_old.py"
        logger.info(f"Moving {old_bot} to {new_name}")
        shutil.move(old_bot, new_name)


def update_dockerfile():
    """Обновить Dockerfile для запуска нового main.py"""
    dockerfile = "/workspace/telegram_bot/Dockerfile"
    
    if os.path.exists(dockerfile):
        logger.info("Updating Dockerfile")
        
        with open(dockerfile, 'r') as f:
            content = f.read()
        
        # Заменяем bot.py на main.py
        content = content.replace('CMD ["python", "bot.py"]', 'CMD ["python", "main.py"]')
        content = content.replace('CMD ["python3", "bot.py"]', 'CMD ["python3", "main.py"]')
        
        with open(dockerfile, 'w') as f:
            f.write(content)


def create_env_template():
    """Создать шаблон .env файла"""
    env_template = """# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here

# Admin users (comma separated Telegram IDs)
ADMIN_USERS=

# API Configuration  
APP_HOST=http://app:8000
BOT_TIMEOUT=60

# Logging
BOT_LOG_LEVEL=INFO
LOG_USER_MESSAGES=false

# OpenAI (inherited from main app)
# OPENAI_API_KEY=
# OPENAI_MODEL=gpt-4.1-mini
"""
    
    env_file = "/workspace/telegram_bot/.env.template"
    logger.info(f"Creating {env_file}")
    
    with open(env_file, 'w') as f:
        f.write(env_template)


def create_readme():
    """Создать README для новой архитектуры"""
    readme = """# Telegram Bot - Mark v3.0

## 🚀 Новая модульная архитектура

### Структура проекта:
```
telegram_bot/
├── main.py              # Главный файл (100 строк)
├── config.py            # Конфигурация
├── handlers/            # Обработчики команд
├── services/            # Сервисы интеграции
├── middleware/          # Rate limiting, auth, logging
├── keyboards/           # Клавиатуры
└── utils/              # Утилиты
```

### Основные улучшения:

1. **Модульность** - каждый компонент в отдельном файле
2. **Интеграция с Фазами 1-2** - использует enhanced_chat и продвинутую память
3. **Упрощенный UI** - только необходимые команды
4. **Rate limiting** - защита от спама
5. **Улучшенная обработка ошибок**

### Запуск:

```bash
# Из директории langchain_api
docker compose up bot
```

### Конфигурация:

1. Скопируйте `.env.template` в `.env`
2. Добавьте BOT_TOKEN
3. Настройте другие параметры по необходимости

### Команды:

- `/start` - начать работу
- `/help` - справка
- `/chat` - новый диалог
- `/memory` - управление памятью
- `/learn` - запуск обучения
"""
    
    readme_file = "/workspace/telegram_bot/README.md"
    logger.info(f"Creating {readme_file}")
    
    with open(readme_file, 'w') as f:
        f.write(readme)


def main():
    """Главная функция миграции"""
    logger.info("🚀 Starting Telegram bot migration...")
    
    # 1. Создаем бэкап
    backup_dir = backup_old_bot()
    
    # 2. Перемещаем старый bot.py
    move_old_bot()
    
    # 3. Обновляем Dockerfile
    update_dockerfile()
    
    # 4. Создаем шаблоны
    create_env_template()
    create_readme()
    
    logger.info("✅ Migration completed!")
    
    if backup_dir:
        logger.info(f"📦 Backup saved to: {backup_dir}")
    
    logger.info("\n📋 Next steps:")
    logger.info("1. Copy .env.template to .env and configure")
    logger.info("2. Test the new bot: docker compose up bot")
    logger.info("3. If everything works, remove bot_old.py")


if __name__ == "__main__":
    main()