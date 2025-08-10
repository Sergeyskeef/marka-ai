"""
Система кеширования для Graphiti
Оптимизирует производительность за счет кеширования частых запросов
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class GraphitiCache:
    """
    Кеш для результатов запросов Graphiti.
    Использует Redis для хранения результатов.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        Инициализация кеша.
        
        Args:
            redis_url: URL подключения к Redis
        """
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self.default_ttl = 3600  # 1 час
        self.user_cache_ttl = 1800  # 30 минут для пользовательских данных
        
    async def connect(self):
        """Подключение к Redis"""
        if not self._redis:
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info("✅ Подключение к Redis для кеша установлено")
    
    async def close(self):
        """Закрытие соединения"""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    def _get_cache_key(self, query_type: str, params: dict) -> str:
        """
        Генерирует ключ кеша на основе типа запроса и параметров.
        
        Args:
            query_type: Тип запроса (search, get_episodes, etc.)
            params: Параметры запроса
            
        Returns:
            Ключ кеша
        """
        # Сортируем параметры для консистентности
        sorted_params = json.dumps(params, sort_keys=True)
        content = f"{query_type}:{sorted_params}"
        hash_key = hashlib.md5(content.encode()).hexdigest()
        
        return f"graphiti:cache:{query_type}:{hash_key}"
    
    async def get(
        self, 
        query_type: str, 
        params: dict,
        user_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Получает результат из кеша.
        
        Args:
            query_type: Тип запроса
            params: Параметры запроса
            user_id: ID пользователя (опционально)
            
        Returns:
            Закешированный результат или None
        """
        if not self._redis:
            await self.connect()
            
        # Добавляем user_id в параметры если указан
        if user_id:
            params = {**params, "user_id": user_id}
            
        key = self._get_cache_key(query_type, params)
        
        try:
            cached = await self._redis.get(key)
            if cached:
                logger.debug(f"Cache HIT: {query_type} - {key[:20]}...")
                result = json.loads(cached)
                
                # Обновляем статистику
                await self._increment_stats("hits", query_type)
                
                return result
            else:
                logger.debug(f"Cache MISS: {query_type} - {key[:20]}...")
                await self._increment_stats("misses", query_type)
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при чтении из кеша: {e}")
            return None
    
    async def set(
        self,
        query_type: str,
        params: dict,
        result: dict,
        ttl: Optional[int] = None,
        user_id: Optional[str] = None
    ):
        """
        Сохраняет результат в кеш.
        
        Args:
            query_type: Тип запроса
            params: Параметры запроса
            result: Результат для кеширования
            ttl: Время жизни в секундах
            user_id: ID пользователя (опционально)
        """
        if not self._redis:
            await self.connect()
            
        # Добавляем user_id в параметры если указан
        if user_id:
            params = {**params, "user_id": user_id}
            
        key = self._get_cache_key(query_type, params)
        
        # Определяем TTL
        if ttl is None:
            ttl = self.user_cache_ttl if user_id else self.default_ttl
            
        try:
            # Добавляем метаданные
            cache_data = {
                "result": result,
                "cached_at": datetime.now().isoformat(),
                "query_type": query_type,
                "ttl": ttl
            }
            
            await self._redis.setex(
                key,
                ttl,
                json.dumps(cache_data)
            )
            
            logger.debug(f"Cache SET: {query_type} - {key[:20]}... (TTL: {ttl}s)")
            
            # Обновляем статистику
            await self._increment_stats("sets", query_type)
            
        except Exception as e:
            logger.error(f"Ошибка при записи в кеш: {e}")
    
    async def invalidate_pattern(self, pattern: str):
        """
        Инвалидирует все ключи по паттерну.
        
        Args:
            pattern: Паттерн для поиска ключей
        """
        if not self._redis:
            await self.connect()
            
        try:
            count = 0
            async for key in self._redis.scan_iter(match=f"graphiti:cache:{pattern}"):
                await self._redis.delete(key)
                count += 1
                
            logger.info(f"Инвалидировано {count} ключей по паттерну: {pattern}")
            
        except Exception as e:
            logger.error(f"Ошибка при инвалидации кеша: {e}")
    
    async def invalidate_user_cache(self, user_id: str):
        """
        Инвалидирует весь кеш пользователя.
        
        Args:
            user_id: ID пользователя
        """
        await self.invalidate_pattern(f"*user_id*{user_id}*")
    
    async def invalidate_query_type(self, query_type: str):
        """
        Инвалидирует весь кеш для определенного типа запросов.
        
        Args:
            query_type: Тип запроса
        """
        await self.invalidate_pattern(f"{query_type}:*")
    
    async def get_stats(self) -> dict[str, Any]:
        """
        Получает статистику использования кеша.
        
        Returns:
            Словарь со статистикой
        """
        if not self._redis:
            await self.connect()
            
        try:
            stats = {}
            
            # Получаем общую статистику
            for metric in ["hits", "misses", "sets"]:
                key = f"graphiti:stats:{metric}"
                value = await self._redis.get(key)
                stats[metric] = int(value) if value else 0
            
            # Вычисляем hit rate
            total = stats["hits"] + stats["misses"]
            stats["hit_rate"] = (stats["hits"] / total * 100) if total > 0 else 0
            
            # Получаем статистику по типам запросов
            stats["by_type"] = {}
            async for key in self._redis.scan_iter(match="graphiti:stats:*:*"):
                parts = key.split(":")
                if len(parts) >= 4:
                    metric_type = parts[2]
                    query_type = parts[3]
                    
                    if query_type not in stats["by_type"]:
                        stats["by_type"][query_type] = {}
                        
                    value = await self._redis.get(key)
                    stats["by_type"][query_type][metric_type] = int(value) if value else 0
            
            # Размер кеша
            cache_size = 0
            async for _ in self._redis.scan_iter(match="graphiti:cache:*"):
                cache_size += 1
            stats["cache_size"] = cache_size
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return {}
    
    async def _increment_stats(self, metric: str, query_type: str):
        """
        Увеличивает счетчик статистики.
        
        Args:
            metric: Метрика (hits, misses, sets)
            query_type: Тип запроса
        """
        try:
            # Общий счетчик
            await self._redis.incr(f"graphiti:stats:{metric}")
            
            # Счетчик по типу запроса
            await self._redis.incr(f"graphiti:stats:{metric}:{query_type}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}")
    
    async def clear_all(self):
        """Очищает весь кеш (осторожно!)"""
        if not self._redis:
            await self.connect()
            
        try:
            count = 0
            async for key in self._redis.scan_iter(match="graphiti:cache:*"):
                await self._redis.delete(key)
                count += 1
                
            logger.warning(f"⚠️ Очищен весь кеш Graphiti: {count} ключей удалено")
            
        except Exception as e:
            logger.error(f"Ошибка при очистке кеша: {e}")


# Глобальный экземпляр кеша
_cache_instance: Optional[GraphitiCache] = None


async def get_cache() -> GraphitiCache:
    """Получает глобальный экземпляр кеша"""
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = GraphitiCache()
        await _cache_instance.connect()
        
    return _cache_instance