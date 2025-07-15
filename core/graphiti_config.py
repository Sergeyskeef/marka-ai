#!/usr/bin/env python3
"""
GraphitiMemory Configuration and Feature Flags
Настройки для интеграции GraphitiMemory в проект Марк v2
"""
import os
from enum import Enum
from typing import Any


class GraphitiMode(Enum):
    """Режимы работы GraphitiMemory"""
    DISABLED = "disabled"  # Полностью отключено
    SHADOW = "shadow"      # Включено в фоновом режиме (регистрация без активации)
    ACTIVE = "active"      # Активный режим
HYBRID = "hybrid"      # Гибридный режим

class GraphitiConfig:
    """Конфигурация GraphitiMemory для проекта"""

    def __init__(self):
        # Основные настройки
        self.mode = GraphitiMode(os.getenv('GRAPHITI_MODE', 'shadow'))
        self.enabled = self.mode != GraphitiMode.DISABLED

        # Настройки подключения
        self.base_url = os.getenv('GRAPHITI_BASE_URL', 'http://graphiti:7878')
        self.neo4j_uri = os.getenv('GRAPHITI_NEO4J_URI', 'bolt://graphiti-neo4j:7687')
        self.neo4j_username = os.getenv('GRAPHITI_NEO4J_USERNAME', 'neo4j')
        self.neo4j_password = os.getenv('GRAPHITI_NEO4J_PASSWORD', 'password')

        # Настройки таймаутов
        self.timeout = int(os.getenv('GRAPHITI_TIMEOUT', '10'))
        self.connection_timeout = int(os.getenv('GRAPHITI_CONNECTION_TIMEOUT', '30'))

        # Настройки производительности
        self.max_retries = int(os.getenv('GRAPHITI_MAX_RETRIES', '3'))
        self.retry_delay = float(os.getenv('GRAPHITI_RETRY_DELAY', '1.0'))

        # Настройки логирования
        self.log_level = os.getenv('GRAPHITI_LOG_LEVEL', 'INFO')
        self.log_requests = os.getenv('GRAPHITI_LOG_REQUESTS', 'false').lower() == 'true'

        # Настройки для Q1 миграции


        # Настройки валидации
        self.validation_enabled = os.getenv('GRAPHITI_VALIDATION_ENABLED', 'true').lower() == 'true'
        self.health_check_interval = int(os.getenv('GRAPHITI_HEALTH_CHECK_INTERVAL', '30'))

        # Настройки для бенчмарков
        self.benchmark_enabled = os.getenv('GRAPHITI_BENCHMARK_ENABLED', 'false').lower() == 'true'

    def is_shadow_mode(self) -> bool:
        """Проверка режима shadow (регистрация без активации)"""
        return self.mode == GraphitiMode.SHADOW

    def is_active_mode(self) -> bool:
        """Проверка активного режима"""
        return self.mode == GraphitiMode.ACTIVE

    def is_hybrid_mode(self) -> bool:
        """Проверка гибридного режима"""
        return self.mode == GraphitiMode.HYBRID

    def should_use_for_queries(self) -> bool:
        """Следует ли использовать GraphitiMemory для запросов"""
        return self.mode in [GraphitiMode.ACTIVE, GraphitiMode.HYBRID]

    def should_use_for_storage(self) -> bool:
        """Следует ли использовать GraphitiMemory для хранения"""
        return self.mode in [GraphitiMode.ACTIVE, GraphitiMode.HYBRID]

    def get_connection_config(self) -> dict[str, Any]:
        """Получить настройки подключения"""
        return {
            'base_url': self.base_url,
            'neo4j_uri': self.neo4j_uri,
            'neo4j_username': self.neo4j_username,
            'neo4j_password': self.neo4j_password,
            'timeout': self.timeout,
            'connection_timeout': self.connection_timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
        }

    def get_feature_flags(self) -> dict[str, Any]:
        """Получить все feature flags для GraphitiMemory"""
        return {
            'GRAPHITI_MODE': self.mode.value,
            'GRAPHITI_ENABLED': self.enabled,
            'GRAPHITI_SHADOW_MODE': self.is_shadow_mode(),
            'GRAPHITI_ACTIVE_MODE': self.is_active_mode(),
            'GRAPHITI_HYBRID_MODE': self.is_hybrid_mode(),

            'GRAPHITI_VALIDATION_ENABLED': self.validation_enabled,
            'GRAPHITI_BENCHMARK_ENABLED': self.benchmark_enabled,
            'GRAPHITI_LOG_REQUESTS': self.log_requests,
        }

    def validate_config(self) -> dict[str, Any]:
        """Валидация конфигурации"""
        issues = []

        if self.enabled and not self.base_url:
            issues.append("GRAPHITI_BASE_URL is required when GraphitiMemory is enabled")

        if self.enabled and not self.neo4j_uri:
            issues.append("GRAPHITI_NEO4J_URI is required when GraphitiMemory is enabled")

        if self.timeout <= 0:
            issues.append("GRAPHITI_TIMEOUT must be positive")

        if self.max_retries < 0:
            issues.append("GRAPHITI_MAX_RETRIES must be non-negative")

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'config_summary': {
                'mode': self.mode.value,
                'enabled': self.enabled,
                'base_url': self.base_url,

                'validation_enabled': self.validation_enabled,
            }
        }

    def __str__(self) -> str:
        """Строковое представление конфигурации"""
        return f"GraphitiConfig(mode={self.mode.value}, enabled={self.enabled}, url={self.base_url})"

    def __repr__(self) -> str:
        """Подробное представление конфигурации"""
        return (
            f"GraphitiConfig("
            f"mode={self.mode.value}, "
            f"enabled={self.enabled}, "
            f"base_url={self.base_url}, "

            f"validation_enabled={self.validation_enabled}"
            f")"
        )

