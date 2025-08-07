"""
Learning Tools - инструменты для самообучения через REAP цикл
"""

import json
import logging
from typing import Optional

from app.learning.reap_cycle import reap_cycle
from .tools import register_tool, format_tool_result, format_tool_error

logger = logging.getLogger(__name__)


@register_tool()
async def start_learning_cycle(
    episode_id: Optional[str] = None,
    auto_mode: bool = False
) -> str:
    """
    Запустить цикл самообучения REAP
    
    Args:
        episode_id: ID конкретного эпизода для анализа (опционально)
        auto_mode: Включить автоматический режим обучения
    """
    try:
        if reap_cycle.is_running:
            return json.dumps({
                "success": False,
                "message": "Цикл обучения уже запущен"
            }, ensure_ascii=False)
        
        logger.info(f"🎓 Запуск REAP цикла (episode: {episode_id}, auto: {auto_mode})")
        
        result = await reap_cycle.run_learning_cycle(
            episode_id=episode_id,
            auto_mode=auto_mode
        )
        
        if result["status"] == "completed":
            return json.dumps({
                "success": True,
                "message": "Цикл обучения завершен",
                "stats": {
                    "patterns_found": result["reflection"]["patterns_found"],
                    "effectiveness": result["reflection"]["effectiveness"],
                    "facts_saved": result["application"]["facts_saved"],
                    "lessons_learned": result["knowledge"]["lessons_learned"]
                }
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "success": False,
                "status": result["status"],
                "reason": result.get("reason", "Unknown")
            }, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в start_learning_cycle: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def reflect_on_recent_experience() -> str:
    """
    Провести рефлексию над недавним опытом
    """
    try:
        # Находим последний эпизод для анализа
        episode_id = await reap_cycle._select_episode_for_learning()
        
        if not episode_id:
            return json.dumps({
                "success": False,
                "message": "Нет подходящих эпизодов для анализа"
            }, ensure_ascii=False)
        
        # Проводим рефлексию
        reflection = await reap_cycle.reflect_on_episode(episode_id)
        
        return json.dumps({
            "success": True,
            "episode_analyzed": episode_id,
            "reflection": {
                "patterns": len(reflection.patterns),
                "effectiveness": reflection.effectiveness,
                "insights": reflection.insights[:3],  # Топ-3
                "recommendations": reflection.recommendations
            }
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в reflect_on_recent_experience: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def get_learning_status() -> str:
    """
    Получить статус системы самообучения
    """
    try:
        # Получаем статистику памяти
        memory_stats = await reap_cycle.memory.get_memory_stats()
        
        # Анализируем последние циклы обучения
        # TODO: Добавить хранение истории циклов
        
        status = {
            "is_running": reap_cycle.is_running,
            "memory_stats": memory_stats,
            "recommendations": []
        }
        
        # Формируем рекомендации
        if memory_stats.get("episodes", 0) > 10:
            status["recommendations"].append("Достаточно эпизодов для глубокого анализа")
        
        if memory_stats.get("facts", 0) < 5:
            status["recommendations"].append("Нужно больше фактов для эффективного обучения")
        
        return json.dumps({
            "success": True,
            "learning_system": status,
            "message": "Система самообучения активна" if reap_cycle.is_running else "Система самообучения в режиме ожидания"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в get_learning_status: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def apply_lesson(lesson: str) -> str:
    """
    Применить конкретный урок к текущей стратегии
    
    Args:
        lesson: Урок для применения
    """
    try:
        # Создаем эпизод обучения
        result = await reap_cycle.memory.save_episode(
            situation="Применение урока пользователя",
            actions_taken=["Получение урока", "Анализ", "Интеграция"],
            outcome="success",
            reasoning="Пользователь предоставил явный урок для обучения",
            lesson_learned=lesson,
            satisfaction=0.9,
            metadata={"source": "user_teaching"}
        )
        
        if result["success"]:
            # Запускаем мини-цикл обучения для этого эпизода
            learning_result = await reap_cycle.run_learning_cycle(
                episode_id=result["id"]
            )
            
            return json.dumps({
                "success": True,
                "message": f"Урок применен: {lesson}",
                "episode_id": result["id"],
                "learning_completed": learning_result["status"] == "completed"
            }, ensure_ascii=False)
        else:
            return json.dumps(result, ensure_ascii=False)
            
    except Exception as e:
        logger.error(f"❌ Ошибка в apply_lesson: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def analyze_performance_trends() -> str:
    """
    Проанализировать тренды производительности для выявления областей улучшения
    """
    try:
        # Получаем последние эпизоды
        recent = await reap_cycle.memory.graphiti.search_episodes("", limit=50)
        
        # Группируем по дням
        daily_stats = {}
        total_success = 0
        total_episodes = 0
        
        for item in recent.get("items", []):
            metadata = item.get("metadata", {})
            if metadata.get("type") == "Episode":
                total_episodes += 1
                
                # Считаем успехи
                if metadata.get("outcome") == "success":
                    total_success += 1
                
                # Группируем по дням
                occurred_at = metadata.get("occurred_at", "")
                if occurred_at:
                    day = occurred_at.split("T")[0]
                    if day not in daily_stats:
                        daily_stats[day] = {"success": 0, "total": 0}
                    
                    daily_stats[day]["total"] += 1
                    if metadata.get("outcome") == "success":
                        daily_stats[day]["success"] += 1
        
        # Рассчитываем общий успех
        overall_success_rate = total_success / total_episodes if total_episodes > 0 else 0
        
        # Находим тренд
        if len(daily_stats) >= 2:
            days = sorted(daily_stats.keys())
            recent_rate = daily_stats[days[-1]]["success"] / daily_stats[days[-1]]["total"] if daily_stats[days[-1]]["total"] > 0 else 0
            older_rate = daily_stats[days[0]]["success"] / daily_stats[days[0]]["total"] if daily_stats[days[0]]["total"] > 0 else 0
            
            if recent_rate > older_rate:
                trend = "improving"
            elif recent_rate < older_rate:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
        
        return json.dumps({
            "success": True,
            "analysis": {
                "total_episodes": total_episodes,
                "overall_success_rate": round(overall_success_rate, 2),
                "trend": trend,
                "daily_breakdown": daily_stats
            },
            "recommendations": [
                "Продолжайте текущую стратегию" if overall_success_rate > 0.7 else "Требуется оптимизация подхода",
                "Изучите неудачные эпизоды для улучшения" if overall_success_rate < 0.7 else "Закрепите успешные паттерны"
            ]
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в analyze_performance_trends: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# Экспортируем инструменты обучения
LEARNING_TOOLS = [
    start_learning_cycle,
    reflect_on_recent_experience,
    get_learning_status,
    apply_lesson,
    analyze_performance_trends
]