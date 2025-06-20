"""
Конфигурация повторных попыток для системы действий.
"""

from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
import time

class RetryStrategy(Enum):
    """Стратегии повторных попыток."""
    FIXED = "fixed"  # Фиксированный интервал
    EXPONENTIAL = "exponential"  # Экспоненциальное увеличение интервала
    LINEAR = "linear"  # Линейное увеличение интервала

@dataclass
class RetryConfig:
    """Конфигурация повторных попыток."""
    max_retries: int = 3  # Максимальное количество попыток
    initial_delay: float = 1.0  # Начальная задержка в секундах
    max_delay: float = 30.0  # Максимальная задержка в секундах
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL  # Стратегия повторных попыток
    backoff_factor: float = 2.0  # Множитель для экспоненциальной стратегии
    
    def get_delay(self, attempt: int) -> float:
        """Получить задержку для конкретной попытки.
        
        Args:
            attempt: Номер попытки (начиная с 1)
            
        Returns:
            Задержка в секундах
        """
        if attempt <= 0:
            return 0.0
            
        if self.strategy == RetryStrategy.FIXED:
            delay = self.initial_delay
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay * attempt
        else:  # EXPONENTIAL
            delay = self.initial_delay * (self.backoff_factor ** (attempt - 1))
            
        return min(delay, self.max_delay)
        
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать конфигурацию в словарь.
        
        Returns:
            Словарь с конфигурацией
        """
        return {
            "max_retries": self.max_retries,
            "initial_delay": self.initial_delay,
            "max_delay": self.max_delay,
            "strategy": self.strategy.value,
            "backoff_factor": self.backoff_factor
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryConfig':
        """Создать конфигурацию из словаря.
        
        Args:
            data: Словарь с конфигурацией
            
        Returns:
            Экземпляр конфигурации
        """
        return cls(
            max_retries=data.get("max_retries", 3),
            initial_delay=data.get("initial_delay", 1.0),
            max_delay=data.get("max_delay", 30.0),
            strategy=RetryStrategy(data.get("strategy", RetryStrategy.EXPONENTIAL.value)),
            backoff_factor=data.get("backoff_factor", 2.0)
        ) 