# 🚀 План оптимизации системы памяти Graphiti + Neo4j

## 📊 Текущее состояние

### Конфигурация Neo4j:
- **Версия**: Neo4j Community (через Docker)
- **Память**: Стандартные настройки контейнера
- **Индексы**: Базовые индексы из `init_memory_indexes.py`
- **Плагины**: APOC включен

### Конфигурация Graphiti:
- **Режим**: Shadow mode (только логирование)
- **Таймауты**: 10 сек (запросы), 30 сек (подключение)
- **Retry**: 3 попытки с задержкой 1 сек
- **Подключение**: Через `httpx.AsyncClient` с RetryableHTTPClient

## 🎯 Цели оптимизации

1. **Скорость поиска**: < 100мс для 95% запросов
2. **Масштабируемость**: Поддержка 10M+ узлов
3. **Надежность**: 99.9% uptime
4. **Качество**: Высокая релевантность результатов

## 🔧 Оптимизации Neo4j

### 1. Настройка памяти JVM
```yaml
# docker-compose.yml дополнения
graphiti-neo4j:
  environment:
    # Heap memory (50% от доступной памяти)
    - NEO4J_server_memory_heap_initial__size=2g
    - NEO4J_server_memory_heap_max__size=2g
    # Page cache (25-50% от доступной памяти)
    - NEO4J_server_memory_pagecache_size=2g
    # Transaction log
    - NEO4J_db_transaction_logs_rotation_retention__policy=2 days
    # Query cache
    - NEO4J_db_query__cache__size=1000
```

### 2. Оптимизация индексов
```cypher
// Композитные индексы для частых запросов
CREATE INDEX episode_user_timestamp IF NOT EXISTS
FOR (e:Episode) ON (e.user_id, e.created_at);

CREATE INDEX entity_name_type IF NOT EXISTS  
FOR (n:Entity) ON (n.name, n.type);

// Полнотекстовый поиск с анализаторами
CALL db.index.fulltext.createNodeIndex(
  'episode_search_optimized',
  ['Episode'],
  ['msg', 'source', 'tags'],
  {
    analyzer: 'russian',
    eventually_consistent: true
  }
);

// Векторный индекс для эмбеддингов
CALL db.index.vector.createNodeIndex(
  'episode_embeddings',
  'Episode',
  'embedding',
  1536,  // размерность OpenAI embeddings
  'cosine'
);
```

### 3. Оптимизация запросов

#### A. Использование индексных хинтов
```cypher
// Плохо
MATCH (e:Episode) 
WHERE e.user_id = $userId AND e.created_at > $date
RETURN e

// Хорошо
MATCH (e:Episode)
USING INDEX e:Episode(user_id, created_at)
WHERE e.user_id = $userId AND e.created_at > $date
RETURN e
```

#### B. Параллельные запросы
```cypher
// Включаем параллельную обработку
CYPHER runtime = parallel
MATCH (e:Episode)-[:MENTIONS]->(entity:Entity)
WHERE e.user_id = $userId
RETURN entity, count(e) as mentions
ORDER BY mentions DESC
```

#### C. Профилирование и оптимизация
```python
# core/memory/neo4j_optimizer.py
class Neo4jOptimizer:
    async def analyze_query_performance(self, query: str):
        """Анализирует производительность запроса"""
        profile_query = f"PROFILE {query}"
        result = await self.driver.execute_query(profile_query)
        
        # Анализируем план выполнения
        db_hits = result.summary.profile.db_hits
        time_ms = result.summary.result_available_after
        
        if db_hits > 10000:
            logger.warning(f"Неоптимальный запрос: {db_hits} db hits")
            # Предлагаем оптимизации
            
        return {
            "db_hits": db_hits,
            "time_ms": time_ms,
            "optimized": db_hits < 10000
        }
```

## 🚀 Оптимизации Graphiti

### 1. Кеширование запросов
```python
# core/memory/graphiti_cache.py
from typing import Optional
import hashlib
import json
from datetime import datetime, timedelta

class GraphitiCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.default_ttl = 3600  # 1 час
        
    def _get_cache_key(self, query: str, params: dict) -> str:
        """Генерирует ключ кеша"""
        content = f"{query}{json.dumps(params, sort_keys=True)}"
        return f"graphiti:cache:{hashlib.md5(content.encode()).hexdigest()}"
    
    async def get(self, query: str, params: dict) -> Optional[dict]:
        """Получает результат из кеша"""
        key = self._get_cache_key(query, params)
        cached = await self.redis.get(key)
        
        if cached:
            logger.debug(f"Cache hit for query: {query[:50]}...")
            return json.loads(cached)
        
        return None
    
    async def set(self, query: str, params: dict, result: dict, ttl: int = None):
        """Сохраняет результат в кеш"""
        key = self._get_cache_key(query, params)
        ttl = ttl or self.default_ttl
        
        await self.redis.setex(
            key, 
            ttl, 
            json.dumps(result)
        )
        
    async def invalidate_user_cache(self, user_id: str):
        """Инвалидирует кеш пользователя"""
        pattern = f"graphiti:cache:*{user_id}*"
        async for key in self.redis.scan_iter(match=pattern):
            await self.redis.delete(key)
```

