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
from core.memory.memory_manager import memory_manager

logger = logging.getLogger(__name__)

# Глобальный экземпляр агента (будет инициализирован позже)
_agent_instance: Optional[MarkAgent] = None


async def get_agent() -> MarkAgent:
    """Получить или создать экземпляр агента"""
    global _agent_instance
    
    if _agent_instance is None:
        # Создаем OpenAI клиент
        client = AsyncOpenAI()
        
        # Создаем агента
        _agent_instance = MarkAgent(
            client=client,
            model="gpt-4.1-mini",  # Используем указанную модель!
            temperature=0.7
        )
        
        # Регистрируем инструменты памяти
        for tool in MEMORY_TOOLS:
            definition = tool._openai_tool_definition
            _agent_instance.register_tool(definition, tool)
            
        logger.info("✅ Агент Марк инициализирован с инструментами памяти")
        
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