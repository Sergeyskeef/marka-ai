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
		resp = await self.graphiti_adapter.search_episodes(query=query, limit=max(k * 3, 10))
		items = resp.get("items", []) if isinstance(resp, dict) else []
		results: List[HybridSearchResult] = []

		# Функции для эмбеддинг-реранка (простейшие, без внешних вызовов)
		def _dot(a: List[float], b: List[float]) -> float:
			return sum(x*y for x, y in zip(a, b))

		def _norm(a: List[float]) -> float:
			import math
			return math.sqrt(sum(x*x for x in a)) or 1.0

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
			emb = metadata.get("embedding")
			if query_emb and isinstance(emb, list) and len(emb) == len(query_emb):
				try:
					emb_score = max(0.0, min(1.0, (_cosine(query_emb, emb) + 1.0) / 2.0))
					final_score = 0.6 * keyword_score + 0.4 * emb_score
				except Exception:
					final_score = keyword_score
			else:
				final_score = keyword_score

			results.append(
				HybridSearchResult(
					id=item.get("id", ""),
					text=item.get("text", ""),
					score=float(final_score),
					source="graphiti",
					metadata=metadata,
				)
			)

		# Сортируем по финальному скору и усечем до k
		results.sort(key=lambda r: r.score, reverse=True)
		return results[:k]