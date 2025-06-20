"""
Обертка для работы с системной памятью.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import os
from pathlib import Path

from .system_memory import SystemMemory

class SystemMemoryWrapper:
    """
    Обертка для удобной работы с системной памятью.
    
    Предоставляет:
    - Упрощенный API для работы с системной памятью
    - Автоматическое управление приоритетами
    - Версионирование данных
    - Интеграцию с LLM
    """
    
    def __init__(self, weaviate_client=None):
        """
        Инициализация обертки.
        
        Args:
            weaviate_client: Клиент Weaviate для интеграции с векторной БД
        """
        self.system_memory = SystemMemory(weaviate_client)
        self.version = "1.0.0"
        
    def insert(self, data: Dict[str, Any]) -> None:
        """
        Вставка данных в системную память.
        
        Args:
            data: Данные для сохранения
        """
        # Добавляем версию
        data['version'] = self.version
        data['inserted_at'] = datetime.utcnow().isoformat()
        
        self.system_memory.insert(data)
    
    def search(self, query: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Поиск данных в системной памяти.
        
        Args:
            query: Параметры поиска
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных записей, отсортированных по приоритету
        """
        return self.system_memory.search(query, limit)
    
    def search_by_type(self, content_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Поиск по типу контента.
        
        Args:
            content_type: Тип контента
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных записей
        """
        return self.system_memory.search_by_type(content_type, limit)
    
    def update(self, query: Dict[str, Any], new_data: Dict[str, Any]) -> bool:
        """
        Обновление данных в системной памяти.
        
        Args:
            query: Параметры поиска для обновления
            new_data: Новые данные
            
        Returns:
            True если обновление прошло успешно
        """
        try:
            # Находим записи для обновления
            existing_records = self.search(query)
            
            if not existing_records:
                return False
            
            # Обновляем каждую найденную запись
            for record in existing_records:
                # Обновляем данные
                record.update(new_data)
                record['updated_at'] = datetime.utcnow().isoformat()
                record['version'] = self.version
                
                # Удаляем старую запись и добавляем обновленную
                self.system_memory._local_memory.remove(record)
                self.system_memory.insert(record)
            
            return True
            
        except Exception as e:
            print(f"Ошибка при обновлении данных: {e}")
            return False
    
    def delete(self, query: Dict[str, Any]) -> bool:
        """
        Удаление данных из системной памяти.
        
        Args:
            query: Параметры поиска для удаления
            
        Returns:
            True если удаление прошло успешно
        """
        try:
            # Находим записи для удаления
            existing_records = self.search(query)
            
            if not existing_records:
                return False
            
            # Удаляем записи (в базовой реализации просто помечаем как удаленные)
            for record in existing_records:
                record['deleted_at'] = datetime.utcnow().isoformat()
                record['is_deleted'] = True
                
                # Удаляем старую запись и добавляем помеченную как удаленную
                self.system_memory._local_memory.remove(record)
                self.system_memory.insert(record)
            
            return True
            
        except Exception as e:
            print(f"Ошибка при удалении данных: {e}")
            return False
    
    def get_identity_context(self) -> Dict[str, Any]:
        """
        Получение контекста идентичности Марка.
        
        Returns:
            Словарь с информацией об идентичности
        """
        return self.system_memory.get_identity_context()
    
    def get_system_capabilities(self) -> Dict[str, Any]:
        """
        Получение информации о возможностях системы.
        
        Returns:
            Словарь с описанием возможностей
        """
        return self.system_memory.get_system_capabilities()
    
    def load_core_documents(self, docs_path: str) -> None:
        """
        Загрузка основных документов в системную память.
        
        Args:
            docs_path: Путь к директории с документами
        """
        self.system_memory.load_core_documents(docs_path)
    
    def get_priority_search_results(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Приоритизированный поиск с учетом весов документов.
        
        Args:
            query: Текст запроса
            limit: Максимальное количество результатов
            
        Returns:
            Список результатов, отсортированных по приоритету
        """
        # Создаем поисковый запрос
        search_query = {
            'content': query
        }
        
        results = self.search(search_query, limit * 2)  # Получаем больше результатов для сортировки
        
        # Фильтруем удаленные записи
        results = [r for r in results if not r.get('is_deleted', False)]
        
        # Сортируем по приоритету
        results.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        return results[:limit]
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Получение статуса системной памяти.
        
        Returns:
            Словарь со статусом системы
        """
        status = {
            'version': self.version,
            'total_records': len(self.system_memory._local_memory),
            'memory_types': {},
            'last_updated': datetime.utcnow().isoformat()
        }
        
        # Подсчитываем записи по типам
        for record in self.system_memory._local_memory:
            record_type = record.get('type', 'unknown')
            if record_type not in status['memory_types']:
                status['memory_types'][record_type] = 0
            status['memory_types'][record_type] += 1
        
        return status 