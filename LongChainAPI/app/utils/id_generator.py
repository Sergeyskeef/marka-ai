"""
Унифицированный генератор ID для всех систем
"""

import uuid
from enum import Enum
from typing import Optional


class IDType(Enum):
    """Типы ID"""
    FACT = "fact"
    EPISODE = "episode"
    SKILL = "skill"
    DIALOG = "dialog"
    USER = "user"


class IDGenerator:
    """
    Генератор унифицированных ID
    Формат: {type}-{uuid}
    """
    
    @staticmethod
    def generate(id_type: IDType, existing_id: Optional[str] = None) -> str:
        """
        Генерирует новый ID или нормализует существующий
        
        Args:
            id_type: Тип сущности
            existing_id: Существующий ID для нормализации
            
        Returns:
            Унифицированный ID
        """
        if existing_id:
            # Если ID уже в правильном формате, возвращаем его
            if existing_id.startswith(f"{id_type.value}-"):
                return existing_id
            
            # Пытаемся извлечь UUID из старого формата
            parts = existing_id.split("-")
            if len(parts) >= 5:  # UUID format
                uuid_part = "-".join(parts[-5:])
                return f"{id_type.value}-{uuid_part}"
        
        # Генерируем новый ID
        return f"{id_type.value}-{uuid.uuid4()}"
    
    @staticmethod
    def extract_type(id_str: str) -> Optional[IDType]:
        """
        Извлекает тип из ID
        
        Args:
            id_str: ID строка
            
        Returns:
            Тип ID или None
        """
        for id_type in IDType:
            if id_str.startswith(f"{id_type.value}-"):
                return id_type
        return None
    
    @staticmethod
    def extract_uuid(id_str: str) -> Optional[str]:
        """
        Извлекает UUID часть из ID
        
        Args:
            id_str: ID строка
            
        Returns:
            UUID или None
        """
        parts = id_str.split("-", 1)
        if len(parts) == 2:
            return parts[1]
        return None
    
    @staticmethod
    def validate(id_str: str) -> bool:
        """
        Проверяет валидность ID
        
        Args:
            id_str: ID строка
            
        Returns:
            True если ID валиден
        """
        if not id_str:
            return False
        
        # Проверяем формат
        parts = id_str.split("-", 1)
        if len(parts) != 2:
            return False
        
        # Проверяем тип
        type_part = parts[0]
        if type_part not in [t.value for t in IDType]:
            return False
        
        # Проверяем UUID
        uuid_part = parts[1]
        try:
            uuid.UUID(uuid_part)
            return True
        except ValueError:
            return False


# Глобальный экземпляр
id_generator = IDGenerator()