from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging, time

from .graphiti_adapter import graphiti_adapter
from .embeddings import embed_text
from .xtrace import build_xtrace, set_last_xtrace
from .metadata import normalize_metadata

logger = logging.getLogger(__name__)

class MemoryService:
    """Unified facade for memory operations.
    Non-breaking: can be wired gradually.
    """
    def __init__(self):
        pass

    async def pre_store(self, text: str, meta: Optional[dict] = None) -> tuple[str, dict | None]:
        # Redact secrets and normalize shapes/types
        return text, normalize_metadata(meta)

    async def store(self, text: str, *, meta: Optional[dict] = None, with_embedding: bool = True) -> dict:
        text, meta = await self.pre_store(text, meta)
        meta = dict(meta or {})
        if with_embedding:
            try:
                emb = await embed_text(text)
                meta.setdefault('embedding', emb)
            except Exception as e:
                logger.warning(f'Embedding failed: {e}')
        return await graphiti_adapter.create_episode(text, meta)

    async def retrieve(self, query: str, *, user_id: str, k: int = 10, filters: Optional[dict] = None) -> List[dict]:
        # For now, delegate to MemoryManager.hybrid_search equivalent through adapter
        # (keyword search via Graphiti; embeddings used by HybridSearch if present)
        from .hybrid_search import HybridSearchEngine
        engine = HybridSearchEngine(graphiti_adapter)
        try:
            timings: Dict[str, float] = {}
            t0 = time.perf_counter()
            qf = dict(filters or {})
            # Try compute query embedding for better rerank
            try:
                t_emb0 = time.perf_counter()
                emb = await embed_text(query)
                timings['embed_query'] = time.perf_counter() - t_emb0
                qf['query_embedding'] = emb
            except Exception as e:
                logger.info(f'Query embedding not available: {e}')
            t_s0 = time.perf_counter()
            results = await engine.search(query=query, user_id=user_id, k=k, filters=qf)
            timings['search'] = time.perf_counter() - t_s0
            timings['total'] = time.perf_counter() - t0
            dicts = [r.to_dict() for r in results]
            limits = {'top_n_preview': 10}
            set_last_xtrace(build_xtrace(query=query, filters=qf, results=dicts, timings=timings, limits=limits))
            return dicts
        except Exception as e:
            logger.error(f'retrieve failed: {e}')
            return []

    async def health(self) -> dict:
        return await graphiti_adapter.health_check()

# singleton
memory_service = MemoryService()
