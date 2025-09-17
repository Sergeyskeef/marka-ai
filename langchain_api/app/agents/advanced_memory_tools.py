"""
Advanced Memory Tools - инструменты для работы с продвинутой системой памяти
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter, MemoryType
from core.memory.memory_manager import memory_manager
from core.memory.graphiti_adapter import graphiti_adapter
from app.memory.fractal_graph import fractal_graph
from .tools import register_tool, format_tool_result, format_tool_error

logger = logging.getLogger(__name__)

# Инициализируем продвинутый адаптер
advanced_memory = AdvancedMemoryAdapter(graphiti_adapter)


# === ИНСТРУМЕНТЫ ДЛЯ ФАКТОВ ===

@register_tool()
async def remember_fact(
    subject: str,
    predicate: str,
    object: str,
    confidence: float = 0.9
) -> str:
    """
    Запомнить факт в семантической памяти
    
    Args:
        subject: О ком или о чем факт (например: "Пользователь", "Python")
        predicate: Отношение или действие (например: "любит", "является")
        object: Что или кого (например: "программирование", "языком программирования")
        confidence: Уверенность в факте от 0 до 1
    """
    try:
        result = await advanced_memory.save_fact(
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            source="agent_tool"
        )
        
        if result["success"]:
            return json.dumps({
                "success": True,
                "message": f"Факт запомнен: {subject} {predicate} {object}",
                "fact_id": result["id"],
                "confidence": confidence
            }, ensure_ascii=False)
        else:
            return json.dumps(result, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в remember_fact: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def search_facts(
    query: str,
    subject: Optional[str] = None,
    predicate: Optional[str] = None,
    limit: int = 5
) -> str:
    """
    Поиск фактов в семантической памяти
    
    Args:
        query: Поисковый запрос
        subject: Фильтр по субъекту (опционально)
        predicate: Фильтр по предикату (опционально)
        limit: Максимальное количество результатов
    """
    try:
        # Используем базовый поиск с фильтрацией
        results = await memory_manager.search_episodes(query, limit * 2)
        
        facts = []
        for item in results.get("items", []):
            metadata = item.get("metadata", {})
            if metadata.get("type") == MemoryType.FACT.value:
                # Применяем фильтры
                if subject and metadata.get("subject") != subject:
                    continue
                if predicate and metadata.get("predicate") != predicate:
                    continue
                    
                facts.append({
                    "id": metadata.get("id"),
                    "fact": f"{metadata.get('subject')} {metadata.get('predicate')} {metadata.get('object')}",
                    "confidence": metadata.get("confidence", 0),
                    "learned_at": metadata.get("learned_at"),
                    "source": metadata.get("source")
                })
                
                if len(facts) >= limit:
                    break
        
        return json.dumps({
            "found": len(facts),
            "facts": facts
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в search_facts: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# === ИНСТРУМЕНТЫ ДЛЯ ЭПИЗОДОВ ===

@register_tool()
async def record_episode(
    situation: str,
    actions: List[str],
    outcome: str,
    reasoning: str,
    lesson: str = "",
    satisfaction: float = 0.5
) -> str:
    """
    Записать эпизод взаимодействия для последующего анализа
    
    Args:
        situation: Описание ситуации
        actions: Список предпринятых действий
        outcome: Результат (success/failure/partial)
        reasoning: Ход рассуждений
        lesson: Извлеченный урок (опционально)
        satisfaction: Оценка результата от 0 до 1
    """
    try:
        result = await advanced_memory.save_episode(
            situation=situation,
            actions_taken=actions,
            outcome=outcome,
            reasoning=reasoning,
            lesson_learned=lesson,
            satisfaction=satisfaction
        )
        
        if result["success"]:
            return json.dumps({
                "success": True,
                "message": f"Эпизод записан с результатом: {outcome}",
                "episode_id": result["id"],
                "satisfaction": satisfaction
            }, ensure_ascii=False)
        else:
            return json.dumps(result, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в record_episode: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def find_similar_experiences(
    situation: str,
    limit: int = 3
) -> str:
    """
    Найти похожие прошлые опыты для текущей ситуации
    
    Args:
        situation: Описание текущей ситуации
        limit: Количество похожих эпизодов для поиска
    """
    try:
        episodes = await advanced_memory.find_similar_episodes(situation, limit)
        
        formatted_episodes = []
        for ep in episodes:
            metadata = ep.get("metadata", {})
            formatted_episodes.append({
                "situation": metadata.get("situation"),
                "outcome": metadata.get("outcome"),
                "lesson": metadata.get("lesson_learned"),
                "satisfaction": metadata.get("satisfaction", 0),
                "actions": json.loads(metadata.get("actions_taken", "[]"))
            })
        
        return json.dumps({
            "found": len(formatted_episodes),
            "similar_experiences": formatted_episodes,
            "recommendation": "Используй уроки из похожих ситуаций"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в find_similar_experiences: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# === ИНСТРУМЕНТЫ ДЛЯ НАВЫКОВ ===

@register_tool()
async def create_skill(
    name: str,
    triggers: List[str],
    procedure: str,
    prompt: str
) -> str:
    """
    Создать новый навык на основе успешного опыта
    
    Args:
        name: Название навыка (например: "analyze_code")
        triggers: Список триггеров для активации (например: ["анализ кода", "проверь код"])
        procedure: Описание процедуры выполнения
        prompt: Системный промпт для этого навыка
    """
    try:
        result = await advanced_memory.save_skill(
            name=name,
            trigger_patterns=triggers,
            procedure=procedure,
            system_prompt=prompt,
            performance_score=0.7  # Начальная оценка
        )
        
        if result["success"]:
            return json.dumps({
                "success": True,
                "message": f"Навык '{name}' создан",
                "skill_id": result["id"],
                "triggers": triggers
            }, ensure_ascii=False)
        else:
            return json.dumps(result, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в create_skill: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def find_skill_for_task(task: str) -> str:
    """
    Найти подходящий навык для выполнения задачи
    
    Args:
        task: Описание задачи
    """
    try:
        skill = await advanced_memory.get_relevant_skill(task)
        
        if skill:
            metadata = skill.get("metadata", {})
            return json.dumps({
                "found": True,
                "skill": {
                    "name": metadata.get("name"),
                    "procedure": metadata.get("procedure"),
                    "prompt": metadata.get("system_prompt"),
                    "performance": metadata.get("performance_score", 0),
                    "usage_count": metadata.get("usage_count", 0)
                }
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "found": False,
                "message": "Подходящий навык не найден. Используй общий подход."
            }, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в find_skill_for_task: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# === АНАЛИТИЧЕСКИЕ ИНСТРУМЕНТЫ ===

@register_tool()
async def analyze_memory_patterns() -> str:
    """
    Проанализировать паттерны в памяти для самообучения
    """
    try:
        # Получаем последние эпизоды
        recent_episodes = await memory_manager.search_episodes("", limit=20)
        
        # Анализируем результаты
        success_count = 0
        failure_count = 0
        lessons = []
        
        for item in recent_episodes.get("items", []):
            metadata = item.get("metadata", {})
            if metadata.get("type") == MemoryType.EPISODE.value:
                outcome = metadata.get("outcome", "")
                if outcome == "success":
                    success_count += 1
                elif outcome == "failure":
                    failure_count += 1
                
                lesson = metadata.get("lesson_learned")
                if lesson:
                    lessons.append(lesson)
        
        success_rate = success_count / (success_count + failure_count) if (success_count + failure_count) > 0 else 0
        
        return json.dumps({
            "analysis": {
                "total_episodes": success_count + failure_count,
                "success_rate": round(success_rate, 2),
                "successes": success_count,
                "failures": failure_count,
                "recent_lessons": lessons[:5]
            },
            "recommendation": "Фокусируйся на паттернах успешных эпизодов" if success_rate > 0.7 else "Нужно больше учиться на ошибках"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в analyze_memory_patterns: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def get_user_profile(user_id: str) -> str:
    """
    Получить профиль пользователя из всех типов памяти
    
    Args:
        user_id: Идентификатор пользователя
    """
    try:
        # Ищем факты о пользователе
        user_facts = await memory_manager.search_episodes(f"user:{user_id} OR Пользователь", limit=20)
        
        facts = []
        preferences = []
        recent_interactions = []
        
        for item in user_facts.get("items", []):
            metadata = item.get("metadata", {})
            memory_type = metadata.get("type")
            
            if memory_type == MemoryType.FACT.value:
                if metadata.get("subject") == "Пользователь" or user_id in str(metadata.get("subject", "")):
                    facts.append({
                        "fact": f"{metadata.get('subject')} {metadata.get('predicate')} {metadata.get('object')}",
                        "confidence": metadata.get("confidence", 0)
                    })
                    
                    # Выделяем предпочтения
                    if "предпочитает" in metadata.get("predicate", ""):
                        preferences.append(metadata.get("object"))
            
            elif memory_type == MemoryType.EPISODE.value:
                if metadata.get("user_id") == user_id:
                    recent_interactions.append({
                        "situation": metadata.get("situation"),
                        "outcome": metadata.get("outcome"),
                        "date": metadata.get("occurred_at")
                    })
        
        return json.dumps({
            "user_id": user_id,
            "profile": {
                "known_facts": facts[:10],
                "preferences": list(set(preferences)),
                "interaction_count": len(recent_interactions),
                "recent_interactions": recent_interactions[:5]
            }
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в get_user_profile: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# Экспортируем все продвинутые инструменты
ADVANCED_MEMORY_TOOLS = [
    # Факты
    remember_fact,
    search_facts,
    # Эпизоды
    record_episode,
    find_similar_experiences,
    # Навыки
    create_skill,
    find_skill_for_task,
    # Аналитика
    analyze_memory_patterns,
    get_user_profile
]


@register_tool()
async def upsert_graph_node(
    node_id: str,
    node_type: str = "Concept",
    scale: str = "meso",
    payload: Optional[Dict[str, Any]] = None,
    motifs: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None
) -> str:
    """Создать/обновить фрактальный узел (Graphiti) с масштабом и полезной нагрузкой."""
    try:
        result = await fractal_graph.upsert_node(
            node_id=node_id,
            node_type=node_type,
            scale=scale,
            payload=payload or {},
            motifs=motifs or [],
            extra=extra or {}
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps(format_tool_error(e), ensure_ascii=False)

# Добавляем новый инструмент в экспорт
ADVANCED_MEMORY_TOOLS.append(upsert_graph_node)