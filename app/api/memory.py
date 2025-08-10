"""
Memory API endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from app.memory.models import Fact, Episode, Skill, SearchResult
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Request/Response models
class MemorySearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10
    memory_types: Optional[List[str]] = None

class MemoryAddRequest(BaseModel):
    content: str
    memory_type: str  # "fact", "episode", or "skill"
    metadata: Optional[Dict[str, Any]] = None

class MemoryStatsResponse(BaseModel):
    total_facts: int
    total_episodes: int
    total_skills: int
    total_memories: int
    last_updated: Optional[datetime] = None

# Global memory adapter instance
memory_adapter = None

async def get_memory_adapter():
    """Get or create memory adapter instance"""
    global memory_adapter
    if memory_adapter is None:
        # Create GraphitiMemoryAdapter first
        from core.memory.graphiti_adapter import GraphitiMemoryAdapter
        from openai import AsyncOpenAI
        
        graphiti_adapter = GraphitiMemoryAdapter()
        openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Create AdvancedMemoryAdapter with required dependencies
        memory_adapter = AdvancedMemoryAdapter(
            graphiti_adapter=graphiti_adapter,
            openai_client=openai_client
        )
    return memory_adapter

@router.post("/search")
async def search_memory(
    request: MemorySearchRequest,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Search through memories
    """
    try:
        logger.info(f"Searching memory with query: {request.query}")
        
        # For now, we search episodes as the main search method
        # This can be expanded to search other memory types
        results = await adapter.graphiti.search_episodes(
            query=request.query,
            limit=request.limit
        )
        
        # Convert to list format if needed
        if isinstance(results, dict) and "episodes" in results:
            results = results["episodes"]
        
        return {
            "query": request.query,
            "results": results,
            "count": len(results) if isinstance(results, list) else 0
        }
        
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add")
async def add_memory(
    request: MemoryAddRequest,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Add a new memory
    """
    try:
        logger.info(f"Adding {request.memory_type} memory")
        
        if request.memory_type == "fact":
            # Parse fact from content (expecting format: "subject predicate object")
            parts = request.content.split(" ", 2)
            if len(parts) >= 3:
                memory = await adapter.save_fact(
                    subject=parts[0],
                    predicate=parts[1],
                    object=parts[2],
                    metadata=request.metadata
                )
            else:
                raise ValueError("Fact must be in format: 'subject predicate object'")
        elif request.memory_type == "episode":
            memory = await adapter.save_episode(
                content=request.content,
                participants=request.metadata.get("participants", []),
                location=request.metadata.get("location", "unknown"),
                metadata=request.metadata
            )
        elif request.memory_type == "skill":
            memory = await adapter.learn_skill(
                name=request.metadata.get("name", "skill"),
                description=request.content,
                implementation=request.metadata.get("implementation", ""),
                metadata=request.metadata
            )
        else:
            raise ValueError(f"Invalid memory type: {request.memory_type}")
        
        return {
            "status": "success",
            "memory_id": memory.get("id"),
            "memory_type": request.memory_type
        }
        
    except Exception as e:
        logger.error(f"Error adding memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Get memory statistics
    """
    try:
        stats = await adapter.get_memory_stats()
        
        return MemoryStatsResponse(
            total_facts=stats.get("facts", 0),
            total_episodes=stats.get("episodes", 0),
            total_skills=stats.get("skills", 0),
            total_memories=stats.get("total", 0),
            last_updated=stats.get("last_updated")
        )
        
    except Exception as e:
        logger.error(f"Error getting memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recent")
async def get_recent_memories(
    limit: int = Query(10, le=100),
    memory_type: Optional[str] = None,
    adapter: AdvancedMemoryAdapter = Depends(get_memory_adapter)
):
    """
    Get recent memories
    """
    try:
        # For now, return empty list as this method doesn't exist yet
        # TODO: Implement get_recent method in AdvancedMemoryAdapter
        return {
            "memories": [],
            "count": 0,
            "message": "This endpoint is not yet implemented"
        }
        
    except Exception as e:
        logger.error(f"Error getting recent memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))