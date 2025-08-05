"""
Тесты производительности системы памяти Graphiti
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import pytest
from unittest.mock import AsyncMock, patch

from core.memory.memory_manager import MemoryManager
from core.memory.graphiti_adapter import GraphitiMemoryAdapter
from core.memory.graphiti_cache import GraphitiCache


class PerformanceMetrics:
    """Класс для сбора метрик производительности"""
    
    def __init__(self):
        self.latencies: List[float] = []
        self.errors: int = 0
        self.total_requests: int = 0
        
    def add_latency(self, latency: float):
        """Добавляет замер латентности"""
        self.latencies.append(latency)
        self.total_requests += 1
        
    def add_error(self):
        """Увеличивает счетчик ошибок"""
        self.errors += 1
        self.total_requests += 1
        
    def get_stats(self) -> Dict[str, float]:
        """Возвращает статистику"""
        if not self.latencies:
            return {}
            
        sorted_latencies = sorted(self.latencies)
        
        return {
            "total_requests": self.total_requests,
            "errors": self.errors,
            "error_rate": (self.errors / self.total_requests * 100) if self.total_requests > 0 else 0,
            "mean": statistics.mean(self.latencies),
            "median": statistics.median(self.latencies),
            "p50": sorted_latencies[int(len(sorted_latencies) * 0.5)],
            "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)],
            "p99": sorted_latencies[int(len(sorted_latencies) * 0.99)] if len(sorted_latencies) > 100 else sorted_latencies[-1],
            "min": min(self.latencies),
            "max": max(self.latencies)
        }


@pytest.mark.asyncio
class TestMemoryPerformance:
    """Тесты производительности системы памяти"""
    
    async def test_search_latency_without_cache(self):
        """Тест латентности поиска без кеша"""
        # Мокаем HTTP ответ
        mock_response = {
            "nodes": [
                {
                    "id": f"node-{i}",
                    "type": "Episode",
                    "properties": {
                        "msg": f"Test message {i}",
                        "created_at": int(time.time()),
                        "user_id": "test_user"
                    },
                    "score": 0.9 - (i * 0.1)
                }
                for i in range(10)
            ]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            # Настраиваем мок
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance
            
            mock_get = AsyncMock()
            mock_get.status_code = 200
            mock_get.json.return_value = mock_response
            mock_instance.get = mock_get
            
            # Создаем адаптер без кеша
            adapter = GraphitiMemoryAdapter(use_cache=False)
            metrics = PerformanceMetrics()
            
            # Выполняем 100 запросов
            queries = [f"test query {i % 10}" for i in range(100)]
            
            for query in queries:
                start_time = time.time()
                try:
                    result = await adapter.search_episodes(query, limit=10)
                    latency = (time.time() - start_time) * 1000  # в миллисекундах
                    metrics.add_latency(latency)
                except Exception as e:
                    metrics.add_error()
                    
            stats = metrics.get_stats()
            
            # Проверяем результаты
            assert stats["error_rate"] == 0, "Не должно быть ошибок"
            assert stats["p95"] < 50, "P95 латентность должна быть < 50ms"
            assert stats["mean"] < 30, "Средняя латентность должна быть < 30ms"
            
            print(f"\n📊 Статистика без кеша:")
            print(f"  - Всего запросов: {stats['total_requests']}")
            print(f"  - Средняя латентность: {stats['mean']:.2f}ms")
            print(f"  - P50: {stats['p50']:.2f}ms")
            print(f"  - P95: {stats['p95']:.2f}ms")
            print(f"  - P99: {stats['p99']:.2f}ms")
    
    async def test_search_latency_with_cache(self):
        """Тест латентности поиска с кешем"""
        # Мокаем Redis
        with patch('redis.asyncio.from_url') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            
            # Симулируем кеш (первый запрос - miss, остальные - hit)
            cache_storage = {}
            
            async def mock_get(key):
                return cache_storage.get(key)
                
            async def mock_setex(key, ttl, value):
                cache_storage[key] = value
                
            mock_redis_instance.get = mock_get
            mock_redis_instance.setex = mock_setex
            mock_redis_instance.incr = AsyncMock()
            mock_redis_instance.scan_iter = AsyncMock(return_value=iter([]))
            
            # Мокаем HTTP ответ
            mock_response = {
                "nodes": [
                    {
                        "id": f"node-{i}",
                        "type": "Episode",
                        "properties": {
                            "msg": f"Test message {i}",
                            "created_at": int(time.time())
                        }
                    }
                    for i in range(10)
                ]
            }
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_instance = AsyncMock()
                mock_client.return_value = mock_instance
                
                mock_get = AsyncMock()
                mock_get.status_code = 200
                mock_get.json.return_value = mock_response
                mock_instance.get = mock_get
                
                # Создаем адаптер с кешем
                adapter = GraphitiMemoryAdapter(use_cache=True)
                metrics = PerformanceMetrics()
                
                # Выполняем 100 запросов (10 уникальных, повторяющихся)
                queries = [f"test query {i % 10}" for i in range(100)]
                
                for query in queries:
                    start_time = time.time()
                    try:
                        result = await adapter.search_episodes(query, limit=10)
                        latency = (time.time() - start_time) * 1000
                        metrics.add_latency(latency)
                    except Exception as e:
                        metrics.add_error()
                        
                stats = metrics.get_stats()
                
                # С кешем латентность должна быть значительно ниже
                assert stats["error_rate"] == 0, "Не должно быть ошибок"
                assert stats["p95"] < 20, "P95 латентность с кешем должна быть < 20ms"
                assert stats["mean"] < 10, "Средняя латентность с кешем должна быть < 10ms"
                
                # Проверяем, что HTTP вызовов было меньше чем запросов
                assert mock_instance.get.call_count < 20, "Должно быть максимум 10 HTTP вызовов"
                
                print(f"\n📊 Статистика с кешем:")
                print(f"  - Всего запросов: {stats['total_requests']}")
                print(f"  - HTTP вызовов: {mock_instance.get.call_count}")
                print(f"  - Cache hit rate: {((100 - mock_instance.get.call_count) / 100 * 100):.1f}%")
                print(f"  - Средняя латентность: {stats['mean']:.2f}ms")
                print(f"  - P50: {stats['p50']:.2f}ms")
                print(f"  - P95: {stats['p95']:.2f}ms")
                print(f"  - P99: {stats['p99']:.2f}ms")
    
    async def test_concurrent_requests(self):
        """Тест производительности при параллельных запросах"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance
            
            # Симулируем задержку сети
            async def mock_get_with_delay(*args, **kwargs):
                await asyncio.sleep(0.01)  # 10ms задержка
                response = AsyncMock()
                response.status_code = 200
                response.json.return_value = {"nodes": []}
                return response
                
            mock_instance.get = mock_get_with_delay
            
            adapter = GraphitiMemoryAdapter(use_cache=False)
            
            # Запускаем 50 параллельных запросов
            start_time = time.time()
            
            async def make_request(i):
                return await adapter.search_episodes(f"query {i}", limit=10)
                
            results = await asyncio.gather(
                *[make_request(i) for i in range(50)],
                return_exceptions=True
            )
            
            total_time = (time.time() - start_time) * 1000
            
            # Подсчитываем ошибки
            errors = sum(1 for r in results if isinstance(r, Exception))
            
            print(f"\n📊 Параллельные запросы:")
            print(f"  - Всего запросов: 50")
            print(f"  - Общее время: {total_time:.2f}ms")
            print(f"  - Среднее время на запрос: {total_time/50:.2f}ms")
            print(f"  - Ошибок: {errors}")
            
            # При параллельном выполнении должно быть быстрее
            assert total_time < 1000, "50 параллельных запросов должны выполниться за < 1 сек"
            assert errors == 0, "Не должно быть ошибок при параллельных запросах"
    
    async def test_cache_invalidation_performance(self):
        """Тест производительности инвалидации кеша"""
        with patch('redis.asyncio.from_url') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            
            # Симулируем большой кеш
            cache_keys = [f"graphiti:cache:search:user_test_{i}" for i in range(1000)]
            
            async def mock_scan_iter(match):
                # Возвращаем ключи, соответствующие паттерну
                pattern = match.replace("*", "")
                for key in cache_keys:
                    if pattern in key:
                        yield key
                        
            mock_redis_instance.scan_iter = mock_scan_iter
            mock_redis_instance.delete = AsyncMock()
            
            cache = GraphitiCache()
            cache._redis = mock_redis_instance
            
            # Замеряем время инвалидации
            start_time = time.time()
            await cache.invalidate_user_cache("test")
            invalidation_time = (time.time() - start_time) * 1000
            
            print(f"\n📊 Инвалидация кеша:")
            print(f"  - Ключей в кеше: 1000")
            print(f"  - Время инвалидации: {invalidation_time:.2f}ms")
            print(f"  - Удалено ключей: {mock_redis_instance.delete.call_count}")
            
            assert invalidation_time < 100, "Инвалидация 1000 ключей должна занимать < 100ms"


if __name__ == "__main__":
    # Запускаем тесты
    asyncio.run(pytest.main([__file__, "-v"]))