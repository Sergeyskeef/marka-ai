"""
Модуль для системной памяти.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import os
from pathlib import Path

from .base_memory import BaseMemory

class SystemMemory(BaseMemory):
    """
    Класс для хранения системной информации.
    
    Отвечает за:
    - Хранение системных документов
    - Управление приоритетами поиска
    - Версионирование системной информации
    - Интеграцию с векторной базой данных
    """
    
    def __init__(self, weaviate_client=None):
        """
        Инициализация системной памяти.
        
        Args:
            weaviate_client: Клиент Weaviate для интеграции с векторной БД
        """
        super().__init__()
        self.weaviate_client = weaviate_client
        self.collection_name = "SystemMemory"
        self._local_memory = []  # Локальная память для хранения данных
        self.priority_weights = {
            'core_docs': 1.0,      # Высший приоритет
            'project_map': 0.9,    # Очень высокий
            'schema': 0.8,         # Высокий
            'docs': 0.7,           # Средний-высокий
            'scripts': 0.6,        # Средний
            'config': 0.5,         # Средний-низкий
            'logs': 0.3            # Низкий
        }
        
    def insert(self, data: Dict[str, Any]) -> None:
        """
        Вставка данных в системную память.
        
        Args:
            data: Данные для сохранения
        """
        # Добавляем системные поля
        data['timestamp'] = datetime.utcnow().isoformat()
        data['version'] = data.get('version', '1.0')
        data['priority'] = self._calculate_priority(data)
        
        # Сохраняем в локальную память
        self._local_memory.append(data)
        
        # Сохраняем в Weaviate если доступен
        if self.weaviate_client:
            self._save_to_weaviate(data)
    
    def search(self, query: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Поиск данных в системной памяти с учетом приоритетов.
        
        Args:
            query: Параметры поиска
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных записей, отсортированных по приоритету
        """
        results = []
        
        # Поиск в локальной памяти
        local_results = self._search_local(query)
        results.extend(local_results)
        
        # Поиск в Weaviate если доступен
        if self.weaviate_client:
            weaviate_results = self._search_in_weaviate(query, limit)
            results.extend(weaviate_results)
        
        # Сортировка по приоритету
        results.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        return results[:limit]
    
    def search_by_type(self, content_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Поиск по типу контента.
        
        Args:
            content_type: Тип контента
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных записей
        """
        return self.search({'type': content_type}, limit)
    
    def get_identity_context(self) -> Dict[str, Any]:
        """
        Получение контекста идентичности Марка.
        
        Returns:
            Словарь с информацией об идентичности
        """
        identity_docs = self.search_by_type('core_docs', limit=20)
        
        context = {
            'identity': {},
            'manifesto': {},
            'principles': {},
            'capabilities': {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        for doc in identity_docs:
            filename = doc.get('filename', '').lower()
            content = doc.get('content', '')
            
            # Ищем по ключевым словам в имени файла и содержимом
            if any(keyword in filename for keyword in ['core', 'завет', 'ядро']) or 'Основной завет' in content:
                context['identity']['core'] = content
            elif any(keyword in filename for keyword in ['manifesto', 'манифест']) or 'Манифест' in content:
                context['manifesto']['text'] = content
            elif any(keyword in filename for keyword in ['codex', 'кодекс']) or 'Кодекс' in content:
                context['principles']['codex'] = content
            elif any(keyword in filename for keyword in ['archetype', 'архетип']) or 'Архетип' in content:
                context['identity']['archetype'] = content
            elif any(keyword in filename for keyword in ['heart', 'сердце']) or 'Сердце' in content:
                context['identity']['heart'] = content
        
        return context
    
    def get_system_capabilities(self) -> Dict[str, Any]:
        """
        Получение информации о возможностях системы.
        
        Returns:
            Словарь с описанием возможностей
        """
        capabilities = {
            'memory_systems': [],
            'action_systems': [],
            'sandbox_features': [],
            'api_endpoints': [],
            'commands': [],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Поиск информации о возможностях
        system_docs = self.search_by_type('system_info', limit=50)
        
        for doc in system_docs:
            content = doc.get('content', '')
            filename = doc.get('filename', '')
            
            if 'memory' in filename.lower():
                capabilities['memory_systems'].append({
                    'name': filename,
                    'description': content[:200] + '...' if len(content) > 200 else content
                })
            elif 'action' in filename.lower():
                capabilities['action_systems'].append({
                    'name': filename,
                    'description': content[:200] + '...' if len(content) > 200 else content
                })
            elif 'sandbox' in filename.lower():
                capabilities['sandbox_features'].append({
                    'name': filename,
                    'description': content[:200] + '...' if len(content) > 200 else content
                })
        
        return capabilities
    
    def _calculate_priority(self, data: Dict[str, Any]) -> float:
        """
        Расчет приоритета для данных.
        
        Args:
            data: Данные для расчета приоритета
            
        Returns:
            float: Приоритет от 0.0 до 1.0
        """
        content_type = data.get('type', 'unknown')
        base_priority = self.priority_weights.get(content_type, 0.5)
        
        # Дополнительные факторы
        if data.get('is_core', False):
            base_priority += 0.1
        
        if data.get('is_critical', False):
            base_priority += 0.1
        
        # Ограничиваем приоритет
        return min(base_priority, 1.0)
    
    def _save_to_weaviate(self, data: Dict[str, Any]) -> None:
        """
        Сохранение данных в Weaviate.
        
        Args:
            data: Данные для сохранения
        """
        try:
            if not self.weaviate_client.collections.exists(self.collection_name):
                self._create_weaviate_collection()
            
            collection = self.weaviate_client.collections.get(self.collection_name)
            
            # Конвертируем дату в RFC3339 формат
            timestamp = data.get('timestamp', '')
            if timestamp:
                # Убираем микросекунды для RFC3339
                if '.' in timestamp:
                    timestamp = timestamp.split('.')[0] + 'Z'
                else:
                    timestamp = timestamp + 'Z'
            
            # Подготавливаем данные для Weaviate
            weaviate_data = {
                'type': data.get('type', 'unknown'),
                'content': data.get('content', ''),
                'filename': data.get('filename', ''),
                'timestamp': timestamp,
                'version': data.get('version', '1.0'),
                'priority': data.get('priority', 0.5)
            }
            
            collection.data.insert(weaviate_data)
            
        except Exception as e:
            print(f"Ошибка при сохранении в Weaviate: {e}")
    
    def _search_in_weaviate(self, query: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Поиск данных в Weaviate.
        
        Args:
            query: Параметры поиска
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных записей
        """
        try:
            if not self.weaviate_client.collections.exists(self.collection_name):
                return []
            
            collection = self.weaviate_client.collections.get(self.collection_name)
            
            # Создаем фильтр для поиска (используем правильный API)
            from weaviate.collections.classes.filters import Filter
            
            filters = []
            for key, value in query.items():
                if key in ['type', 'filename', 'version']:
                    # Используем правильный синтаксис фильтров
                    filters.append(Filter.by_property(key).equal(value))
            
            # Объединяем фильтры
            if filters:
                combined_filter = filters[0]
                for f in filters[1:]:
                    combined_filter = combined_filter & f
            else:
                combined_filter = None
            
            # Выполняем поиск
            results = collection.query.fetch_objects(
                filters=combined_filter,
                limit=limit
            )
            
            return [obj.properties for obj in results.objects]
            
        except Exception as e:
            print(f"Ошибка при поиске в Weaviate: {e}")
            return []
    
    def _create_weaviate_collection(self) -> None:
        """
        Создание коллекции в Weaviate.
        """
        from weaviate.classes.config import Property, DataType, Configure
        
        # Настраиваем векторайзер
        vectorizer_config = Configure.Vectorizer.text2vec_openai()
        
        # Создаем коллекцию
        self.weaviate_client.collections.create(
            name=self.collection_name,
            vectorizer_config=vectorizer_config,
            properties=[
                Property(name="type", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="filename", data_type=DataType.TEXT),
                Property(name="timestamp", data_type=DataType.DATE),
                Property(name="version", data_type=DataType.TEXT),
                Property(name="priority", data_type=DataType.NUMBER)
            ]
        )
    
    def load_core_documents(self, docs_path: str) -> None:
        """
        Загрузка основных документов в системную память.
        
        Args:
            docs_path: Путь к директории с документами
        """
        docs_path = Path(docs_path)
        
        if not docs_path.exists():
            print(f"Директория {docs_path} не существует")
            return
        
        # Проверяем, является ли переданный путь уже core_docs
        if docs_path.name == "core_docs":
            # Если это уже core_docs, загружаем напрямую
            self._load_documents_from_path(docs_path, 'core_docs')
        else:
            # Иначе ищем core_docs внутри переданного пути
            core_docs_path = docs_path / "core_docs"
            if core_docs_path.exists():
                self._load_documents_from_path(core_docs_path, 'core_docs')
        
        # Загружаем project_map.json
        project_map_path = docs_path / "project_map.json"
        if project_map_path.exists():
            self._load_project_map(project_map_path)
        
        # Загружаем weaviate_schema.json
        schema_path = docs_path / "weaviate_schema.json"
        if schema_path.exists():
            self._load_schema(schema_path)
        
        # Загружаем docs/
        docs_dir = docs_path / "docs"
        if docs_dir.exists():
            self._load_documents_from_path(docs_dir, 'docs')
    
    def _load_documents_from_path(self, path: Path, content_type: str) -> None:
        """
        Загрузка документов из указанного пути.
        
        Args:
            path: Путь к директории
            content_type: Тип контента
        """
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix in ['.txt', '.md', '.json']:
                try:
                    # Пробуем разные кодировки для русских файлов
                    content = None
                    encodings = ['utf-8', 'windows-1251', 'cp1251', 'latin-1']
                    
                    for encoding in encodings:
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                content = f.read()
                            break  # Если чтение успешно, выходим из цикла
                        except UnicodeDecodeError:
                            continue
                    
                    if content is None:
                        print(f"Не удалось прочитать файл {file_path} ни с одной из кодировок: {encodings}")
                        continue
                    
                    # Определяем приоритет на основе имени файла
                    is_core = any(keyword in file_path.name.lower() 
                                for keyword in ['манифест', 'завет', 'кодекс', 'архетип', 'manifesto', 'core', 'codex'])
                    
                    self.insert({
                        'type': content_type,
                        'content': content,
                        'filename': file_path.name,
                        'is_core': is_core,
                        'file_path': str(file_path)
                    })
                    
                except Exception as e:
                    print(f"Ошибка при загрузке {file_path}: {e}")
    
    def _load_project_map(self, file_path: Path) -> None:
        """
        Загрузка карты проекта.
        
        Args:
            file_path: Путь к файлу project_map.json
        """
        try:
            # Пробуем разные кодировки
            content = None
            encodings = ['utf-8', 'windows-1251', 'cp1251', 'latin-1']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                print(f"Не удалось прочитать project_map.json ни с одной из кодировок: {encodings}")
                return
            
            self.insert({
                'type': 'project_map',
                'content': content,
                'filename': 'project_map.json',
                'is_critical': True
            })
            
        except Exception as e:
            print(f"Ошибка при загрузке project_map.json: {e}")
    
    def _load_schema(self, file_path: Path) -> None:
        """
        Загрузка схемы базы данных.
        
        Args:
            file_path: Путь к файлу weaviate_schema.json
        """
        try:
            # Пробуем разные кодировки
            content = None
            encodings = ['utf-8', 'windows-1251', 'cp1251', 'latin-1']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                print(f"Не удалось прочитать weaviate_schema.json ни с одной из кодировок: {encodings}")
                return
            
            self.insert({
                'type': 'schema',
                'content': content,
                'filename': 'weaviate_schema.json',
                'is_critical': True
            })
            
        except Exception as e:
            print(f"Ошибка при загрузке weaviate_schema.json: {e}")
    
    # Реализация абстрактных методов BaseMemory
    
    def add(self, key: str, value: Any) -> None:
        """
        Добавить значение в память (реализация абстрактного метода).
        
        Args:
            key: Ключ для сохранения
            value: Значение для сохранения
        """
        self.insert({
            'type': 'key_value',
            'content': str(value),
            'filename': f"{key}.txt",
            'key': key,
            'value': value
        })
    
    def get(self, key: str) -> Optional[Any]:
        """
        Получить значение из памяти (реализация абстрактного метода).
        
        Args:
            key: Ключ для поиска
            
        Returns:
            Значение или None если не найдено
        """
        results = self.search({'key': key}, limit=1)
        if results:
            return results[0].get('value')
        return None
    
    def delete(self, key: str) -> None:
        """
        Удалить значение из памяти (реализация абстрактного метода).
        
        Args:
            key: Ключ для удаления
        """
        results = self.search({'key': key}, limit=1)
        if results:
            # Помечаем как удаленное
            record = results[0]
            record['is_deleted'] = True
            record['deleted_at'] = datetime.utcnow().isoformat()
            self.insert(record)
    
    def clear(self) -> None:
        """
        Очистить память (реализация абстрактного метода).
        """
        # В базовой реализации просто очищаем локальную память
        self._local_memory = []
    
    def get_all(self) -> Dict[str, Any]:
        """
        Получить все значения из памяти (реализация абстрактного метода).
        
        Returns:
            Словарь всех значений
        """
        results = self.search({}, limit=1000)  # Получаем все записи
        return {r.get('key', f"item_{i}"): r.get('value', r.get('content', '')) 
                for i, r in enumerate(results)}
    
    def _search_local(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Поиск в локальной памяти.
        
        Args:
            query: Параметры поиска
            
        Returns:
            Список найденных записей
        """
        results = []
        for item in self._local_memory:
            # Проверяем, соответствует ли элемент запросу
            matches = True
            for key, value in query.items():
                if key in item:
                    # Для строковых значений используем частичное совпадение
                    if isinstance(value, str) and isinstance(item[key], str):
                        if value.lower() not in item[key].lower():
                            matches = False
                            break
                    # Для точных значений
                    elif item[key] != value:
                        matches = False
                        break
                else:
                    # Если ключ не найден, но мы ищем точное совпадение
                    if key != 'type' or value != 'any':  # Исключение для 'type': 'any'
                        matches = False
                        break
            if matches:
                results.append(item)
        return results 