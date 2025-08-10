"""
Chat API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from openai import AsyncOpenAI
from app.agents.mark_agent import MarkAgent
from app.config import settings

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

# Global agent instance (in production, you might want to use dependency injection)
agent = None

async def get_agent():
    """Get or create agent instance"""
    global agent
    if agent is None:
        # Create OpenAI client
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # Create agent with the client
        agent = MarkAgent(
            client=client,
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=settings.OPENAI_MAX_TOKENS
        )
    return agent

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent_instance: MarkAgent = Depends(get_agent)
):
    """
    Process a chat message
    """
    try:
        logger.info(f"Processing chat request from user {request.user_id}")
        
        # Process the message through the agent
        result = await agent_instance.chat(
            message=request.message,
            user_id=request.user_id,
            chat_id=None,  # Could be mapped from session_id if needed
            context=None,  # Could be built from request.context
            use_tools=True
        )
        
        return ChatResponse(
            response=result.get("content", ""),
            session_id=request.session_id or "default",
            metadata=result.get("metadata")
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