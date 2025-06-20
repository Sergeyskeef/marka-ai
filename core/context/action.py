"""
Модуль для базового класса Action и его реализации.
"""

from typing import Dict, List, Optional, Any, Type
from datetime import datetime
import uuid
from abc import ABC, abstractmethod
from ..memory.memory_manager import MemoryManager
from .action_types import ActionPriority, ActionStatus, ActionType
from .retry_config import RetryConfig, RetryStrategy

class Action(ABC):
    """
    Базовый абстрактный класс для всех действий в системе.
    
    Отвечает за:
    - Определение структуры действия
    - Выполнение действия
    - Валидацию параметров
    - Интеграцию с системой памяти
    - Отслеживание состояния
    """
    
    def __init__(self, 
                 action_type: str,
                 memory_manager: MemoryManager,
                 session_id: str,
                 priority: ActionPriority = ActionPriority.NORMAL,
                 details: Optional[Dict[str, Any]] = None,
                 retry_config: Optional[RetryConfig] = None):
        """
        Инициализация действия.
        
        Args:
            action_type: Тип действия
            memory_manager: Менеджер памяти для интеграции
            session_id: ID сессии
            priority: Приоритет действия
            details: Дополнительные детали действия
            retry_config: Конфигурация повторных попыток
        """
        self.id = str(uuid.uuid4())
        self.type = action_type
        self.memory_manager = memory_manager
        self.session_id = session_id
        self.priority = priority
        self.details = details or {}
        self.created_at = datetime.utcnow()
        self.completed_at = None
        self.timestamp = self.created_at.isoformat() + 'Z'
        self.status = ActionStatus.CREATED.value
        self.result = None
        self.error = None
        self.retry_count = 0
        self.retry_config = retry_config or RetryConfig()
        self.last_retry_timestamp = None
        self.wait_time = 0.0  # Время ожидания в очереди в секундах
        
    def calculate_dynamic_priority(self) -> float:
        """
        Рассчитать динамический приоритет действия.
        
        Учитывает:
        - Базовый приоритет (вес от 1 до 4)
        - Время ожидания в очереди (коэффициент от 1.0 до 2.0)
        - Количество попыток выполнения (коэффициент от 1.0 до 1.5)
        - Тип действия (коэффициент от 0.6 до 1.5)
        
        Returns:
            float: Динамический приоритет (чем больше, тем выше приоритет)
        """
        # Базовый вес приоритета
        base_weight = ActionPriority.get_weight(self.priority)
        
        # Коэффициент времени ожидания (максимум 2.0 при ожидании более 1 часа)
        wait_factor = min(2.0, 1.0 + (self.wait_time / 3600))
        
        # Коэффициент попыток (максимум 1.5 при 3+ попытках)
        retry_factor = min(1.5, 1.0 + (self.retry_count * 0.2))
        
        # Коэффициент типа действия
        type_factor = ActionType.get_importance(ActionType(self.type))
        
        # Итоговый приоритет
        dynamic_priority = base_weight * wait_factor * retry_factor * type_factor
        
        return dynamic_priority
        
    def update_wait_time(self) -> None:
        """
        Обновить время ожидания в очереди.
        """
        self.wait_time = (datetime.utcnow() - self.created_at).total_seconds()
        
    def __eq__(self, other):
        """
        Сравнение действий.
        
        Args:
            other: Другое действие для сравнения
            
        Returns:
            True, если действия равны
        """
        if not isinstance(other, Action):
            return NotImplemented
        return self.id == other.id
        
    def __hash__(self):
        """
        Хеш действия.
        
        Returns:
            Хеш действия
        """
        return hash(self.id)
        
    @abstractmethod
    async def execute(self) -> Dict[str, Any]:
        """
        Выполнение действия.
        
        Returns:
            Результат выполнения
        """
        pass
        
    @abstractmethod
    def validate(self) -> bool:
        """
        Валидация параметров действия.
        
        Returns:
            True, если параметры валидны
        """
        pass
        
    @abstractmethod
    async def rollback(self) -> bool:
        """
        Откат действия.
        
        Returns:
            True, если откат успешен
        """
        pass
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Преобразование действия в словарь.
        
        Returns:
            Словарь с данными действия
        """
        return {
            'id': self.id,
            'type': self.type,
            'priority': self.priority.value,
            'dynamic_priority': self.calculate_dynamic_priority(),
            'details': self.details,
            'timestamp': self.timestamp,
            'session_id': self.session_id,
            'status': self.status,
            'result': self.result,
            'error': self.error,
            'retry_count': self.retry_count,
            'retry_config': self.retry_config.to_dict(),
            'last_retry_timestamp': self.last_retry_timestamp,
            'wait_time': self.wait_time,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
        
    def save_to_memory(self) -> None:
        """
        Сохранение действия в память.
        """
        self.memory_manager.memory_registry.get('Experience').insert({
            'summary': f"Действие {self.type}: {self.details}",
            'timestamp': self.timestamp,
            'session_id': self.session_id,
            'status': self.status,
            'result': self.result,
            'error': self.error,
            'priority': self.priority.value,
            'dynamic_priority': self.calculate_dynamic_priority(),
            'retry_count': self.retry_count,
            'retry_config': self.retry_config.to_dict(),
            'last_retry_timestamp': self.last_retry_timestamp,
            'wait_time': self.wait_time,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        })
        
    def update_status(self, 
                     status: str, 
                     result: Optional[Dict[str, Any]] = None, 
                     error: Optional[str] = None) -> None:
        """
        Обновление статуса действия.
        
        Args:
            status: Новый статус
            result: Результат выполнения
            error: Ошибка выполнения
        """
        self.status = status
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error
            
        # Устанавливаем время завершения при успешном выполнении или ошибке
        if status in [ActionStatus.COMPLETED.value, ActionStatus.FAILED.value, ActionStatus.CANCELLED.value]:
            self.completed_at = datetime.utcnow()
            
        self.save_to_memory()
        
    def can_retry(self) -> bool:
        """
        Проверка возможности повторного выполнения.
        
        Returns:
            True, если действие можно повторить
        """
        # Проверяем только количество попыток
        return self.retry_count <= self.retry_config.max_retries
        
    def increment_retry_count(self) -> None:
        """
        Увеличение счетчика попыток выполнения.
        """
        self.retry_count += 1
        self.last_retry_timestamp = datetime.utcnow().isoformat() + 'Z'
        
    def get_retry_delay(self) -> float:
        """
        Получить задержку перед следующей попыткой.
        
        Returns:
            Задержка в секундах
        """
        return self.retry_config.get_delay(self.retry_count)
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any], memory_manager: MemoryManager) -> 'Action':
        """
        Создание действия из словаря.
        
        Args:
            data: Словарь с данными действия
            memory_manager: Менеджер памяти
            
        Returns:
            Экземпляр действия
        """
        action = cls(
            action_type=data['type'],
            memory_manager=memory_manager,
            session_id=data['session_id'],
            priority=ActionPriority(data['priority']),
            details=data.get('details'),
            retry_config=RetryConfig.from_dict(data['retry_config'])
        )
        action.id = data['id']
        action.timestamp = data['timestamp']
        action.status = data['status']
        action.result = data.get('result')
        action.error = data.get('error')
        action.retry_count = data['retry_count']
        action.last_retry_timestamp = data.get('last_retry_timestamp')
        action.wait_time = data.get('wait_time', 0.0)
        action.created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        action.completed_at = datetime.fromisoformat(data['completed_at'].replace('Z', '+00:00')) if data.get('completed_at') else None
        return action 