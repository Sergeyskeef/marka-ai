"""
MemoryManager - менеджер памяти для управления различными типами памяти
"""

import logging
from typing import Any

# Импортируем GraphitiMemoryAdapter
from .graphiti_adapter import graphiti_adapter

logger = logging.getLogger(__name__)


class MemoryManager:
    """Менеджер памяти"""

    def __init__(self):
        self.memory_instances = {}
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
            result = await graphiti_adapter.create_episode(text, metadata)
            if result.get("success", True):  # Graphiti может не возвращать success поле
                self.memory_stats["total_entries"] += 1
                logger.info(f"✅ Эпизод добавлен в память: {text[:50]}...")
            return result
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


# Глобальный экземпляр MemoryManager
memory_manager = MemoryManager()
