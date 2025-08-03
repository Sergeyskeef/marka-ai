#!/usr/bin/env python3
"""
Система метрик для Марка
"""

import time
import logging
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# Метрики Prometheus
REQUEST_COUNT = Counter(
    'mark_requests_total',
    'Total number of requests',
    ['endpoint', 'method', 'status']
)

REQUEST_DURATION = Histogram(
    'mark_request_duration_seconds',
    'Request duration in seconds',
    ['endpoint', 'method']
)

CHAT_REQUESTS = Counter(
    'mark_chat_requests_total',
    'Total number of chat requests',
    ['mode', 'status']
)

MEMORY_OPERATIONS = Counter(
    'mark_memory_operations_total',
    'Total number of memory operations',
    ['operation', 'status']
)

TOOL_EXECUTIONS = Counter(
    'mark_tool_executions_total',
    'Total number of tool executions',
    ['tool_name', 'status']
)

BOT_MESSAGES = Counter(
    'mark_bot_messages_total',
    'Total number of bot messages',
    ['command', 'status']
)

ACTIVE_USERS = Gauge(
    'mark_active_users',
    'Number of active users'
)

REFLEXION_ATTEMPTS = Counter(
    'mark_reflexion_attempts_total',
    'Total number of reflexion attempts',
    ['result']  # 'success', 'failure'
)

REFLEXION_SUCCESS_RATE = Gauge(
    'mark_reflexion_success_rate',
    'Reflexion success rate (0.0 to 1.0)'
)

class MetricsManager:
    """Менеджер метрик"""
    
    def __init__(self):
        self.start_time = time.time()
        logger.info("📊 MetricsManager инициализирован")
    
    def record_request(self, endpoint: str, method: str, status: int, duration: float):
        """Запись метрики запроса"""
        REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=status).inc()
        REQUEST_DURATION.labels(endpoint=endpoint, method=method).observe(duration)
    
    def record_chat_request(self, mode: str, status: str):
        """Запись метрики чата"""
        CHAT_REQUESTS.labels(mode=mode, status=status).inc()
    
    def record_memory_operation(self, operation: str, status: str):
        """Запись метрики операции с памятью"""
        MEMORY_OPERATIONS.labels(operation=operation, status=status).inc()
    
    def record_tool_execution(self, tool_name: str, status: str):
        """Запись метрики выполнения инструмента"""
        TOOL_EXECUTIONS.labels(tool_name=tool_name, status=status).inc()
    
    def record_bot_message(self, command: str, status: str):
        """Запись метрики сообщения бота"""
        BOT_MESSAGES.labels(command=command, status=status).inc()
    
    def set_active_users(self, count: int):
        """Установка количества активных пользователей"""
        ACTIVE_USERS.set(count)
    
    def record_reflexion_attempt(self, result: str):
        """Запись метрики попытки рефлексии"""
        REFLEXION_ATTEMPTS.labels(result=result).inc()
        
        # Обновляем success rate
        self._update_reflexion_success_rate()
    
    def _update_reflexion_success_rate(self):
        """Обновление метрики success rate рефлексии"""
        try:
            # Получаем значения счетчиков
            success_count = REFLEXION_ATTEMPTS.labels(result='success')._value._value
            failure_count = REFLEXION_ATTEMPTS.labels(result='failure')._value._value
            
            total = success_count + failure_count
            if total > 0:
                success_rate = success_count / total
                REFLEXION_SUCCESS_RATE.set(success_rate)
            else:
                REFLEXION_SUCCESS_RATE.set(0.0)
        except Exception as e:
            logger.warning(f"Ошибка обновления reflexion success rate: {e}")
            REFLEXION_SUCCESS_RATE.set(0.0)
    
    def get_uptime(self) -> float:
        """Получение времени работы"""
        return time.time() - self.start_time
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Получение сводки метрик"""
        return {
            "uptime_seconds": self.get_uptime(),
            "metrics": {
                "requests": "REQUEST_COUNT",
                "duration": "REQUEST_DURATION", 
                "chat": "CHAT_REQUESTS",
                "memory": "MEMORY_OPERATIONS",
                "tools": "TOOL_EXECUTIONS",
                "bot": "BOT_MESSAGES",
                "users": "ACTIVE_USERS",
                "reflexion_attempts": "REFLEXION_ATTEMPTS",
                "reflexion_success_rate": "REFLEXION_SUCCESS_RATE"
            }
        }
    
    def export_prometheus(self) -> str:
        """Экспорт метрик в формате Prometheus"""
        return generate_latest()

# Глобальный экземпляр менеджера метрик
metrics_manager = MetricsManager() 