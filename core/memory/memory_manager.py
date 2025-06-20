"""
Модуль для управления памятью системы.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import os

from .base_memory import BaseMemory
from .enhanced_memory import EnhancedMemory
from .system_memory import SystemMemory

class MemoryManager:
    """
    Класс для управления памятью системы.
    
    Отвечает за:
    - Управление различными типами памяти
    - Сохранение и извлечение воспоминаний
    - Интеграцию с внешними системами хранения
    """
    
    def __init__(self, weaviate_client=None):
        """
        Инициализация менеджера памяти.
        
        Args:
            weaviate_client: Клиент Weaviate для интеграции с векторной БД
        """
        self.memory_registry: Dict[str, Any] = {
            'Experience': ExperienceMemory(),
            'Task': TaskMemory(),
            'Context': ContextMemory(),
            'Enhanced': EnhancedMemory(),  # Добавляем расширенную память
            'System': SystemMemory(weaviate_client)  # Добавляем системную память
        }
        
    def get_memory(self, memory_type: str) -> Any:
        """
        Получение определенного типа памяти.
        
        Args:
            memory_type: Тип памяти
            
        Returns:
            Экземпляр памяти указанного типа
        """
        return self.memory_registry.get(memory_type)
        
    def save_memory(self, memory_type: str, data: Dict[str, Any]) -> None:
        """
        Сохранение данных в память.
        
        Args:
            memory_type: Тип памяти
            data: Данные для сохранения
        """
        if memory_type in self.memory_registry:
            self.memory_registry[memory_type].insert(data)
            
    def retrieve_memory(self, memory_type: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Извлечение данных из памяти.
        
        Args:
            memory_type: Тип памяти
            query: Параметры поиска
            
        Returns:
            Список найденных воспоминаний
        """
        if memory_type in self.memory_registry:
            return self.memory_registry[memory_type].search(query)
        return []
    
    def get_system_memory(self) -> SystemMemory:
        """
        Получение системной памяти.
        
        Returns:
            Экземпляр SystemMemory
        """
        return self.memory_registry.get('System')
    
    def load_core_documents(self, docs_path: str) -> None:
        """
        Загрузка основных документов в системную память.
        
        Args:
            docs_path: Путь к директории с документами
        """
        system_memory = self.get_system_memory()
        if system_memory:
            system_memory.load_core_documents(docs_path)
            
    def get_status(self) -> Dict[str, Any]:
        """
        Получение статуса менеджера памяти.
        
        Returns:
            Словарь со статусом памяти
        """
        status = {
            'total_memories': 0,
            'memory_types': {},
            'system_memory_available': False,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Подсчитываем общее количество воспоминаний
        for memory_type, memory in self.memory_registry.items():
            if hasattr(memory, 'memories'):
                count = len(memory.memories)
            elif hasattr(memory, '_local_memory'):
                count = len(memory._local_memory)
            else:
                count = 0
                
            status['memory_types'][memory_type] = {
                'count': count,
                'available': True
            }
            status['total_memories'] += count
            
        # Проверяем доступность системной памяти
        system_memory = self.get_system_memory()
        status['system_memory_available'] = system_memory is not None
        
        return status

class BaseMemory:
    """Базовый класс для всех типов памяти."""
    
    def __init__(self):
        self.memories: List[Dict[str, Any]] = []
        
    def insert(self, data: Dict[str, Any]) -> None:
        """Вставка данных в память."""
        data['timestamp'] = datetime.utcnow().isoformat()
        self.memories.append(data)
        
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Поиск данных в памяти."""
        # Базовая реализация поиска
        return [m for m in self.memories if all(m.get(k) == v for k, v in query.items())]

class ExperienceMemory(BaseMemory):
    """Память для хранения опыта."""
    pass

class TaskMemory(BaseMemory):
    """Память для хранения задач."""
    pass

class ContextMemory(BaseMemory):
    """Память для хранения контекста."""
    pass 