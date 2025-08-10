"""
Единая конфигурация проекта
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Основные настройки
    APP_NAME: str = "Mark AI Assistant"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-5-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: Optional[int] = None
    
    # Memory System
    USE_DIRECT_NEO4J: bool = True
    SYNC_TO_GRAPHITI: bool = False
    
    # Neo4j
    NEO4J_URI: str = "bolt://graphiti-neo4j:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    
    # Graphiti
    GRAPHITI_URL: str = "http://graphiti:8001"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379"
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    
    # Learning System
    REAP_CYCLE_AUTO_RUN: bool = False
    REAP_CYCLE_INTERVAL: int = 300  # seconds
    
    # Vector Search
    VECTOR_DIMENSIONS: int = 1536
    VECTOR_SIMILARITY_THRESHOLD: float = 0.7
    
    # Archival
    ARCHIVE_DAYS_THRESHOLD: int = 90
    
    # Performance
    MAX_CONCURRENT_TOOLS: int = 5
    TOOL_TIMEOUT: int = 30  # seconds
    
    # Prompt Management System
    PROMPTS_STORAGE_PATH: str = "/workspace/data/prompts"
    PROMPTS_CACHE_TTL: int = 3600  # 1 hour
    PROMPTS_MAX_CONTEXT_TOKENS: int = 8192
    PROMPTS_EVOLUTION_ENABLED: bool = True
    PROMPTS_EVOLUTION_CHECK_INTERVAL: int = 60  # seconds
    PROMPTS_ROUTER_ALPHA: float = 0.25  # exploration parameter
    PROMPTS_DEFAULT_ENVIRONMENT: str = "development"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Глобальный экземпляр настроек
settings = Settings()


# Вспомогательные функции
def get_openai_config() -> dict:
    """Получить конфигурацию для OpenAI"""
    return {
        "api_key": settings.OPENAI_API_KEY,
        "model": settings.OPENAI_MODEL,
        "temperature": settings.OPENAI_TEMPERATURE,
        "max_tokens": settings.OPENAI_MAX_TOKENS
    }


def get_memory_config() -> dict:
    """Получить конфигурацию системы памяти"""
    return {
        "use_direct_neo4j": settings.USE_DIRECT_NEO4J,
        "sync_to_graphiti": settings.SYNC_TO_GRAPHITI,
        "neo4j_uri": settings.NEO4J_URI,
        "graphiti_url": settings.GRAPHITI_URL
    }


def get_learning_config() -> dict:
    """Получить конфигурацию системы обучения"""
    return {
        "auto_run": settings.REAP_CYCLE_AUTO_RUN,
        "interval": settings.REAP_CYCLE_INTERVAL,
        "archive_days": settings.ARCHIVE_DAYS_THRESHOLD
    }