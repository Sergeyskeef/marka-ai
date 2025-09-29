from __future__ import annotations
import os
import logging
from typing import Any, Optional

from .service import memory_service
from .memory_manager import MemoryManager

logger = logging.getLogger(__name__)

_DEF_FLAG = os.getenv('MARK_MEMORY_FACADE', '1')

def _enabled() -> bool:
    return os.getenv('MARK_MEMORY_FACADE', _DEF_FLAG) in ('1','true','True','yes') and memory_service is not None

# --- wrap add_episode ---
_orig_add = MemoryManager.add_episode
async def _add_episode(self: MemoryManager, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if _enabled():
        try:
            return await memory_service.store(text, meta=metadata, with_embedding=True)
        except Exception as e:
            logger.warning(f'facade add_episode failed, fallback: {e}')
    return await _orig_add(self, text, metadata)
MemoryManager.add_episode = _add_episode  # type: ignore[assignment]

# --- wrap hybrid_search ---
_orig_hs = MemoryManager.hybrid_search
async def _hybrid_search(self: MemoryManager, query: str, user_id: str, k: int = 10,
                         filters: Optional[dict[str, Any]] = None, time_window=None, use_hybrid: bool = True) -> list[dict]:
    if _enabled():
        try:
            return await memory_service.retrieve(query=query, user_id=user_id, k=k, filters=filters)  # type: ignore[arg-type]
        except Exception as e:
            logger.warning(f'facade hybrid_search failed, fallback: {e}')
    return await _orig_hs(self, query=query, user_id=user_id, k=k, filters=filters, time_window=time_window, use_hybrid=use_hybrid)
MemoryManager.hybrid_search = _hybrid_search  # type: ignore[assignment]

logger.info('🔁 Memory facade shim loaded (MARK_MEMORY_FACADE=%s)', os.getenv('MARK_MEMORY_FACADE','1'))
