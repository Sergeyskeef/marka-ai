"""
HealthService - сервис для мониторинга здоровья системы
"""

import logging
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class HealthService:
    """Сервис для мониторинга здоровья системы"""

    def __init__(self):
        self.start_time = time.time()
        self.services_status = {
            "app": "healthy",
            "memory": "healthy",
            "database": "healthy",
            "external_apis": "healthy"
        }
        logger.info("✅ HealthService инициализирован")

    def get_uptime(self) -> float:
        """Возвращает время работы системы в секундах"""
        return time.time() - self.start_time

    def get_services_status(self) -> dict[str, str]:
        """Возвращает статус всех сервисов"""
        return self.services_status.copy()

    def update_service_status(self, service: str, status: str):
        """Обновляет статус сервиса"""
        self.services_status[service] = status
        logger.info(f"🔄 Статус сервиса {service} обновлен: {status}")

    def get_overall_status(self) -> str:
        """Возвращает общий статус системы"""
        if all(status == "healthy" for status in self.services_status.values()):
            return "healthy"
        elif any(status == "critical" for status in self.services_status.values()):
            return "critical"
        else:
            return "degraded"

    def get_health_info(self) -> dict[str, Any]:
        """Возвращает полную информацию о здоровье системы"""
        return {
            "status": self.get_overall_status(),
            "services": self.get_services_status(),
            "uptime": self.get_uptime(),
            "timestamp": datetime.now().isoformat()
        }
