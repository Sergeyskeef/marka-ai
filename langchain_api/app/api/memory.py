"""
Memory API endpoints (search/save/stats)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from openai import AsyncOpenAI
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from core.memory.graphiti_adapter import GraphitiMemoryAdapter
from app.config import settings
from core.memory.graphiti_adapter import graphiti_adapter
from core.memory.xtrace import get_last_xtrace

logger = logging.getLogger(__name__)

router = APIRouter()

# Request/Response models
class MemorySearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10

class MemoryAddRequest(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = None

class MemoryStatsResponse(BaseModel):
    total_memories: int = 0

class ToolLogItem(BaseModel):
    text: str
    metadata: Dict[str, Any]

class ToolLogsResponse(BaseModel):
    items: List[ToolLogItem]

# Global memory adapter instance
_memory_adapter: Optional[AdvancedMemoryAdapter] = None

def _build_adapter() -> AdvancedMemoryAdapter:
    graphiti = GraphitiMemoryAdapter()
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return AdvancedMemoryAdapter(graphiti_adapter=graphiti, openai_client=client)

async def get_memory_adapter() -> AdvancedMemoryAdapter:
    global _memory_adapter
    if _memory_adapter is None:
        _memory_adapter = _build_adapter()
    return _memory_adapter

@router.post("/search")
async def search_memory(
    request: MemorySearchRequest,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Search episodes via Graphiti full-text search
    """
    try:
        logger.info(f"Searching memory: q='{request.query}', limit={request.limit}")
        result = await adapter.graphiti.search_episodes(
            query=request.query,
            limit=request.limit or 10
        )
        return result
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save")
async def save_memory(
    request: MemoryAddRequest,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Save a memory entry. For now, store as an Episode in Graphiti with provided metadata.
    """
    try:
        logger.info("Saving episode to memory")
        # Save directly via Graphiti to avoid overconstraining the schema
        result = await adapter.graphiti.create_episode(
            text=request.content,
            metadata=request.metadata or {}
        )
        return {"status": "success" if result.get("success") else "error", **result}
    except Exception as e:
        logger.error(f"Error saving memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Return basic memory stats (placeholder without DB aggregation).
    """
    try:
        # Placeholder: could be extended by querying Graphiti for counts
        return MemoryStatsResponse(total_memories=0)
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tool-logs", response_model=ToolLogsResponse)
async def get_tool_logs(limit: int = Query(50, ge=1, le=500)):
    """
    Получить последние события вызовов инструментов из памяти (type=tool_call).
    Требует Graphiti; отдаёт последние N записей в обратном порядке времени.
    """
    try:
        res = await graphiti_adapter.list_episodes(limit=500)
        items: List[ToolLogItem] = []
        for n in res.get("nodes", []):
            props = n.get("properties", {}) or {}
            if props.get("type") == "tool_call":
                text = props.get("text") or props.get("msg") or ""
                items.append(ToolLogItem(text=text, metadata=props))
        # Сортировка по timestamp, затем берём последние limit
        items = sorted(items, key=lambda x: x.metadata.get("timestamp", 0))[-limit:]
        return ToolLogsResponse(items=items)
    except Exception as e:
        logger.error(f"Error getting tool logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/xtrace/last')
async def get_last_memory_xtrace():
    """Вернуть последнюю xtrace по операциям памяти (build_xtrace).
    Полезно для дебага подборки контекста.
    """
    try:
        xt = get_last_xtrace()
        return {"has_xtrace": bool(xt), "xtrace": xt or {}}
    except Exception as e:
        logger.error(f"Error getting xtrace: {e}")
        raise HTTPException(status_code=500, detail=str(e))
