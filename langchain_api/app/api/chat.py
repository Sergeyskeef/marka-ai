"""
Chat API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
from starlette.responses import StreamingResponse

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


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Стриминговый чат: отдаёт ответ токенами по мере генерации (SSE совместимый поток).
    Примечание: для простоты первая версия без инструментов (tools=false).
    По завершении сохраняет историю в Redis и Graphiti так же, как обычный чат.
    """
    try:
        agent = await get_agent()

        # Подготовим внешний контекст (как в enhanced_chat)
        from app.agents.chat_handler import _prepare_context
        external_context = await _prepare_context(request.message, request.user_id)

        # Подготовим сообщения с динамическим промптом
        if getattr(agent, 'use_dynamic_prompts', False):
            messages = await agent._prepare_messages_dynamic(
                message=request.message,
                context=external_context,
                user_id=request.user_id,
            )
        else:
            messages = [
                {"role": "system", "content": agent.system_prompt},
                *external_context,
                {"role": "user", "content": request.message},
            ]

        async def token_stream():
            import json as _json
            from datetime import datetime as _dt
            # Отправим мета-информацию первым событием
            meta = {
                "model": agent.model,
                "user_id": request.user_id,
                "selected_prompt": getattr(agent, "_last_prompt_name", None),
            }
            yield f"data: {_json.dumps({'type':'meta','meta':meta}, ensure_ascii=False)}\n\n"

            # Стримим токены
            final_text_parts = []
            try:
                # Формируем параметры запроса со стримом
                params = {
                    "model": agent.model,
                    "messages": messages,
                    "stream": True,
                }
                if getattr(agent, "max_tokens", None):
                    params["max_tokens"] = agent.max_tokens
                # Добавляем temperature только если он не равен 1.0
                if getattr(agent, "temperature", None) is not None and float(agent.temperature) != 1.0:
                    params["temperature"] = agent.temperature

                try:
                    stream = await agent.client.chat.completions.create(**params)
                except Exception as _e:
                    _err = str(_e).lower()
                    if "temperature" in _err and ("unsupported" in _err or "unsupported_value" in _err):
                        # Повторяем без temperature
                        params.pop("temperature", None)
                        stream = await agent.client.chat.completions.create(**params)
                    else:
                        raise
                async for chunk in stream:
                    try:
                        choice = chunk.choices[0] if getattr(chunk, 'choices', None) else None
                        delta = getattr(choice, 'delta', None)
                        text = getattr(delta, 'content', None) if delta else None
                        if text:
                            final_text_parts.append(text)
                            yield f"data: {_json.dumps({'type':'token','text':text}, ensure_ascii=False)}\n\n"
                    except Exception:
                        continue
            except Exception as e:
                yield f"data: {_json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

            # Финализация: сохраняем историю и метаданные
            try:
                final_text = "".join(final_text_parts)
                # Если модель не прислала токенов в stream, делаем синхронный запрос и отдаём как 'final'
                if not final_text:
                    try:
                        params_sync = {
                            "model": agent.model,
                            "messages": messages,
                        }
                        if getattr(agent, "max_tokens", None):
                            params_sync["max_tokens"] = agent.max_tokens
                        if getattr(agent, "temperature", None) is not None and float(agent.temperature) != 1.0:
                            params_sync["temperature"] = agent.temperature
                        try:
                            non_stream_resp = await agent.client.chat.completions.create(**params_sync)
                        except Exception as _e2:
                            _err2 = str(_e2).lower()
                            if "temperature" in _err2 and ("unsupported" in _err2 or "unsupported_value" in _err2):
                                params_sync.pop("temperature", None)
                                non_stream_resp = await agent.client.chat.completions.create(**params_sync)
                            else:
                                raise
                        final_text = getattr(non_stream_resp.choices[0].message, 'content', None) or ""
                    except Exception as e:
                        # Сообщаем об ошибке финализации
                        yield f"data: {_json.dumps({'type':'finalize_error','message':str(e)}, ensure_ascii=False)}\n\n"
                        final_text = ""

                # Отправляем финальный текст отдельным событием
                yield f"data: {_json.dumps({'type':'final','text':final_text}, ensure_ascii=False)}\n\n"
                # Обновляем in-memory и Redis
                history_key = request.user_id or "anonymous"
                new_entries = [
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": final_text},
                ]
                user_hist = agent.user_histories.setdefault(history_key, [])
                user_hist.extend(new_entries)
                if len(user_hist) > getattr(agent, '_max_history_per_user', 100):
                    agent.user_histories[history_key] = user_hist[-getattr(agent, '_max_history_per_user', 100):]
                # Persist в Redis, если доступен
                try:
                    await agent._persist_user_history_to_store(history_key, new_entries)
                except Exception:
                    pass

                # Сохраняем в Graphiti (как в enhanced_chat)
                try:
                    from core.memory.graphiti_adapter import graphiti_adapter
                    session_id = str(request.session_id or "stream-" + (request.user_id or "anon"))
                    await graphiti_adapter.create_session(session_id=session_id, user_id=request.user_id)
                    await graphiti_adapter.create_message(
                        session_id=session_id,
                        role="user",
                        text=request.message,
                        metadata={"user_id": request.user_id, "mode": "chat"}
                    )
                    await graphiti_adapter.create_message(
                        session_id=session_id,
                        role="assistant",
                        text=final_text,
                        metadata={"user_id": request.user_id, "mode": "chat", "streamed": True}
                    )
                except Exception:
                    pass

                yield f"data: {_json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {_json.dumps({'type':'finalize_error','message':str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(token_stream(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in chat_stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))
