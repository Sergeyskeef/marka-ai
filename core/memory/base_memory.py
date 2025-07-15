from abc import ABC, abstractmethod
from typing import Any


class BaseMemory(ABC):
    """Базовый класс для всех типов памяти."""

    @abstractmethod
    def add(self, key: str, value: Any) -> None:
        """Добавить значение в память."""
        pass

    @abstractmethod
    def get(self, key: str) -> Any | None:
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
    def get_all(self) -> dict[str, Any]:
        """Получить все значения из памяти."""
        pass
