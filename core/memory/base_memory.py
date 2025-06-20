from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseMemory(ABC):
    """Базовый класс для всех типов памяти."""
    
    @abstractmethod
    def add(self, key: str, value: Any) -> None:
        """Добавить значение в память."""
        pass
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из памяти."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        """Удалить значение из памяти."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Очистить память."""
        pass
    
    @abstractmethod
    def get_all(self) -> Dict[str, Any]:
        """Получить все значения из памяти."""
        pass 