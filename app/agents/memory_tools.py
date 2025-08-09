"""
Инструменты для работы с памятью Graphiti
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from core.memory.memory_manager import memory_manager
from .tools import register_tool, format_tool_result, format_tool_error

logger = logging.getLogger(__name__)


@register_tool()
async def search_memory(query: str, limit: int = 5) -> str:
    """
    Поиск информации в памяти агента
    
    Args:
        query: Поисковый запрос
        limit: Максимальное количество результатов
        
    Returns:
        JSON с результатами поиска
    """
    try:
        logger.info(f"🔍 Поиск в памяти: '{query}' (limit={limit})")
        
        # Поиск эпизодов
        results = await memory_manager.search_episodes(query, limit)
        
        # Форматируем результаты
        if results.get("items"):
            formatted_items = []
            for item in results["items"]:
                formatted_items.append({
                    "id": item.get("id"),
                    "text": item.get("text"),
                    "similarity": item.get("similarity", 0),
                    "metadata": item.get("metadata", {})
                })
            
            return json.dumps({
                "found": len(formatted_items),
                "items": formatted_items
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "found": 0,
                "items": [],
                "message": "Ничего не найдено"
            }, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка поиска в памяти: {str(e)}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def save_to_memory(text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Сохранение информации в память
    
    Args:
        text: Текст для сохранения
        metadata: Дополнительные метаданные (опционально)
        
    Returns:
        JSON с результатом сохранения
    """
    try:
        logger.info(f"💾 Сохранение в память: '{text[:50]}...'")
        
        # Подготавливаем метаданные
        if metadata is None:
            metadata = {}
            
        metadata.update({
            "source": "agent_tool",
            "timestamp": datetime.now().isoformat(),
            "tool": "save_to_memory"
        })
        
        # Сохраняем
        result = await memory_manager.save(text, metadata)
        
        if result.get("success", True):
            return json.dumps({
                "success": True,
                "id": result.get("id", "unknown"),
                "message": f"Сохранено в память: {result.get('id', 'unknown')}"
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Unknown error")
            }, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения в память: {str(e)}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def get_user_context(user_id: str, limit: int = 10) -> str:
    """
    Получение контекста пользователя из памяти
    
    Args:
        user_id: ID пользователя
        limit: Количество записей для извлечения
        
    Returns:
        JSON с контекстом пользователя
    """
    try:
        logger.info(f"👤 Получение контекста для пользователя: {user_id}")
        
        # Используем гибридный поиск
        results = await memory_manager.hybrid_search(
            query=f"user:{user_id}",
            user_id=user_id,
            k=limit,
            use_hybrid=True
        )
        
        if results:
            # Группируем по типам
            facts = []
            episodes = []
            preferences = []
            
            for item in results:
                text = item.get("text", "")
                metadata = item.get("metadata", {})
                
                # Классифицируем
                if "факт" in text.lower() or "fact" in metadata.get("type", ""):
                    facts.append({
                        "text": text,
                        "confidence": metadata.get("confidence", 0.8)
                    })
                elif "предпочтение" in text.lower() or "preference" in metadata.get("type", ""):
                    preferences.append({
                        "text": text,
                        "category": metadata.get("category", "general")
                    })
                else:
                    episodes.append({
                        "text": text,
                        "timestamp": metadata.get("timestamp"),
                        "score": item.get("score", 0)
                    })
            
            return json.dumps({
                "user_id": user_id,
                "facts": facts,
                "episodes": episodes[-5:],  # Последние 5 эпизодов
                "preferences": preferences,
                "total_items": len(results)
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "user_id": user_id,
                "facts": [],
                "episodes": [],
                "preferences": [],
                "total_items": 0,
                "message": "Контекст пользователя не найден"
            }, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения контекста: {str(e)}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def remember_fact(subject: str, predicate: str, object: str, confidence: float = 0.9) -> str:
    """
    Запомнить факт в структурированном виде
    
    Args:
        subject: Субъект факта (кто/что)
        predicate: Предикат (действие/отношение)
        object: Объект факта (что/кого)
        confidence: Уверенность в факте (0-1)
        
    Returns:
        JSON с результатом сохранения
    """
    try:
        logger.info(f"📝 Запоминание факта: {subject} {predicate} {object}")
        
        # Формируем текст факта
        fact_text = f"{subject} {predicate} {object}"
        
        # Метаданные для факта
        metadata = {
            "type": "fact",
            "subject": subject,
            "predicate": predicate,
            "object": object,
            "confidence": confidence,
            "source": "agent_reasoning",
            "timestamp": datetime.now().isoformat()
        }
        
        # Сохраняем
        result = await memory_manager.save(fact_text, metadata)
        
        if result.get("success", True):
            return json.dumps({
                "success": True,
                "fact": fact_text,
                "id": result.get("id"),
                "message": f"Факт запомнен с уверенностью {confidence}"
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Failed to save fact")
            }, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка запоминания факта: {str(e)}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def check_memory_health() -> str:
    """
    Проверка состояния системы памяти
    
    Returns:
        JSON со статусом памяти
    """
    try:
        logger.info("🏥 Проверка состояния памяти")
        
        # Проверяем здоровье Graphiti
        health = await memory_manager.health_check()
        
        # Получаем статистику
        stats = memory_manager.get_memory_stats()
        
        # Пробуем сделать тестовый поиск
        test_search = await memory_manager.search_episodes("test", limit=1)
        search_ok = not test_search.get("error")
        
        return json.dumps({
            "status": health.get("status", "unknown"),
            "graphiti_healthy": health.get("status") == "healthy",
            "search_functional": search_ok,
            "stats": {
                "total_entries": stats.get("total_entries", 0),
                "memory_types": stats.get("memory_types", [])
            },
            "details": health
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки памяти: {str(e)}")
        return json.dumps({
            "status": "error",
            "graphiti_healthy": False,
            "search_functional": False,
            "error": str(e)
        }, ensure_ascii=False)


# Экспортируем все инструменты памяти
MEMORY_TOOLS = [
    search_memory,
    save_to_memory,
    get_user_context,
    remember_fact,
    check_memory_health
]