### 2. Пулы соединений и батчинг
```python
# core/memory/graphiti_adapter.py улучшения
class GraphitiMemoryAdapter:
    def __init__(self):
        # Оптимизированный пул соединений
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(10.0, connect=5.0, pool=30.0),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0
            ),
            http2=True  # HTTP/2 для мультиплексирования
        )
        
        # Батч-процессор
        self._batch_processor = BatchProcessor(
            process_func=self._process_batch,
            batch_size=50,
            batch_timeout=0.1  # 100ms
        )
    
    async def add_episodes_batch(self, episodes: List[dict]) -> List[dict]:
        """Добавляет эпизоды батчами"""
        return await self._batch_processor.add_items(episodes)
    
    async def _process_batch(self, items: List[dict]) -> List[dict]:
        """Обрабатывает батч эпизодов"""
        response = await self._retry_client.post(
            "/episodes/batch",
            json={"episodes": items}
        )
        return response.json()["results"]
```

### 3. Умная предзагрузка (Prefetching)
```python
# core/memory/prefetch_manager.py
class PrefetchManager:
    def __init__(self, memory_manager):
        self.memory = memory_manager
        self.prefetch_queue = asyncio.Queue(maxsize=1000)
        self.worker_task = None
        
    async def start(self):
        """Запускает воркер предзагрузки"""
        self.worker_task = asyncio.create_task(self._prefetch_worker())
        
    async def _prefetch_worker(self):
        """Воркер для предзагрузки данных"""
        while True:
            try:
                user_id, context = await self.prefetch_queue.get()
                
                # Анализируем контекст и предзагружаем
                if "topic" in context:
                    # Предзагружаем похожие темы
                    await self._prefetch_similar_topics(user_id, context["topic"])
                    
                if "entities" in context:
                    # Предзагружаем связанные сущности
                    await self._prefetch_related_entities(user_id, context["entities"])
                    
            except Exception as e:
                logger.error(f"Prefetch error: {e}")
                
    async def hint(self, user_id: str, context: dict):
        """Подсказка для предзагрузки"""
        try:
            await self.prefetch_queue.put_nowait((user_id, context))
        except asyncio.QueueFull:
            pass  # Игнорируем если очередь полна
```

## 📈 Оптимизация векторного поиска

### 1. Гибридный поиск (Vector + Graph)
```python
# core/memory/hybrid_search.py
class HybridSearch:
    def __init__(self, graphiti_adapter):
        self.graphiti = graphiti_adapter
        
    async def search(
        self, 
        query: str, 
        user_id: str,
        filters: dict = None,
        k: int = 10
    ) -> List[dict]:
        """Гибридный поиск: векторный + графовый"""
        
        # 1. Векторный поиск
        vector_results = await self._vector_search(query, k * 2)
        
        # 2. Расширение через граф
        expanded_results = await self._graph_expansion(
            vector_results, 
            user_id,
            filters
        )
        
        # 3. Реранжирование
        final_results = await self._rerank_results(
            query,
            expanded_results,
            k
        )
        
        return final_results
    
    async def _graph_expansion(self, vector_results: List[dict], user_id: str, filters: dict):
        """Расширяет результаты через граф"""
        expanded = []
        
        for result in vector_results:
            # Находим связанные узлы
            query = """
            MATCH (e:Episode {id: $episode_id})-[:MENTIONS]->(entity:Entity)
            MATCH (entity)<-[:MENTIONS]-(related:Episode)
            WHERE related.user_id = $user_id
            AND related.id <> e.id
            RETURN related, 
                   count(entity) as shared_entities,
                   collect(entity.name) as entities
            ORDER BY shared_entities DESC
            LIMIT 5
            """
            
            related = await self.graphiti.query(query, {
                "episode_id": result["id"],
                "user_id": user_id
            })
            
            expanded.append({
                **result,
                "related": related,
                "expansion_score": len(related) * 0.1
            })
            
        return expanded
```

### 2. Адаптивные эмбеддинги
```python
# core/memory/adaptive_embeddings.py
class AdaptiveEmbeddingManager:
    def __init__(self):
        self.models = {
            "general": "text-embedding-3-small",
            "technical": "text-embedding-3-large",
            "multilingual": "multilingual-e5-large"
        }
        self.user_preferences = {}
        
    async def get_embedding(self, text: str, user_id: str) -> List[float]:
        """Выбирает оптимальную модель для пользователя"""
        # Определяем тип контента
        content_type = await self._detect_content_type(text)
        
        # Учитываем предпочтения пользователя
        user_pref = self.user_preferences.get(user_id, {})
        
        # Выбираем модель
        if user_pref.get("language") != "ru" and self._is_multilingual(text):
            model = self.models["multilingual"]
        elif content_type == "technical":
            model = self.models["technical"]
        else:
            model = self.models["general"]
            
        # Генерируем эмбеддинг
        return await self._generate_embedding(text, model)
    
    async def update_user_preferences(self, user_id: str, feedback: dict):
        """Обновляет предпочтения на основе обратной связи"""
        if feedback["quality"] == "good":
            # Запоминаем успешные настройки
            self.user_preferences[user_id] = {
                "preferred_model": feedback["model"],
                "language": feedback["language"],
                "avg_query_length": feedback["query_length"]
            }
```

