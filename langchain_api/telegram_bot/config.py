"""
Конфигурация Telegram бота
"""

import os
import sys
from typing import Optional, List

# Добавляем путь к корню проекта для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.config import settings as app_settings
except ImportError:
    # Если не можем импортировать, используем значения по умолчанию
    class app_settings:
        USE_DIRECT_NEO4J = True


class BotConfig:
    """Настройки Telegram бота"""
    
    # Telegram
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # API endpoints
    APP_HOST: str = os.getenv("APP_HOST", "http://app:8000")
    
    # Timeouts
    REQUEST_TIMEOUT: int = int(os.getenv("BOT_TIMEOUT", "60"))
    POLL_TIMEOUT: int = 30
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 30
    RATE_LIMIT_WINDOW: int = 60  # seconds
    
    # UI настройки
    MAX_MESSAGE_LENGTH: int = 4096
    MAX_BUTTONS_PER_ROW: int = 3
    DEFAULT_PARSE_MODE: str = "Markdown"
    
    # Команды (упрощенный набор)
    AVAILABLE_COMMANDS: List[str] = [
        "/start",
        "/help", 
        "/chat",
        "/memory",
        "/learn",
        "/settings",
        "/cancel"
    ]
    
    # Админские команды
    ADMIN_COMMANDS: List[str] = [
        "/stats",
        "/sync",
        "/debug"
    ]
    
    # Пользователи-админы (Telegram ID)
    ADMIN_USERS: List[int] = [
        int(uid) for uid in os.getenv("ADMIN_USERS", "").split(",") if uid
    ]
    
    # Интеграция с основным приложением
    USE_ENHANCED_CHAT: bool = True
    USE_ADVANCED_MEMORY: bool = app_settings.USE_DIRECT_NEO4J if hasattr(app_settings, 'USE_DIRECT_NEO4J') else True
    USE_LEARNING_SYSTEM: bool = True
    
    # Режим разработки
    DEV_MODE: bool = os.getenv("BOT_DEV_MODE", "true").lower() == "true"
    
    # Логирование
    LOG_LEVEL: str = os.getenv("BOT_LOG_LEVEL", "INFO")
    LOG_USER_MESSAGES: bool = os.getenv("LOG_USER_MESSAGES", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> None:
        """Проверка конфигурации"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не установлен!")
        
        if not cls.APP_HOST:
            raise ValueError("APP_HOST не установлен!")


# Глобальный экземпляр конфигурации
bot_config = BotConfig()