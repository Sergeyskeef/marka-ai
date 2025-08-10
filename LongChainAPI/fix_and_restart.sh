#!/bin/bash

echo "=== Исправление проблемы с ExternalIntegrationService ==="

# Переходим в директорию проекта пользователя
cd /home/sergey/marka/langchain_api

# Создаем необходимую структуру директорий если их нет
mkdir -p langchain_api/services

# Создаем файл-заглушку для ExternalIntegrationService
cat > langchain_api/services/external_integration_service.py << 'EOF'
"""
External Integration Service - заглушка для совместимости
"""
import logging

logger = logging.getLogger(__name__)


class ExternalIntegrationService:
    """
    Сервис для интеграции с внешними системами
    """
    
    def __init__(self):
        logger.info("ExternalIntegrationService инициализирован (заглушка)")
    
    async def initialize(self):
        """Инициализация сервиса"""
        logger.info("ExternalIntegrationService.initialize() вызван")
        pass
    
    async def shutdown(self):
        """Завершение работы сервиса"""
        logger.info("ExternalIntegrationService.shutdown() вызван")
        pass
EOF

# Создаем __init__.py файлы если их нет
touch langchain_api/__init__.py
touch langchain_api/services/__init__.py

echo "✅ Файл-заглушка создан"

# Перезапускаем контейнер
echo "=== Перезапуск Docker контейнера ==="
docker compose restart app

echo "✅ Контейнер перезапущен"
echo ""
echo "Проверьте логи командой:"
echo "docker compose logs app --tail=50"