## 🔍 Мониторинг и метрики

### 1. Система метрик
```python
# core/memory/metrics_collector.py
class MemoryMetricsCollector:
    def __init__(self):
        self.metrics = {
            "query_latency": [],
            "cache_hit_rate": 0,
            "index_usage": {},
            "error_rate": 0
        }
        
    async def track_query(self, query_type: str, duration_ms: float, hit_cache: bool):
        """Отслеживает метрики запроса"""
        self.metrics["query_latency"].append({
            "type": query_type,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(),
            "cache_hit": hit_cache
        })
        
        # Вычисляем percentiles
        if len(self.metrics["query_latency"]) > 100:
            latencies = [m["duration_ms"] for m in self.metrics["query_latency"][-1000:]]
            self.metrics["p50"] = np.percentile(latencies, 50)
            self.metrics["p95"] = np.percentile(latencies, 95)
            self.metrics["p99"] = np.percentile(latencies, 99)
    
    async def export_prometheus(self):
        """Экспортирует метрики для Prometheus"""
        return {
            "memory_query_latency_p50": self.metrics.get("p50", 0),
            "memory_query_latency_p95": self.metrics.get("p95", 0),
            "memory_query_latency_p99": self.metrics.get("p99", 0),
            "memory_cache_hit_rate": self.metrics["cache_hit_rate"],
            "memory_error_rate": self.metrics["error_rate"]
        }
```

### 2. Автоматическая оптимизация
```python
# core/memory/auto_optimizer.py
class AutoOptimizer:
    def __init__(self, neo4j_driver, metrics_collector):
        self.driver = neo4j_driver
        self.metrics = metrics_collector
        
    async def analyze_and_optimize(self):
        """Анализирует и оптимизирует производительность"""
        # 1. Анализируем медленные запросы
        slow_queries = await self._get_slow_queries()
        
        for query in slow_queries:
            # 2. Получаем план выполнения
            plan = await self._get_query_plan(query)
            
            # 3. Предлагаем оптимизации
            if "NodeIndexSeek" not in plan:
                await self._suggest_index(query)
                
            if plan["db_hits"] > 100000:
                await self._suggest_query_rewrite(query)
        
        # 4. Анализируем использование индексов
        index_stats = await self._get_index_statistics()
        
        for index in index_stats:
            if index["usage_count"] == 0 and index["age_days"] > 7:
                logger.warning(f"Неиспользуемый индекс: {index['name']}")
```

## 📋 План внедрения

### Фаза 1: Базовые оптимизации (1-2 дня)
1. ✅ Настройка памяти Neo4j
2. ✅ Создание оптимизированных индексов
3. ✅ Внедрение кеширования
4. ✅ Настройка пулов соединений

### Фаза 2: Продвинутые оптимизации (3-5 дней)
1. ⏳ Гибридный поиск
2. ⏳ Батч-обработка
3. ⏳ Предзагрузка данных
4. ⏳ Адаптивные эмбеддинги

### Фаза 3: Мониторинг и тюнинг (ongoing)
1. ⏳ Система метрик
2. ⏳ Автооптимизация
3. ⏳ A/B тестирование
4. ⏳ Обратная связь

## 🎯 Ожидаемые результаты

### Производительность:
- **Latency p50**: 50ms → 20ms (-60%)
- **Latency p95**: 200ms → 80ms (-60%)
- **Throughput**: 100 rps → 500 rps (+400%)

### Качество:
- **Релевантность**: +30% (за счет гибридного поиска)
- **Полнота ответов**: +25% (за счет графовых связей)
- **Персонализация**: +40% (за счет адаптивности)

### Надежность:
- **Uptime**: 99.9%
- **Error rate**: < 0.1%
- **Cache hit rate**: > 60%

## 🚨 Риски и митигация

1. **Риск**: Увеличение сложности
   - **Митигация**: Поэтапное внедрение, тщательное тестирование

2. **Риск**: Рост затрат на инфраструктуру
   - **Митигация**: Оптимизация ресурсов, автоскейлинг

3. **Риск**: Деградация при росте данных
   - **Митигация**: Шардирование, архивация старых данных

## 📚 Дополнительные ресурсы

1. [Neo4j Performance Tuning](https://neo4j.com/docs/operations-manual/current/performance/)
2. [Graphiti Documentation](https://github.com/getzep/graphiti)
3. [Vector Search Best Practices](https://www.pinecone.io/learn/vector-search-best-practices/)
4. [Hybrid Search Techniques](https://arxiv.org/abs/2310.14888)