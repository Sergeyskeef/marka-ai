"""
MemoryManager - менеджер памяти для управления различными типами памяти
"""

import logging
from typing import Any, Optional
from datetime import timedelta

# Импортируем GraphitiMemoryAdapter
from .graphiti_adapter import graphiti_adapter
from .models import MemoryEntry, MemoryMetadata, MemoryResponse
from .hybrid_search import HybridSearchEngine
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class MemoryManager:
    """Менеджер памяти"""

    def __init__(self):
        self.memory_instances = {}
        # Не пересекаемся по имени с методом hybrid_search
        self.hybrid_search_engine = None  # Ленивая инициализация
        self.memory_stats = {
            "total_entries": 0,
            "memory_types": []
        }
        logger.info("✅ MemoryManager инициализирован")

    def register_memory(self, name: str, memory_instance: Any):
        """Регистрирует экземпляр памяти"""
        self.memory_instances[name] = memory_instance
        self.memory_stats["memory_types"].append(name)
        logger.info(f"🧠 Зарегистрирована память: {name}")

    def get_memory(self, name: str) -> Any | None:
        """Возвращает экземпляр памяти по имени"""
        return self.memory_instances.get(name)

    def list_memories(self) -> list[str]:
        """Возвращает список зарегистрированных типов памяти"""
        return list(self.memory_instances.keys())

    def get_memory_stats(self) -> dict[str, Any]:
        """Возвращает статистику памяти"""
        stats = self.memory_stats.copy()
        stats["registered_memories"] = len(self.memory_instances)
        return stats

    def clear_memory(self, name: str) -> bool:
        """Очищает память по имени"""
        if name in self.memory_instances:
            memory = self.memory_instances[name]
            if hasattr(memory, 'clear_all'):
                memory.clear_all()
            elif hasattr(memory, 'clear'):
                memory.clear()
            logger.info(f"🧹 Очищена память: {name}")
            return True
        return False

    def clear_all_memories(self):
        """Очищает все типы памяти"""
        for name in self.memory_instances:
            self.clear_memory(name)
        logger.info("🧹 Очищены все типы памяти")

    # Новые методы для работы с Graphiti
    async def add_episode(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Добавляет эпизод в Graphiti память"""
        try:
            # Валидируем входные данные
            if metadata:
                # Приводим к dict, даже если пришел MemoryMetadata
                if isinstance(metadata, MemoryMetadata):
                    validated_metadata = metadata.model_dump(exclude_none=True)
                else:
                    validated_metadata = MemoryMetadata(**metadata).model_dump(exclude_none=True)
            else:
                validated_metadata = None
            
            entry = MemoryEntry(text=text, metadata=validated_metadata)
            
            # Передаем в адаптер уже сериализованные метаданные (dict)
            result = await graphiti_adapter.create_episode(entry.text, validated_metadata)
            if result.get("success", True):  # Graphiti может не возвращать success поле
                self.memory_stats["total_entries"] += 1
                logger.info(f"✅ Эпизод добавлен в память: {entry.text[:50]}...")
            return result
        except ValueError as e:
            logger.error(f"❌ Ошибка валидации данных: {str(e)}")
            return {"success": False, "error": f"Validation error: {str(e)}"}
        except Exception as e:
            logger.error(f"❌ Ошибка добавления эпизода: {str(e)}")
            return {"success": False, "error": str(e)}

    async def search_episodes(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Ищет эпизоды в Graphiti памяти"""
        try:
            result = await graphiti_adapter.search_episodes(query, limit)
            logger.info(f"🔍 Поиск выполнен: '{query}' -> {len(result.get('items', []))} результатов")
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка поиска эпизодов: {str(e)}")
            return {"items": [], "total": 0, "error": str(e)}

    async def get_episode(self, episode_id: str) -> dict[str, Any]:
        """Получает эпизод по ID"""
        try:
            result = await graphiti_adapter.get_episode(episode_id)
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения эпизода {episode_id}: {str(e)}")
            return {"error": str(e)}

    async def list_episodes(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Получает список эпизодов"""
        try:
            result = await graphiti_adapter.list_episodes(limit, offset)
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка эпизодов: {str(e)}")
            return {"items": [], "total": 0, "error": str(e)}

    async def health_check(self) -> dict[str, Any]:
        """Проверяет здоровье Graphiti памяти"""
        try:
            result = await graphiti_adapter.health_check()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка проверки здоровья Graphiti: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def save(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Сохраняет информацию в память (алиас для add_episode).
        
        Args:
            text: Текст для сохранения
            metadata: Дополнительные метаданные
            
        Returns:
            Результат операции с полями success, id, error
        """
        return await self.add_episode(text, metadata)
    
    async def hybrid_search(
        self,
        query: str,
        user_id: str,
        k: int = 10,
        filters: Optional[dict[str, Any]] = None,
        time_window: Optional[timedelta] = None,
        use_hybrid: bool = True
    ) -> list[dict[str, Any]]:
        """
        Выполняет гибридный поиск в памяти.
        
        Args:
            query: Поисковый запрос
            user_id: ID пользователя
            k: Количество результатов
            filters: Дополнительные фильтры
            time_window: Временное окно для поиска (например, последние 7 дней)
            use_hybrid: Использовать ли гибридный поиск (если False, то только векторный)
            
        Returns:
            Список результатов поиска с расширенными метаданными
        """
        try:
            if use_hybrid:
                # Инициализируем гибридный поиск если еще не создан
                if self.hybrid_search_engine is None:
                    self.hybrid_search_engine = HybridSearchEngine(graphiti_adapter)
                
                # Выполняем гибридный поиск
                # Готовим фильтры и эмбеддинг запроса
                _filters: dict[str, Any] = dict(filters or {})
                try:
                    client = AsyncOpenAI()
                    emb_resp = await client.embeddings.create(
                        model="text-embedding-3-small",
                        input=query
                    )
                    query_embedding = emb_resp.data[0].embedding
                    _filters["query_embedding"] = query_embedding
                except Exception:
                    # Если эмбеддинг не доступен, продолжаем без него
                    pass

                results = await self.hybrid_search_engine.search(
                    query=query,
                    user_id=user_id,
                    k=k,
                    filters=_filters,
                    time_window=time_window
                )
                
                # Преобразуем результаты в словари
                return [r.to_dict() for r in results]
            else:
                # Используем обычный векторный поиск
                response = await self.search_episodes(query, limit=k)
                results = []
                for item in response.get("items", []):
                    results.append({
                        "id": item["id"],
                        "text": item["text"],
                        "score": item.get("similarity", 0.8),
                        "source": "vector",
                        "metadata": item.get("metadata", {})
                    })
                return results
                
        except Exception as e:
            logger.error(f"❌ Ошибка гибридного поиска: {str(e)}")
            return []


# Глобальный экземпляр MemoryManager
memory_manager = MemoryManager()
