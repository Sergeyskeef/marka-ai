"""
Гибридный поиск для системы памяти
Комбинирует векторный поиск с графовыми запросами для максимальной релевантности
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
import numpy as np

from core.memory.graphiti_adapter import GraphitiMemoryAdapter
from core.memory.graphiti_cache import get_cache

logger = logging.getLogger(__name__)


class SearchResult:
    """Результат поиска с метаданными"""
    def __init__(
        self,
        id: str,
        text: str,
        score: float,
        source: str,  # 'vector', 'graph', 'hybrid'
        metadata: dict = None
    ):
        self.id = id
        self.text = text
        self.score = score
        self.source = source
        self.metadata = metadata or {}
        self.graph_distance = float('inf')
        self.temporal_relevance = 1.0
        self.access_frequency = 0
        
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata,
            "graph_distance": self.graph_distance,
            "temporal_relevance": self.temporal_relevance,
            "access_frequency": self.access_frequency
        }


class HybridSearchEngine:
    """
    Гибридный поисковый движок, комбинирующий:
    1. Векторный поиск (семантическое сходство)
    2. Графовый поиск (структурные связи)
    3. Временной контекст
    4. Персональные предпочтения
    """
    
    def __init__(self, graphiti_adapter: GraphitiMemoryAdapter):
        self.adapter = graphiti_adapter
        self._cache = None
        
        # Веса для комбинирования результатов
        self.weights = {
            "vector_similarity": 0.4,
            "graph_relevance": 0.3,
            "temporal_relevance": 0.2,
            "user_preference": 0.1
        }
        
    async def search(
        self,
        query: str,
        user_id: str,
        k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        time_window: Optional[timedelta] = None
    ) -> List[SearchResult]:
        """
        Выполняет гибридный поиск.
        
        Args:
            query: Поисковый запрос
            user_id: ID пользователя
            k: Количество результатов
            filters: Дополнительные фильтры
            time_window: Временное окно для поиска
            
        Returns:
            Список результатов поиска
        """
        # Проверяем кеш
        cache = await self._get_cache()
        cache_key = {
            "query": query,
            "user_id": user_id,
            "k": k,
            "filters": filters,
            "time_window": str(time_window) if time_window else None
        }
        
        if cache:
            cached = await cache.get("hybrid_search", cache_key)
            if cached:
                logger.debug(f"Гибридный поиск - cache hit для: {query[:50]}...")
                return [SearchResult(**r) for r in cached["result"]]
        
        # 1. Векторный поиск
        vector_results = await self._vector_search(query, k * 2, filters)
        logger.info(f"Векторный поиск нашел {len(vector_results)} результатов")
        
        # 2. Расширение через граф
        graph_expanded = await self._expand_via_graph(vector_results, user_id)
        logger.info(f"Графовое расширение добавило {len(graph_expanded) - len(vector_results)} результатов")
        
        # 3. Временной контекст
        temporal_filtered = await self._apply_temporal_context(
            graph_expanded, 
            time_window
        )
        
        # 4. Получение пользовательских предпочтений
        user_preferences = await self._get_user_preferences(user_id)
        
        # 5. Умное ранжирование
        final_results = await self._smart_rerank(
            temporal_filtered,
            query,
            user_preferences
        )
        
        # Берем топ k результатов
        top_results = final_results[:k]
        
        # Сохраняем в кеш
        if cache:
            await cache.set(
                "hybrid_search",
                cache_key,
                [r.to_dict() for r in top_results],
                ttl=1800  # 30 минут
            )
        
        # Логируем доступ для обучения
        await self._log_access(user_id, query, top_results)
        
        return top_results
    
    async def _vector_search(
        self,
        query: str,
        k: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Выполняет векторный поиск"""
        # Используем существующий метод адаптера
        response = await self.adapter.search_episodes(query, limit=k)
        
        results = []
        for item in response.get("items", []):
            result = SearchResult(
                id=item["id"],
                text=item["text"],
                score=item.get("similarity", 0.8),
                source="vector",
                metadata=item.get("metadata", {})
            )
            results.append(result)
            
        return results
    
    async def _expand_via_graph(
        self,
        initial_results: List[SearchResult],
        user_id: str
    ) -> List[SearchResult]:
        """Расширяет результаты через граф"""
        expanded = list(initial_results)
        seen_ids = {r.id for r in initial_results}
        
        # Для каждого начального результата находим связанные
        for result in initial_results[:5]:  # Берем топ 5 для расширения
            # Запрос связанных узлов (псевдо-Cypher)
            related_query = f"""
            MATCH (e:Episode {{id: '{result.id}'}})-[:MENTIONS]->(entity:Entity)
            MATCH (entity)<-[:MENTIONS]-(related:Episode)
            WHERE related.user_id = '{user_id}' AND related.id <> '{result.id}'
            RETURN related.id, related.msg, count(entity) as shared_entities
            ORDER BY shared_entities DESC
            LIMIT 5
            """
            
            # TODO: Реализовать через GraphitiAdapter.query
            # Пока используем заглушку
            related_results = await self._mock_graph_query(related_query)
            
            for related in related_results:
                if related["id"] not in seen_ids:
                    graph_result = SearchResult(
                        id=related["id"],
                        text=related["msg"],
                        score=result.score * 0.7,  # Понижаем score для графовых
                        source="graph",
                        metadata={"shared_entities": related["shared_entities"]}
                    )
                    graph_result.graph_distance = 1  # Прямая связь
                    expanded.append(graph_result)
                    seen_ids.add(related["id"])
        
        return expanded
    
    async def _apply_temporal_context(
        self,
        results: List[SearchResult],
        time_window: Optional[timedelta] = None
    ) -> List[SearchResult]:
        """Применяет временной контекст к результатам"""
        if not time_window:
            time_window = timedelta(days=30)  # По умолчанию последний месяц
            
        cutoff_time = datetime.now() - time_window
        
        for result in results:
            # Получаем временную метку из метаданных
            created_at = result.metadata.get("created_at")
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at)
                elif isinstance(created_at, (int, float)):
                    created_at = datetime.fromtimestamp(created_at)
                    
                # Вычисляем временную релевантность
                if created_at > cutoff_time:
                    # Линейное убывание от 1.0 до 0.5
                    age_days = (datetime.now() - created_at).days
                    window_days = time_window.days
                    result.temporal_relevance = 1.0 - (0.5 * age_days / window_days)
                else:
                    result.temporal_relevance = 0.5
            
        return results
    
    async def _get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Получает предпочтения пользователя"""
        # TODO: Реализовать через анализ истории
        # Пока возвращаем заглушку
        return {
            "preferred_topics": [],
            "access_patterns": {},
            "time_preferences": {}
        }
    
    async def _smart_rerank(
        self,
        results: List[SearchResult],
        query: str,
        user_preferences: Dict[str, Any]
    ) -> List[SearchResult]:
        """Умное переранжирование результатов"""
        for result in results:
            # Комбинируем все сигналы
            final_score = (
                self.weights["vector_similarity"] * result.score +
                self.weights["graph_relevance"] * (1.0 / (1.0 + result.graph_distance)) +
                self.weights["temporal_relevance"] * result.temporal_relevance +
                self.weights["user_preference"] * self._calculate_user_preference_score(
                    result, user_preferences
                )
            )
            
            result.score = final_score
        
        # Сортируем по финальному score
        results.sort(key=lambda r: r.score, reverse=True)
        
        # Диверсификация результатов
        diversified = self._diversify_results(results)
        
        return diversified
    
    def _calculate_user_preference_score(
        self,
        result: SearchResult,
        user_preferences: Dict[str, Any]
    ) -> float:
        """Вычисляет score на основе предпочтений пользователя"""
        # TODO: Реализовать на основе истории пользователя
        return 0.5  # Базовое значение
    
    def _diversify_results(
        self,
        results: List[SearchResult],
        diversity_threshold: float = 0.8
    ) -> List[SearchResult]:
        """
        Диверсифицирует результаты, чтобы избежать дубликатов.
        Использует простое сравнение текстов.
        """
        diversified = []
        
        for result in results:
            # Проверяем, не слишком ли похож на уже добавленные
            is_diverse = True
            
            for added in diversified:
                similarity = self._text_similarity(result.text, added.text)
                if similarity > diversity_threshold:
                    is_diverse = False
                    break
                    
            if is_diverse:
                diversified.append(result)
                
        return diversified
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Простое сравнение текстов по общим словам"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
            
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    async def _get_cache(self):
        """Получает экземпляр кеша"""
        if self._cache is None and self.adapter.use_cache:
            self._cache = await get_cache()
        return self._cache
    
    async def _log_access(
        self,
        user_id: str,
        query: str,
        results: List[SearchResult]
    ):
        """Логирует доступ для обучения системы"""
        # TODO: Реализовать логирование для анализа
        logger.debug(f"Пользователь {user_id} искал: {query[:50]}...")
    
    async def _mock_graph_query(self, query: str) -> List[Dict[str, Any]]:
        """Временная заглушка для графовых запросов"""
        # TODO: Заменить на реальный GraphitiAdapter.query
        return []
    
    async def update_weights(self, feedback: Dict[str, Any]):
        """
        Обновляет веса на основе обратной связи.
        
        Args:
            feedback: Словарь с информацией о том, какие результаты были полезны
        """
        # TODO: Реализовать адаптивное обучение весов
        pass