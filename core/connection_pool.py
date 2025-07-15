"""
Connection Pool - пул соединений для работы с базами данных
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Базовый пул соединений"""

    def __init__(self):
        self.connections = {}
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "idle_connections": 0
        }
        self._graphiti_memory_cache = {}
        logger.info("✅ ConnectionPool инициализирован")

    async def get_connection(self, name: str = "default") -> dict[str, Any]:
        """Получает соединение из пула"""
        if name not in self.connections:
            self.connections[name] = {
                "id": f"conn_{len(self.connections)}",
                "name": name,
                "status": "active",
                "created_at": "2025-07-14T13:30:00Z"
            }
            self.stats["total_connections"] += 1
            self.stats["active_connections"] += 1

        logger.debug(f"🔗 Получено соединение: {name}")
        return self.connections[name]

    async def release_connection(self, name: str = "default"):
        """Освобождает соединение обратно в пул"""
        if name in self.connections:
            self.connections[name]["status"] = "idle"
            self.stats["active_connections"] -= 1
            self.stats["idle_connections"] += 1
            logger.debug(f"🔓 Освобождено соединение: {name}")

    def get_graphiti_memory_adapter(self, short_term_limit: int = 20):
        """Получает кешированный экземпляр GraphitiMemoryAdapter"""
        cache_key = f"graphiti_memory_{short_term_limit}"

        if cache_key not in self._graphiti_memory_cache:
            from langchain_api.memory.graphiti_memory import GraphitiMemoryAdapter
            self._graphiti_memory_cache[cache_key] = GraphitiMemoryAdapter(
                short_term_limit=short_term_limit
            )
            logger.debug(f"🧠 Создан новый экземпляр GraphitiMemoryAdapter (limit={short_term_limit})")

        return self._graphiti_memory_cache[cache_key]

    def get_stats(self) -> dict[str, Any]:
        """Возвращает статистику пула"""
        return self.stats.copy()

    async def close_all(self):
        """Закрывает все соединения"""
        self.connections.clear()
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "idle_connections": 0
        }
        logger.info("🔒 Все соединения закрыты")


# Глобальный экземпляр пула
_connection_pool: ConnectionPool | None = None


def get_connection_pool() -> ConnectionPool:
    """Возвращает глобальный экземпляр пула соединений"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool()
    return _connection_pool


@asynccontextmanager
async def get_connection(name: str = "default"):
    """Контекстный менеджер для работы с соединениями"""
    pool = get_connection_pool()
    connection = await pool.get_connection(name)
    try:
        yield connection
    finally:
        await pool.release_connection(name)
