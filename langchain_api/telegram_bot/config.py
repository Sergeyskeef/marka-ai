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
    REQUEST_TIMEOUT: int = int(os.getenv("BOT_TIMEOUT", "240"))
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
    
    # Система внутреннего диалога
    USE_INTERNAL_DIALOGUE: bool = os.getenv("USE_INTERNAL_DIALOGUE", "true").lower() == "true"
    INTERNAL_DIALOGUE_LIFETIME: int = int(os.getenv("INTERNAL_DIALOGUE_LIFETIME", "30"))  # секунды
    INTERNAL_DIALOGUE_MAX_STEPS: int = int(os.getenv("INTERNAL_DIALOGUE_MAX_STEPS", "10"))
    INTERNAL_DIALOGUE_AUTO_SOLVE_THRESHOLD: float = float(os.getenv("INTERNAL_DIALOGUE_AUTO_SOLVE_THRESHOLD", "0.7"))
    
    # Стриминговый чат (SSE)
    # По умолчанию ОТКЛЮЧЁН. Включать только при готовности инфраструктуры.
    USE_STREAMED_CHAT: bool = os.getenv("USE_STREAMED_CHAT", "false").lower() == "true"
    STREAM_EDIT_INTERVAL_MS: int = int(os.getenv("STREAM_EDIT_INTERVAL_MS", "400"))
    STREAM_MAX_MESSAGE_CHARS: int = int(os.getenv("STREAM_MAX_MESSAGE_CHARS", "3500"))
    
    # Режим разработки
    DEV_MODE: bool = os.getenv("BOT_DEV_MODE", "false").lower() == "true"
    
    # Логирование
    LOG_LEVEL: str = os.getenv("BOT_LOG_LEVEL", "INFO")
    LOG_USER_MESSAGES: bool = os.getenv("LOG_USER_MESSAGES", "false").lower() == "true"
    
    # Rate limits / safety
    OPENAI_TPM_LIMIT: int = int(os.getenv("OPENAI_TPM_LIMIT", "180000"))  # tokens per minute budget
    MAX_USER_TOKENS: int = int(os.getenv("MAX_USER_TOKENS", "2048"))     # cap user message tokens
    MAX_GEN_TOKENS: int = int(os.getenv("MAX_GEN_TOKENS", "1024"))       # optimistic budget for output tokens
    RATE_LIMIT_MAX_RETRIES: int = int(os.getenv("RATE_LIMIT_MAX_RETRIES", "3"))
    RATE_LIMIT_BACKOFF_BASE: float = float(os.getenv("RATE_LIMIT_BACKOFF_BASE", "1.2"))
    
    @classmethod
    def validate(cls) -> None:
        """Проверка конфигурации"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не установлен!")
        
        if not cls.APP_HOST:
            raise ValueError("APP_HOST не установлен!")
        
        # Проверяем настройки внутреннего диалога
        if cls.USE_INTERNAL_DIALOGUE:
            if cls.INTERNAL_DIALOGUE_LIFETIME < 5:
                raise ValueError("INTERNAL_DIALOGUE_LIFETIME должен быть не менее 5 секунд!")
            
            if cls.INTERNAL_DIALOGUE_MAX_STEPS < 1:
                raise ValueError("INTERNAL_DIALOGUE_MAX_STEPS должен быть не менее 1!")
            
            if not (0.0 <= cls.INTERNAL_DIALOGUE_AUTO_SOLVE_THRESHOLD <= 1.0):
                raise ValueError("INTERNAL_DIALOGUE_AUTO_SOLVE_THRESHOLD должен быть от 0.0 до 1.0!")


# Глобальный экземпляр конфигурации
bot_config = BotConfig()