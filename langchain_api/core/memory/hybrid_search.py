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
		"""Выполнить гибридный поиск и вернуть список результатов.

		На текущем этапе: прокси к search_episodes с преобразованием в общий формат.
		"""
		resp = await self.graphiti_adapter.search_episodes(query=query, limit=k)
		items = resp.get("items", []) if isinstance(resp, dict) else []
		results: List[HybridSearchResult] = []
		for item in items:
			results.append(
				HybridSearchResult(
					id=item.get("id", ""),
					text=item.get("text", ""),
					score=float(item.get("similarity", 0.8)),
					source="graphiti",
					metadata=item.get("metadata", {}) or {},
				)
			)
		return results