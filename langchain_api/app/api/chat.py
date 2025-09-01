"""
Chat API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging

from openai import AsyncOpenAI
from app.agents.mark_agent import MarkAgent
from app.agents.chat_handler import get_agent
from app.config import settings
from app.agents.chat_handler import enhanced_chat

logger = logging.getLogger(__name__)

router = APIRouter()

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    user_id: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
):
    """
    Process a chat message
    """
    try:
        logger.info(f"Processing chat request from user {request.user_id}")
        
        # Route through enhanced_chat to ensure memory search + tool usage
        result = await enhanced_chat(
            question=request.message,
            chat_id=None,
            mode=str((request.context or {}).get("mode", "chat")),
            user_id=request.user_id,
        )
        
        return ChatResponse(
            response=result.get("content", ""),
            session_id=request.session_id or "default",
            metadata=result.get("metadata"),
            tool_calls=result.get("tool_calls")
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/sessions/{user_id}")
async def get_user_sessions(user_id: str):
    """
    Get chat sessions for a user
    """
    try:
        # This would typically fetch from database
        # For now, return a placeholder
        return {
            "user_id": user_id,
            "sessions": []
        }
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/chat/sessions/{session_id}")
async def clear_session(session_id: str):
    """
    Clear a chat session
    """
    try:
        # This would typically clear session from database/cache
        return {"status": "success", "message": f"Session {session_id} cleared"}
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/debug/last")
async def get_last_chat_debug():
    """
    Вернуть подробную отладочную трассировку последнего вызова LLM/инструментов.
    """
    try:
        agent = await get_agent()
        debug = getattr(agent, "_last_debug", None) or {}
        # Гарантируем JSON-сериализацию
        debug_encoded = jsonable_encoder(debug)
        return {
            "has_debug": bool(debug_encoded),
            "debug": debug_encoded,
        }
    except Exception as e:
        logger.error(f"Error fetching last debug: {e}")
        raise HTTPException(status_code=500, detail=str(e))