# Глобальный экземпляр конфигурации
graphiti_config = GraphitiConfig()

# Функции для удобного доступа
def get_graphiti_config() -> GraphitiConfig:
    """Получить конфигурацию GraphitiMemory"""
    return graphiti_config

def is_graphiti_enabled() -> bool:
    """Проверить, включен ли GraphitiMemory"""
    return graphiti_config.enabled

def is_graphiti_shadow_mode() -> bool:
    """Проверить, в shadow режиме ли GraphitiMemory"""
    return graphiti_config.is_shadow_mode()

def get_graphiti_feature_flags() -> dict[str, Any]:
    """Получить все feature flags GraphitiMemory"""
    return graphiti_config.get_feature_flags()

def validate_graphiti_config() -> dict[str, Any]:
    """Валидировать конфигурацию GraphitiMemory"""
    return graphiti_config.validate_config()

# Константы для использования в проекте
GRAPHITI_DEFAULT_TIMEOUT = 10
GRAPHITI_DEFAULT_MAX_RETRIES = 3
GRAPHITI_DEFAULT_RETRY_DELAY = 1.0

# Метаданные для мониторинга
GRAPHITI_METRICS_ENABLED = os.getenv('GRAPHITI_METRICS_ENABLED', 'true').lower() == 'true'
GRAPHITI_HEALTH_CHECK_ENABLED = os.getenv('GRAPHITI_HEALTH_CHECK_ENABLED', 'true').lower() == 'true'

if __name__ == "__main__":
    # Для тестирования конфигурации
    config = get_graphiti_config()
    print("=== GraphitiMemory Configuration ===")
    print(config)
    print(f"\nFeature Flags: {get_graphiti_feature_flags()}")

    validation = validate_graphiti_config()
    print(f"\nValidation: {validation}")

    if not validation['valid']:
        print(f"Issues: {validation['issues']}")
    else:
        print("✅ Configuration is valid")
