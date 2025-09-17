"""
Фрактальный слой работы с графом памяти на базе Graphiti.

Цели:
- Единый интерфейс для узлов разных масштабов (micro/meso/macro)
- Идемпотентные upsert-операции по node_id (через Graphiti upsert_node)
- Связи SUPERSEDES/SUPPORTS/CAUSES с атрибутами масштаба и веса
- Поиск контекста с «зум-вниманием» (scale-aware) с переоценкой по эмбеддингам

Зависимости: core.memory.graphiti_adapter (HTTP клиент к graphiti_service)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from openai import AsyncOpenAI

from core.memory.graphiti_adapter import graphiti_adapter
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FractalNode:
    node_id: str
    node_type: str
    scale: str  # micro|meso|macro
    payload: Dict[str, Any]
    motifs: List[str]


class FractalGraph:
    """Высокоуровневый адаптер фрактальной памяти поверх Graphiti."""

    def __init__(self, openai_client: Optional[AsyncOpenAI] = None) -> None:
        self._openai = openai_client or AsyncOpenAI()
        self._embedding_model = settings.OPENAI_EMBEDDING_MODEL

    async def upsert_node(
        self,
        node_id: str,
        node_type: str,
        scale: str,
        payload: Dict[str, Any] | None = None,
        motifs: List[str] | None = None,
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Создать или обновить узел с масштабом и полезной нагрузкой.

        Сохраняем scale/payload/motifs прямо в properties узла, чтобы не трогать схему Graphiti.
        """
        props: Dict[str, Any] = {
            "scale": scale,
            "payload": payload or {},
            "motifs": motifs or [],
            "updated_at": datetime.now().isoformat(),
            "project_id": settings.PROJECT_ID,
            "group_id": settings.GRAPH_GROUP_ID,
            "type": node_type,
        }
        # Ленивая генерация эмбеддинга для payload.text/msg если есть
        text_for_embed = self._extract_text_for_embedding(props)
        if text_for_embed:
            try:
                props["embedding"] = await self._embed(text_for_embed)
            except Exception as e:
                logger.warning(f"Не удалось построить embedding для узла {node_id}: {e}")

        if extra:
            props.update(extra)

        return await graphiti_adapter.upsert_node(node_id=node_id, node_type=node_type, properties=props)

    async def supersedes(self, new_id: str, old_id: str, scale: str) -> Dict[str, Any]:
        """Задать отношение SUPERSEDES между версиями знаний."""
        return await graphiti_adapter.create_edge(
            source_id=new_id,
            target_id=old_id,
            type="SUPERSEDES",
            properties={"scale": scale, "ts": int(datetime.now().timestamp())}
        )

    async def relate(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        scale: str,
        weight: float | None = None,
        properties: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Создать связь SUPPORTS/CAUSES/DERIVES и пр."""
        props = {"scale": scale, "ts": int(datetime.now().timestamp())}
        if weight is not None:
            props["weight"] = weight
        if properties:
            props.update(properties)
        return await graphiti_adapter.create_edge(
            source_id=source_id, target_id=target_id, type=rel_type, properties=props
        )

    async def retrieve_context(
        self,
        query: str,
        scale: str = "auto",
        k: int = 12,
        prefer_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """«Зум‑внимание»: подобрать k наиболее релевантных узлов под запрос.

        Реализация: используем search_episodes как базовый индекс (есть в сервисе),
        затем фильтруем по scale/типам, и переоцениваем по косинусной близости эмбеддингов.
        Если в item нет embedding — сортируем по длине пересечения токенов как fallback.
        """
        try:
            prefer_types = prefer_types or []
            # 1) считаем эмбеддинг запроса
            q_emb = await self._embed(query)
            # 2) берём кандидатов из эпизодов
            raw = await graphiti_adapter.search_episodes(query=query, limit=max(50, k * 4))
            items = raw.get("items", [])
            # 3) фильтрация по scale/типам (в metadata)
            def _match(it: Dict[str, Any]) -> bool:
                md = it.get("metadata", {}) or {}
                s_ok = (scale == "auto") or (str(md.get("scale") or md.get("payload", {}).get("scale") or "").lower() == str(scale).lower())
                t_ok = (not prefer_types) or (str(md.get("type") or it.get("type") or "") in prefer_types)
                return s_ok and t_ok

            candidates = [it for it in items if _match(it)] or items
            # 4) скоринг
            scored: List[Tuple[float, Dict[str, Any]]] = []
            for it in candidates:
                md = it.get("metadata", {}) or {}
                emb = md.get("embedding") or md.get("payload", {}).get("embedding")
                text = (it.get("text") or "")
                if emb and isinstance(emb, list):
                    score = self._cosine(q_emb, emb)
                else:
                    score = self._token_overlap_score(query, text)
                scored.append((float(score), it))
            scored.sort(key=lambda p: p[0], reverse=True)
            return [it for _, it in scored[:k]]
        except Exception as e:
            logger.error(f"Ошибка retrieve_context: {e}")
            return []

    async def _embed(self, text: str) -> List[float]:  # type: ignore[name-defined]
        resp = await self._openai.embeddings.create(model=self._embedding_model, input=text)
        return list(resp.data[0].embedding)

    def _cosine(self, a: List[float], b: List[float]) -> float:
        import math
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _token_overlap_score(self, a: str, b: str) -> float:
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        if not sa or not sb:
            return 0.0
        inter = len(sa & sb)
        return inter / max(1, min(len(sa), len(sb)))

    def _extract_text_for_embedding(self, props: Dict[str, Any]) -> str:
        # Приоритет: payload.text/msg → type → пусто
        payload = props.get("payload") or {}
        for key in ("text", "msg", "description", "name"):
            if key in payload and isinstance(payload[key], str) and payload[key]:
                return payload[key]
        if isinstance(props.get("type"), str):
            return str(props["type"])[:200]
        return ""


# Глобальный экземпляр
fractal_graph = FractalGraph()


