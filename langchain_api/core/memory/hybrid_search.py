"""
HybridSearchEngine - минимальная реализация для гибридного поиска по памяти.
Совместима с вызовами из MemoryManager.hybrid_search().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import timedelta


@dataclass
class HybridSearchResult:
    id: str
    text: str
    score: float
    source: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata,
        }


class HybridSearchEngine:
    """Простая реализация гибридного поиска на базе GraphitiAdapter.

    Пока выполняет только полнотекстовый поиск через graphiti_adapter.search_episodes,
    а затем может быть расширена векторной частью и rerank.
    """

    def __init__(self, graphiti_adapter: Any):
        self.graphiti_adapter = graphiti_adapter

    async def search(
        self,
        query: str,
        user_id: str,
        k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        time_window: Optional[timedelta] = None,
    ) -> List[HybridSearchResult]:
        """Выполнить гибридный поиск: keyword (fulltext/LIKE) + простейший эмбеддинг-rerank.

        Этапы:
        1) keyword-кандидаты через GraphitiAdapter.search_episodes
        2) при наличии эмбеддингов в метаданных — косинусное сходство для rerank
        3) усреднение score: 0.6*keyword + 0.4*embedding (если embedding есть)
        """

        resp = await self.graphiti_adapter.search_episodes(
            query=query,
            limit=max(k * 3, 10),
            user_id=user_id,
        )
        items = resp.get("items", []) if isinstance(resp, dict) else []

        metadata_filters: Dict[str, Any] = {}
        if filters:
            if isinstance(filters.get("metadata"), dict):
                metadata_filters.update(filters["metadata"])
            # Поддерживаем прямые алиасы для наиболее частых метаданных
            for key in ("user_id", "type"):
                if key in filters and key not in metadata_filters:
                    metadata_filters[key] = filters[key]

        cutoff_ts: Optional[float] = None
        if time_window:
            try:
                import time

                cutoff_ts = time.time() - time_window.total_seconds()
            except Exception:
                cutoff_ts = None

        results_by_id: Dict[str, HybridSearchResult] = {}

        # Функции для эмбеддинг-реранка (простейшие, без внешних вызовов)
        def _dot(a: List[float], b: List[float]) -> float:
            return sum(x * y for x, y in zip(a, b))

        def _norm(a: List[float]) -> float:
            import math

            return math.sqrt(sum(x * x for x in a)) or 1.0

        def _cosine(a: List[float], b: List[float]) -> float:
            return _dot(a, b) / (_norm(a) * _norm(b))

        # Извлечь эмбеддинг запроса при наличии (ожидается дальнейшая интеграция)
        query_emb: Optional[List[float]] = None
        try:
            # В текущей минимальной версии пропускаем расчет эмбеддинга запроса,
            # предполагая, что он может быть передан в filters["query_embedding"].
            if filters and isinstance(filters.get("query_embedding"), list):
                query_emb = [float(v) for v in filters["query_embedding"]]
        except Exception:
            query_emb = None

        for item in items:
            keyword_score = float(item.get("similarity", 0.8))
            metadata = item.get("metadata", {}) or {}

            # Применяем фильтры по метаданным
            if metadata_filters:
                passed = True
                for key, expected in metadata_filters.items():
                    if expected is None:
                        continue
                    if metadata.get(key) != expected:
                        passed = False
                        break
                if not passed:
                    continue

            # Ограничение по временно́му окну
            if cutoff_ts is not None:
                created_at = metadata.get("created_at")
                created_ts: Optional[float] = None
                if isinstance(created_at, (int, float)):
                    created_ts = float(created_at)
                elif isinstance(created_at, str):
                    try:
                        created_ts = float(created_at)
                    except ValueError:
                        try:
                            from datetime import datetime

                            created_ts = datetime.fromisoformat(created_at).timestamp()
                        except Exception:
                            created_ts = None

                if created_ts is None or created_ts < cutoff_ts:
                    continue

            emb = metadata.get("embedding")
            if query_emb and isinstance(emb, list) and len(emb) == len(query_emb):
                try:
                    emb_score = max(0.0, min(1.0, (_cosine(query_emb, emb) + 1.0) / 2.0))
                    final_score = 0.6 * keyword_score + 0.4 * emb_score
                except Exception:
                    final_score = keyword_score
            else:
                final_score = keyword_score

            item_id = str(item.get("id", ""))
            candidate = HybridSearchResult(
                id=item_id,
                text=item.get("text", ""),
                score=float(final_score),
                source="graphiti",
                metadata=metadata,
            )
            existing = results_by_id.get(item_id)
            if existing is None or candidate.score > existing.score:
                results_by_id[item_id] = candidate

        # Сортируем по финальному скору и усечем до k
        results = list(results_by_id.values())
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]
