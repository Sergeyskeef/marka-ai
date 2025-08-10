"""
Chat handler - замена simple_chat на базе OpenAI Agents SDK
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from openai import AsyncOpenAI
from .mark_agent import MarkAgent
from .tools import tool_registry
from .memory_tools import MEMORY_TOOLS
from .advanced_memory_tools import ADVANCED_MEMORY_TOOLS
from .learning_tools import LEARNING_TOOLS
from .vector_search_tools import VECTOR_SEARCH_TOOLS
from .introspection_tools import INTROSPECTION_TOOLS
from .file_tools import FILE_TOOLS
from .test_tools import TEST_TOOLS
from .code_analysis_tools import CODE_ANALYSIS_TOOLS
from .dependency_tools import DEPENDENCY_TOOLS
from core.memory.memory_manager import memory_manager
from ..prompts import PromptSystemFactory
from redis.asyncio import Redis
import asyncio

logger = logging.getLogger(__name__)

# Глобальный экземпляр агента (будет инициализирован позже)
_agent_instance: Optional[MarkAgent] = None
_prompt_system: Optional[dict] = None
_agent_lock = asyncio.Lock()


async def get_agent() -> MarkAgent:
    """Получить или создать экземпляр агента"""
    global _agent_instance, _prompt_system
    
    if _agent_instance is None:
        async with _agent_lock:
            # Двойная проверка после получения блокировки
            if _agent_instance is None:
                # Создаем OpenAI клиент
                client = AsyncOpenAI()
                
                # Создаем систему промптов
                try:
                    from app.config import settings
                    redis_client = None
                    
                    # Пытаемся подключиться к Redis если настроен
                    if settings.REDIS_URL:
                        try:
                            redis_client = Redis.from_url(settings.REDIS_URL)
                            await redis_client.ping()
                            logger.info("✅ Подключен к Redis для системы промптов")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось подключиться к Redis: {e}")
                            redis_client = None
                    
                    # Создаем систему промптов
                    _prompt_system = await PromptSystemFactory.create_system(
                        redis_client=redis_client
                    )
                    
                    # Создаем агента с системой промптов
                    _agent_instance = MarkAgent(
                        client=client,
                        model=settings.OPENAI_MODEL,
                        temperature=settings.OPENAI_TEMPERATURE,
                        max_tokens=settings.OPENAI_MAX_TOKENS,
                        prompt_manager=_prompt_system["manager"],
                        use_dynamic_prompts=True
                    )
                    
                    logger.info("✅ Агент создан с динамической системой промптов")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка создания системы промптов: {e}")
                    logger.info("⚠️ Создаю агента без динамических промптов")
                    
                    # Fallback - создаем агента без системы промптов
                    _agent_instance = MarkAgent(
                        client=client,
                        model=settings.OPENAI_MODEL,
                        temperature=settings.OPENAI_TEMPERATURE,
                        max_tokens=settings.OPENAI_MAX_TOKENS,
                        use_dynamic_prompts=False
                    )
                
                # Регистрируем все инструменты
                all_tools = (MEMORY_TOOLS + ADVANCED_MEMORY_TOOLS + 
                            LEARNING_TOOLS + VECTOR_SEARCH_TOOLS + 
                            INTROSPECTION_TOOLS + FILE_TOOLS + TEST_TOOLS +
                            CODE_ANALYSIS_TOOLS + DEPENDENCY_TOOLS)
                
                for tool in all_tools:
                    definition = tool._openai_tool_definition
                    _agent_instance.register_tool(definition, tool)
                    
                logger.info(f"✅ Агент Марк инициализирован с {len(all_tools)} инструментами")
                
    return _agent_instance


async def enhanced_chat(
    question: str,
    chat_id: Optional[int] = None,
    mode: str = "chat",
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Улучшенная функция чата на базе OpenAI Agents SDK
    
    Полная замена simple_chat с дополнительными возможностями:
    - Автоматический поиск контекста в памяти
    - Использование инструментов
    - Сохранение важной информации
    - Персонализация на основе user_id
    
    Args:
        question: Вопрос пользователя
        chat_id: ID чата
        mode: Режим работы (chat, task, analysis)
        user_id: ID пользователя
        
    Returns:
        Словарь с ответом и метаданными
    """
    try:
        logger.info(f"💬 Новый запрос: '{question[:50]}...' (user={user_id}, mode={mode})")
        
        # Получаем агента
        agent = await get_agent()
        
        # Подготавливаем контекст из памяти
        context = await _prepare_context(question, user_id)
        
        # Вызываем агента
        result = await agent.chat(
            message=question,
            user_id=user_id,
            chat_id=chat_id,
            context=context,
            use_tools=True
        )
        
        # Обрабатываем результат
        response = await _process_result(result, question, user_id)
        
        # Добавляем дополнительные метаданные
        response["metadata"].update({
            "mode": mode,
            "context_used": len(context) > 0,
            "memory_searched": True,
            "tools_available": len(agent.tools)
        })
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка в enhanced_chat: {str(e)}")
        return {
            "content": f"Произошла ошибка при обработке запроса: {str(e)}",
            "error": True,
            "metadata": {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        }


async def _prepare_context(question: str, user_id: Optional[str]) -> List[Dict[str, str]]:
    """Подготовка контекста из памяти"""
    context = []
    
    try:
        # Поиск релевантной информации
        if question.strip():
            # Сначала ищем по вопросу
            search_results = await memory_manager.search_episodes(question, limit=3)
            
            if search_results.get("items"):
                # Добавляем найденную информацию в контекст
                memory_info = "Информация из памяти:\n"
                for item in search_results["items"]:
                    memory_info += f"- {item.get('text', '')}\n"
                
                context.append({
                    "role": "system",
                    "content": f"Используй эту информацию из памяти для персонализации ответа:\n{memory_info}"
                })
                logger.info(f"📚 Добавлено {len(search_results['items'])} элементов из памяти")
        
        # Получаем контекст пользователя если есть user_id
        if user_id:
            user_results = await memory_manager.hybrid_search(
                query=f"user:{user_id}",
                user_id=user_id,
                k=5,
                use_hybrid=True
            )
            
            if user_results:
                user_info = "Информация о пользователе:\n"
                for item in user_results[:3]:  # Берем топ-3
                    user_info += f"- {item.get('text', '')}\n"
                    
                context.append({
                    "role": "system", 
                    "content": f"Контекст пользователя:\n{user_info}"
                })
                logger.info(f"👤 Добавлен контекст пользователя")
                
    except Exception as e:
        logger.error(f"⚠️ Ошибка при подготовке контекста: {str(e)}")
        
    return context


async def _process_result(
    result: Dict[str, Any],
    question: str,
    user_id: Optional[str]
) -> Dict[str, Any]:
    """Обработка результата от агента"""
    
    # Если были вызваны инструменты памяти, логируем
    if result.get("tool_calls"):
        for tool_call in result["tool_calls"]:
            logger.info(f"🔧 Использован инструмент: {tool_call['name']}")
    
    # Автоматически сохраняем диалог в память
    try:
        dialog_text = f"Вопрос: {question}\nОтвет: {result.get('content', '')}"
        metadata = {
            "type": "dialog",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "has_tools": bool(result.get("tool_calls"))
        }
        
        save_result = await memory_manager.save(dialog_text, metadata)
        if save_result.get("success"):
            logger.info(f"💾 Диалог сохранен в память: {save_result.get('id')}")
    except Exception as e:
        logger.error(f"⚠️ Не удалось сохранить диалог: {str(e)}")
    
    return result


async def shutdown_agent():
    """Корректное завершение работы агента и системы промптов"""
    global _agent_instance, _prompt_system
    
    if _prompt_system:
        try:
            await PromptSystemFactory.shutdown_system(_prompt_system)
            logger.info("✅ Система промптов остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки системы промптов: {e}")
        _prompt_system = None
    
    _agent_instance = None
    logger.info("✅ Агент остановлен")


# Функция обратной совместимости с simple_chat
async def simple_chat(
    question: str,
    chat_id: Optional[int] = None,
    mode: str = "chat",
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Обратная совместимость с simple_chat
    
    Эта функция сохранена для совместимости с существующим кодом.
    Внутри использует новый enhanced_chat.
    """
    logger.info("🔄 Вызов simple_chat перенаправлен на enhanced_chat")
    
    result = await enhanced_chat(question, chat_id, mode, user_id)
    
    # Преобразуем результат в старый формат если нужно
    if "content" in result:
        return {
            "answer": result["content"],  # Изменено с "result" на "answer" для совместимости
            "result": result["content"],  # Оставляем и result для обратной совместимости
            "metadata": result.get("metadata", {}),
            "context_used": result.get("metadata", {}).get("context_used", False)
        }
    
    return result