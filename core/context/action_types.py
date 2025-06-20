"""
Типы и интерфейсы для системы действий.
"""

from typing import Protocol, Dict, Any, Optional
from enum import Enum
from datetime import datetime

class ActionPriority(Enum):
    """Приоритеты действий."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    def get_weight(self) -> float:
        """Получить числовой вес приоритета."""
        weights = {
            ActionPriority.LOW: 1.0,
            ActionPriority.NORMAL: 2.0,
            ActionPriority.HIGH: 3.0
        }
        return weights[self]

class ActionStatus(Enum):
    """Статусы действий."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"

class ActionType(Enum):
    """Типы действий."""
    SYSTEM = "system"
    USER = "user"
    LEARNING = "learning"
    MEMORY = "memory"
    REFLECTION = "reflection"

    def get_importance(self) -> float:
        """Получить числовое значение важности типа действия."""
        importance = {
            ActionType.SYSTEM: 1.0,
            ActionType.USER: 2.0,
            ActionType.LEARNING: 1.5,
            ActionType.MEMORY: 1.2,
            ActionType.REFLECTION: 1.8
        }
        return importance[self]

class RetryStrategy(Enum):
    """Стратегии повторных попыток."""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"

class RetryConfig:
    """Конфигурация повторных попыток."""
    
    def __init__(
        self,
        max_retries: int = 3,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        base_delay: float = 1.0
    ):
        self.max_retries = max_retries
        self.strategy = strategy
        self.base_delay = base_delay
    
    def get_delay(self, retry_count: int) -> float:
        """Получить задержку перед следующей попыткой."""
        if self.strategy == RetryStrategy.FIXED:
            return self.base_delay
        elif self.strategy == RetryStrategy.LINEAR:
            return self.base_delay * (retry_count + 1)
        else:  # EXPONENTIAL
            return self.base_delay * (2 ** retry_count)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать конфигурацию в словарь."""
        return {
            "max_retries": self.max_retries,
            "strategy": self.strategy.value,
            "base_delay": self.base_delay
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryConfig':
        """Создать конфигурацию из словаря."""
        return cls(
            max_retries=data.get("max_retries", 3),
            strategy=RetryStrategy(data.get("strategy", RetryStrategy.EXPONENTIAL.value)),
            base_delay=data.get("base_delay", 1.0)
        )

class Action(Protocol):
    """Интерфейс действия."""
    id: str
    type: str
    status: ActionStatus
    priority: ActionPriority
    dependencies: list[str]
    metadata: Dict[str, Any]
    created_at: datetime
    retry_count: int
    wait_time: float  # Время ожидания в очереди в секундах

    async def execute(self) -> Dict[str, Any]:
        """Выполнить действие."""
        ...

    async def validate(self) -> bool:
        """Проверить валидность действия."""
        ...

    async def rollback(self) -> None:
        """Откатить действие."""
        ...

    def calculate_dynamic_priority(self) -> float:
        """
        Рассчитать динамический приоритет действия.
        
        Учитывает:
        - Базовый приоритет
        - Время ожидания в очереди
        - Количество попыток выполнения
        - Тип действия
        
        Returns:
            float: Динамический приоритет (чем больше, тем выше приоритет)
        """
        ...

class ActionSystem(Protocol):
    """Интерфейс системы действий."""
    async def add_action(self, action: Action) -> None:
        """Добавить действие в систему."""
        ...

    async def execute_next_action(self) -> Optional[Dict[str, Any]]:
        """Выполнить следующее действие."""
        ...

    async def cancel_action(self, action_id: str) -> None:
        """Отменить действие."""
        ...

    async def rollback_action(self, action_id: str) -> None:
        """Откатить действие."""
        ...

    def get_queue_status(self) -> Dict[str, Any]:
        """Получить статус очереди действий."""
        ... 