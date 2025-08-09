"""
Vector Search Module - векторный поиск для продвинутой памяти
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from openai import AsyncOpenAI
from sklearn.metrics.pairwise import cosine_similarity
import asyncio

logger = logging.getLogger(__name__)


class VectorSearchEngine:
    """
    Движок векторного поиска для Graphiti
    
    Поддерживает:
    - Генерацию embeddings через OpenAI
    - Косинусное сходство для поиска
    - Гибридный поиск (векторный + текстовый)
    - Кеширование embeddings
    """
    
    def __init__(
        self,
        openai_client: Optional[AsyncOpenAI] = None,
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536
    ):
        self.openai = openai_client or AsyncOpenAI()
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self._embedding_cache = {}
        logger.info(f"🔍 VectorSearchEngine инициализирован (model: {embedding_model})")
    
    async def get_embedding(
        self,
        text: str,
        use_cache: bool = True
    ) -> List[float]:
        """
        Получить векторное представление текста
        
        Args:
            text: Текст для векторизации
            use_cache: Использовать кеш
            
        Returns:
            Вектор размерности embedding_dim
        """
        try:
            # Проверяем кеш
            if use_cache and text in self._embedding_cache:
                return self._embedding_cache[text]
            
            # Генерируем embedding
            response = await self.openai.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            
            # Кешируем
            if use_cache and len(self._embedding_cache) < 1000:  # Ограничение кеша
                self._embedding_cache[text] = embedding
            
            return embedding
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации embedding: {e}")
            # Возвращаем случайный вектор как fallback
            return np.random.rand(self.embedding_dim).tolist()
    
    async def get_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Получить embeddings для списка текстов пакетами
        
        Args:
            texts: Список текстов
            batch_size: Размер пакета
            
        Returns:
            Список векторов
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                response = await self.openai.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)
                
            except Exception as e:
                logger.error(f"❌ Ошибка пакетной генерации: {e}")
                # Добавляем случайные векторы для сбойного пакета
                embeddings.extend([
                    np.random.rand(self.embedding_dim).tolist()
                    for _ in batch
                ])
        
        return embeddings
    
    def calculate_similarity(
        self,
        query_embedding: List[float],
        embeddings: List[List[float]]
    ) -> List[float]:
        """
        Рассчитать косинусное сходство
        
        Args:
            query_embedding: Вектор запроса
            embeddings: Список векторов для сравнения
            
        Returns:
            Список оценок сходства
        """
        if not embeddings:
            return []
        
        # Преобразуем в numpy массивы
        query_vec = np.array(query_embedding).reshape(1, -1)
        emb_matrix = np.array(embeddings)
        
        # Рассчитываем косинусное сходство
        similarities = cosine_similarity(query_vec, emb_matrix)[0]
        
        return similarities.tolist()
    
    async def vector_search(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Векторный поиск по кандидатам
        
        Args:
            query: Поисковый запрос
            candidates: Список кандидатов с полем 'embedding'
            top_k: Количество результатов
            threshold: Порог сходства
            
        Returns:
            Отсортированный список результатов
        """
        try:
            # Получаем embedding запроса
            query_embedding = await self.get_embedding(query)
            
            # Извлекаем embeddings кандидатов
            candidate_embeddings = []
            valid_candidates = []
            
            for candidate in candidates:
                embedding = candidate.get("embedding") or candidate.get("metadata", {}).get("embedding")
                if embedding and len(embedding) == self.embedding_dim:
                    candidate_embeddings.append(embedding)
                    valid_candidates.append(candidate)
            
            if not candidate_embeddings:
                logger.warning("⚠️ Нет кандидатов с валидными embeddings")
                return []
            
            # Рассчитываем сходство
            similarities = self.calculate_similarity(query_embedding, candidate_embeddings)
            
            # Создаем результаты с оценками
            results = []
            for i, (candidate, similarity) in enumerate(zip(valid_candidates, similarities)):
                if similarity >= threshold:
                    result = candidate.copy()
                    result["similarity_score"] = float(similarity)
                    result["rank"] = i + 1
                    results.append(result)
            
            # Сортируем по сходству
            results.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            # Возвращаем топ-K
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"❌ Ошибка векторного поиска: {e}")
            return []
    
    async def hybrid_search(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        text_field: str = "text",
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Гибридный поиск (векторный + текстовый)
        
        Args:
            query: Поисковый запрос
            candidates: Список кандидатов
            text_field: Поле для текстового поиска
            vector_weight: Вес векторного поиска
            text_weight: Вес текстового поиска
            top_k: Количество результатов
            
        Returns:
            Результаты с комбинированным скором
        """
        try:
            # Векторный поиск
            vector_results = await self.vector_search(
                query, 
                candidates, 
                top_k=len(candidates),  # Берем все для последующего ранжирования
                threshold=0.0
            )
            
            # Создаем словарь для быстрого доступа
            vector_scores = {
                self._get_candidate_id(r): r["similarity_score"]
                for r in vector_results
            }
            
            # Текстовый поиск (простое вхождение)
            query_lower = query.lower()
            text_scores = {}
            
            for candidate in candidates:
                text = candidate.get(text_field, "") or candidate.get("metadata", {}).get(text_field, "")
                if text:
                    text_lower = text.lower()
                    # Простая оценка на основе вхождения слов
                    score = sum(1 for word in query_lower.split() if word in text_lower)
                    score = min(score / len(query_lower.split()), 1.0)  # Нормализация
                    text_scores[self._get_candidate_id(candidate)] = score
            
            # Комбинируем оценки
            combined_results = []
            
            for candidate in candidates:
                cand_id = self._get_candidate_id(candidate)
                
                vector_score = vector_scores.get(cand_id, 0.0)
                text_score = text_scores.get(cand_id, 0.0)
                
                # Взвешенная сумма
                combined_score = (
                    vector_weight * vector_score +
                    text_weight * text_score
                )
                
                if combined_score > 0:
                    result = candidate.copy()
                    result["hybrid_score"] = float(combined_score)
                    result["vector_score"] = float(vector_score)
                    result["text_score"] = float(text_score)
                    combined_results.append(result)
            
            # Сортируем по комбинированному скору
            combined_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
            
            return combined_results[:top_k]
            
        except Exception as e:
            logger.error(f"❌ Ошибка гибридного поиска: {e}")
            return []
    
    async def find_similar(
        self,
        reference_embedding: List[float],
        candidates: List[Dict[str, Any]],
        top_k: int = 5,
        exclude_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Найти похожие элементы по embedding
        
        Args:
            reference_embedding: Эталонный вектор
            candidates: Список кандидатов
            top_k: Количество результатов
            exclude_ids: ID для исключения
            
        Returns:
            Похожие элементы
        """
        exclude_ids = exclude_ids or []
        
        # Фильтруем кандидатов
        filtered_candidates = [
            c for c in candidates
            if self._get_candidate_id(c) not in exclude_ids
        ]
        
        # Извлекаем embeddings
        candidate_embeddings = []
        valid_candidates = []
        
        for candidate in filtered_candidates:
            embedding = candidate.get("embedding") or candidate.get("metadata", {}).get("embedding")
            if embedding and len(embedding) == self.embedding_dim:
                candidate_embeddings.append(embedding)
                valid_candidates.append(candidate)
        
        if not candidate_embeddings:
            return []
        
        # Рассчитываем сходство
        similarities = self.calculate_similarity(reference_embedding, candidate_embeddings)
        
        # Создаем результаты
        results = []
        for candidate, similarity in zip(valid_candidates, similarities):
            result = candidate.copy()
            result["similarity_score"] = float(similarity)
            results.append(result)
        
        # Сортируем и возвращаем топ-K
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_k]
    
    def _get_candidate_id(self, candidate: Dict[str, Any]) -> str:
        """Получить ID кандидата"""
        return (
            candidate.get("id") or
            candidate.get("metadata", {}).get("id") or
            str(hash(str(candidate)))
        )
    
    async def update_embeddings(
        self,
        items: List[Dict[str, Any]],
        text_field: str = "text",
        force_update: bool = False
    ) -> int:
        """
        Обновить embeddings для списка элементов
        
        Args:
            items: Элементы для обновления
            text_field: Поле с текстом
            force_update: Принудительное обновление
            
        Returns:
            Количество обновленных элементов
        """
        updated = 0
        
        for item in items:
            # Проверяем, нужно ли обновление
            if not force_update and item.get("embedding"):
                continue
            
            # Извлекаем текст
            text = item.get(text_field) or item.get("metadata", {}).get(text_field)
            if not text:
                continue
            
            try:
                # Генерируем embedding
                embedding = await self.get_embedding(text)
                
                # Обновляем элемент
                if "metadata" in item:
                    item["metadata"]["embedding"] = embedding
                else:
                    item["embedding"] = embedding
                
                updated += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка обновления embedding: {e}")
        
        logger.info(f"✅ Обновлено embeddings: {updated}/{len(items)}")
        return updated


# Глобальный экземпляр
vector_search_engine = VectorSearchEngine()