"""
REAP Learning Cycle - цикл самообучения для агента Марка
Reflect -> Extract -> Apply -> Persist
"""

import logging
import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter, MemoryType
from core.memory.graphiti_adapter import graphiti_adapter
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LearningOutcome(Enum):
    """Результаты обучения"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    SKIP = "skip"


@dataclass
class ReflectionResult:
    """Результат рефлексии"""
    patterns: List[Dict[str, Any]]
    effectiveness: float
    insights: List[str]
    recommendations: List[str]


@dataclass
class KnowledgePackage:
    """Пакет знаний для применения"""
    new_facts: List[Dict[str, Any]]
    skill_updates: List[Dict[str, Any]]
    lessons: List[str]
    confidence: float


class REAPLearningCycle:
    """
    REAP цикл самообучения
    
    Reflect - анализировать прошлый опыт
    Extract - извлекать знания
    Apply - применять новые знания
    Persist - закреплять изменения
    """
    
    def __init__(
        self,
        memory_adapter: AdvancedMemoryAdapter,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        self.memory = memory_adapter
        self.openai = openai_client or AsyncOpenAI()
        self.is_running = False
        logger.info("🔄 REAP Learning Cycle инициализирован")
    
    # === REFLECT (Рефлексия) ===
    
    async def reflect_on_episode(self, episode_id: str) -> ReflectionResult:
        """
        Анализировать конкретный эпизод
        
        Args:
            episode_id: ID эпизода для анализа
        """
        try:
            logger.info(f"🤔 Рефлексия над эпизодом: {episode_id}")
            
            # Получаем эпизод
            episode_data = await self._get_episode_by_id(episode_id)
            if not episode_data:
                return ReflectionResult([], 0, [], ["Эпизод не найден"])
            
            # Находим похожие эпизоды
            similar_episodes = await self.memory.find_similar_episodes(
                episode_data.get("situation", ""),
                limit=5
            )
            
            # Анализируем паттерны
            patterns = await self._analyze_patterns(episode_data, similar_episodes)
            
            # Оцениваем эффективность
            effectiveness = await self._evaluate_effectiveness(episode_data, similar_episodes)
            
            # Генерируем инсайты через LLM
            insights = await self._generate_insights(episode_data, patterns, effectiveness)
            
            # Формируем рекомендации
            recommendations = await self._generate_recommendations(insights, effectiveness)
            
            return ReflectionResult(
                patterns=patterns,
                effectiveness=effectiveness,
                insights=insights,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка рефлексии: {e}")
            return ReflectionResult([], 0, [], [f"Ошибка: {str(e)}"])
    
    async def _analyze_patterns(
        self,
        episode: Dict[str, Any],
        similar_episodes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Анализировать паттерны в эпизодах"""
        patterns = []
        
        # Паттерн успеха/неудачи
        outcomes = [ep.get("metadata", {}).get("outcome") for ep in similar_episodes]
        success_rate = outcomes.count("success") / len(outcomes) if outcomes else 0
        
        patterns.append({
            "type": "outcome_pattern",
            "success_rate": success_rate,
            "total_similar": len(similar_episodes)
        })
        
        # Паттерн действий
        common_actions = self._find_common_actions(episode, similar_episodes)
        if common_actions:
            patterns.append({
                "type": "action_pattern",
                "common_actions": common_actions,
                "frequency": len(common_actions) / 3  # Нормализованная частота
            })
        
        # Временной паттерн
        if similar_episodes:
            time_pattern = self._analyze_time_pattern(similar_episodes)
            patterns.append({
                "type": "temporal_pattern",
                **time_pattern
            })
        
        return patterns
    
    async def _evaluate_effectiveness(
        self,
        episode: Dict[str, Any],
        similar_episodes: List[Dict[str, Any]]
    ) -> float:
        """Оценить эффективность действий"""
        # Базовая оценка из эпизода
        base_score = episode.get("metadata", {}).get("satisfaction", 0.5)
        
        # Сравнение с похожими
        if similar_episodes:
            similar_scores = [
                ep.get("metadata", {}).get("satisfaction", 0.5)
                for ep in similar_episodes
            ]
            avg_similar = sum(similar_scores) / len(similar_scores)
            
            # Если лучше среднего - повышаем оценку
            if base_score > avg_similar:
                effectiveness = min(base_score * 1.2, 1.0)
            else:
                effectiveness = base_score * 0.9
        else:
            effectiveness = base_score
        
        return round(effectiveness, 2)
    
    # === EXTRACT (Извлечение) ===
    
    async def extract_knowledge(
        self,
        reflection: ReflectionResult
    ) -> KnowledgePackage:
        """
        Извлечь знания из рефлексии
        
        Args:
            reflection: Результат рефлексии
        """
        try:
            logger.info("📚 Извлечение знаний из рефлексии")
            
            # Извлекаем факты
            new_facts = await self._extract_facts(reflection)
            
            # Извлекаем улучшения для навыков
            skill_updates = await self._extract_skill_improvements(reflection)
            
            # Извлекаем уроки
            lessons = await self._extract_lessons(reflection)
            
            # Оцениваем уверенность в знаниях
            confidence = self._calculate_knowledge_confidence(
                reflection.effectiveness,
                len(new_facts),
                len(skill_updates)
            )
            
            return KnowledgePackage(
                new_facts=new_facts,
                skill_updates=skill_updates,
                lessons=lessons,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения знаний: {e}")
            return KnowledgePackage([], [], [], 0)
    
    async def _extract_facts(
        self,
        reflection: ReflectionResult
    ) -> List[Dict[str, Any]]:
        """Извлечь новые факты из рефлексии"""
        facts = []
        
        # Из паттернов
        for pattern in reflection.patterns:
            if pattern["type"] == "outcome_pattern" and pattern["success_rate"] > 0.8:
                facts.append({
                    "subject": "Подход",
                    "predicate": "эффективен для",
                    "object": "похожих задач",
                    "confidence": pattern["success_rate"]
                })
        
        # Из инсайтов (используем LLM для структурирования)
        if reflection.insights:
            prompt = f"""
            Извлеки структурированные факты из следующих инсайтов.
            Формат: субъект|предикат|объект|уверенность
            
            Инсайты:
            {chr(10).join(reflection.insights)}
            
            Примеры фактов:
            - Пользователь|предпочитает|краткие ответы|0.9
            - Python|подходит для|анализа данных|0.95
            """
            
            try:
                from app.config import settings
                response = await self.openai.chat.completions.create(
                    model=settings.OPENAI_MODEL or "gpt-5-mini",
                    messages=[{"role": "system", "content": prompt}],
                    temperature=0.3
                )
                
                # Парсим ответ
                lines = response.choices[0].message.content.strip().split('\n')
                for line in lines:
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 4:
                            facts.append({
                                "subject": parts[0].strip(),
                                "predicate": parts[1].strip(),
                                "object": parts[2].strip(),
                                "confidence": float(parts[3].strip())
                            })
            except Exception as e:
                logger.error(f"Ошибка извлечения фактов через LLM: {e}")
        
        return facts
    
    # === APPLY (Применение) ===
    
    async def apply_knowledge(
        self,
        knowledge: KnowledgePackage
    ) -> Dict[str, Any]:
        """
        Применить полученные знания
        
        Args:
            knowledge: Пакет знаний для применения
        """
        try:
            logger.info("🚀 Применение новых знаний")
            
            results = {
                "facts_saved": 0,
                "skills_updated": 0,
                "lessons_applied": 0,
                "errors": []
            }
            
            # Сохраняем новые факты
            for fact in knowledge.new_facts:
                try:
                    result = await self.memory.save_fact(
                        subject=fact["subject"],
                        predicate=fact["predicate"],
                        object=fact["object"],
                        confidence=fact.get("confidence", 0.8),
                        source="reap_learning"
                    )
                    if result["success"]:
                        results["facts_saved"] += 1
                except Exception as e:
                    results["errors"].append(f"Факт: {e}")
            
            # Обновляем навыки
            for update in knowledge.skill_updates:
                try:
                    # Эволюция навыка через memory adapter
                    await self.memory.evolve_skill(
                        skill_name=update.get("name"),
                        improved_procedure=update.get("procedure"),
                        improved_prompt=update.get("prompt", ""),
                        performance_improvement=update.get("improvement", 0.1),
                        reason=update.get("reason", "Улучшено через REAP цикл")
                    )
                    logger.info(f"Навык обновлен: {update.get('name')}")
                    results["skills_updated"] += 1
                except Exception as e:
                    results["errors"].append(f"Навык {update.get('name', 'unknown')}: {e}")
            
            # Применяем уроки (сохраняем как эпизоды обучения)
            for lesson in knowledge.lessons:
                try:
                    await self.memory.save_episode(
                        situation="Обучение через REAP цикл",
                        actions_taken=["Анализ", "Извлечение", "Применение"],
                        outcome="success",
                        reasoning="Автоматическое обучение",
                        lesson_learned=lesson,
                        satisfaction=knowledge.confidence
                    )
                    results["lessons_applied"] += 1
                except Exception as e:
                    results["errors"].append(f"Урок: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения знаний: {e}")
            return {"error": str(e)}
    
    # === PERSIST (Закрепление) ===
    
    async def persist_learnings(self) -> Dict[str, Any]:
        """Закрепить изменения и оптимизировать память"""
        try:
            logger.info("💾 Закрепление изученного")
            
            results = {
                "optimizations": [],
                "archived": 0,
                "indices_updated": False
            }
            
            # Graphiti-only: опускаем прямые оптимизации графа на Neo4j
            results["optimizations"].append("Skipped direct Neo4j optimizations (Graphiti-only mode)")
            
            # Архивация старых данных
            archived_count = await self._archive_old_memories()
            results["archived"] = archived_count
            
            # Обновление статистики
            await self._update_learning_stats()
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка закрепления: {e}")
            return {"error": str(e)}
    
    # === Полный цикл обучения ===
    
    async def run_learning_cycle(
        self,
        episode_id: Optional[str] = None,
        auto_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Запустить полный цикл обучения
        
        Args:
            episode_id: ID конкретного эпизода или None для автоматического выбора
            auto_mode: Автоматический режим обучения
        """
        try:
            logger.info("🎯 Запуск REAP цикла обучения")
            self.is_running = True
            
            # Выбираем эпизод для анализа
            if not episode_id:
                episode_id = await self._select_episode_for_learning()
                if not episode_id:
                    return {"status": "skip", "reason": "Нет подходящих эпизодов"}
            
            # 1. REFLECT - Рефлексия
            reflection = await self.reflect_on_episode(episode_id)
            
            # 2. EXTRACT - Извлечение
            knowledge = await self.extract_knowledge(reflection)
            
            # 3. APPLY - Применение
            apply_results = await self.apply_knowledge(knowledge)
            
            # 4. PERSIST - Закрепление
            persist_results = await self.persist_learnings()
            
            # Результаты цикла
            cycle_results = {
                "status": "completed",
                "episode_id": episode_id,
                "reflection": {
                    "patterns_found": len(reflection.patterns),
                    "effectiveness": reflection.effectiveness,
                    "insights": len(reflection.insights)
                },
                "knowledge": {
                    "facts_extracted": len(knowledge.new_facts),
                    "skills_to_update": len(knowledge.skill_updates),
                    "lessons_learned": len(knowledge.lessons),
                    "confidence": knowledge.confidence
                },
                "application": apply_results,
                "persistence": persist_results,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ REAP цикл завершен: {cycle_results}")
            
            # В автоматическом режиме планируем следующий цикл
            if auto_mode:
                await asyncio.sleep(300)  # Пауза 5 минут
                asyncio.create_task(self.run_learning_cycle(auto_mode=True))
            
            return cycle_results
            
        except Exception as e:
            logger.error(f"❌ Ошибка REAP цикла: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            self.is_running = False
    
    # === Вспомогательные методы ===
    
    async def _get_episode_by_id(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Получить эпизод по ID"""
        from app.memory.neo4j_direct import neo4j_client
        
        # Graphiti-only
        results = await self.memory.graphiti.search_episodes(episode_id, limit=1)
        if results.get("items"):
            return results["items"][0]
        return None
    
    async def _select_episode_for_learning(self) -> Optional[str]:
        """Выбрать эпизод для обучения"""
        # Ищем недавние эпизоды без извлеченных уроков
        recent = await self.memory.graphiti.search_episodes("", limit=10)
        
        for item in recent.get("items", []):
            metadata = item.get("metadata", {})
            if (metadata.get("type") == MemoryType.EPISODE.value and
                not metadata.get("lesson_learned") and
                metadata.get("outcome") in ["success", "failure"]):
                return metadata.get("id")
        
        return None
    
    def _find_common_actions(
        self,
        episode: Dict[str, Any],
        similar_episodes: List[Dict[str, Any]]
    ) -> List[str]:
        """Найти общие действия в эпизодах"""
        from collections import Counter
        
        all_actions = []
        
        # Извлекаем действия из основного эпизода
        episode_actions = episode.get("metadata", {}).get("actions_taken", "[]")
        if isinstance(episode_actions, str):
            try:
                episode_actions = json.loads(episode_actions)
            except:
                episode_actions = []
        all_actions.extend(episode_actions)
        
        # Извлекаем действия из похожих эпизодов
        for ep in similar_episodes:
            actions = ep.get("metadata", {}).get("actions_taken", "[]")
            if isinstance(actions, str):
                try:
                    actions = json.loads(actions)
                except:
                    actions = []
            all_actions.extend(actions)
        
        # Находим частые действия
        if all_actions:
            action_counts = Counter(all_actions)
            # Возвращаем действия, встречающиеся более 2 раз
            common = [action for action, count in action_counts.items() if count > 2]
            logger.info(f"🔍 Найдено {len(common)} общих действий из {len(all_actions)} всего")
            return common
        
        return []
    
    def _analyze_time_pattern(
        self,
        episodes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Анализировать временные паттерны"""
        from collections import Counter
        from datetime import datetime as dt
        
        hours = []
        days = []
        
        for ep in episodes:
            occurred_at = ep.get("metadata", {}).get("occurred_at", "")
            if occurred_at:
                try:
                    # Парсим datetime
                    if isinstance(occurred_at, str):
                        timestamp = dt.fromisoformat(occurred_at.replace('Z', '+00:00'))
                    else:
                        timestamp = occurred_at
                    
                    hours.append(timestamp.hour)
                    days.append(timestamp.weekday())
                except:
                    pass
        
        # Анализируем частоту по часам
        peak_hours = []
        if hours:
            hour_counts = Counter(hours)
            # Топ-3 часа по активности
            peak_hours = [hour for hour, _ in hour_counts.most_common(3)]
        
        # Определяем тренд
        if len(episodes) >= 2:
            # Сравниваем первую и последнюю половину
            mid = len(episodes) // 2
            first_half_success = sum(1 for ep in episodes[:mid] 
                                   if ep.get("metadata", {}).get("outcome") == "success")
            second_half_success = sum(1 for ep in episodes[mid:] 
                                    if ep.get("metadata", {}).get("outcome") == "success")
            
            if second_half_success > first_half_success:
                trend = "improving"
            elif second_half_success < first_half_success:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
        
        # Определяем частоту
        if len(episodes) > 20:
            frequency = "high"
        elif len(episodes) > 5:
            frequency = "moderate"
        else:
            frequency = "low"
        
        return {
            "frequency": frequency,
            "peak_hours": peak_hours,
            "trend": trend,
            "total_episodes": len(episodes)
        }
    
    async def _generate_insights(
        self,
        episode: Dict[str, Any],
        patterns: List[Dict[str, Any]],
        effectiveness: float
    ) -> List[str]:
        """Генерировать инсайты через LLM"""
        prompt = f"""
        Проанализируй эпизод и выдели ключевые инсайты для обучения.
        
        Эпизод:
        - Ситуация: {episode.get('metadata', {}).get('situation')}
        - Результат: {episode.get('metadata', {}).get('outcome')}
        - Эффективность: {effectiveness}
        
        Найденные паттерны:
        {json.dumps(patterns, ensure_ascii=False, indent=2)}
        
        Выдели 3-5 ключевых инсайтов для улучшения работы агента.
        """
        
        try:
            from app.config import settings
            response = await self.openai.chat.completions.create(
                model=settings.OPENAI_MODEL or "gpt-5-mini",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.7
            )
            
            insights = response.choices[0].message.content.strip().split('\n')
            return [i.strip() for i in insights if i.strip()]
            
        except Exception as e:
            logger.error(f"Ошибка генерации инсайтов: {e}")
            return ["Требуется больше данных для анализа"]
    
    async def _generate_recommendations(
        self,
        insights: List[str],
        effectiveness: float
    ) -> List[str]:
        """Генерировать рекомендации на основе инсайтов"""
        if effectiveness > 0.8:
            return ["Продолжать использовать этот подход", "Закрепить успешный паттерн"]
        elif effectiveness > 0.5:
            return ["Оптимизировать подход", "Изучить альтернативные методы"]
        else:
            return ["Пересмотреть стратегию", "Найти новые решения"]
    
    async def _extract_skill_improvements(
        self,
        reflection: ReflectionResult
    ) -> List[Dict[str, Any]]:
        """Извлечь улучшения для навыков"""
        improvements = []
        
        # Анализируем паттерны ошибок для улучшения навыков
        if reflection.patterns:
            for pattern in reflection.patterns:
                if pattern.get("type") == "repeated_error" and pattern.get("count", 0) > 2:
                    # Создаем улучшение для навыка обработки этой ошибки
                    improvements.append({
                        "name": f"handle_{pattern.get('error_type', 'error')}",
                        "procedure": f"При возникновении {pattern.get('error_type')}: {pattern.get('suggested_fix', 'использовать альтернативный подход')}",
                        "prompt": f"Избегать {pattern.get('error_type')} используя проверенные методы",
                        "improvement": 0.2,
                        "reason": f"Обнаружена повторяющаяся ошибка (встречается {pattern.get('count')} раз)"
                    })
        
        # Анализируем успешные паттерны для усиления навыков
        if hasattr(reflection, 'successful_patterns'):
            for pattern in reflection.successful_patterns:
                if pattern.get("success_rate", 0) > 0.8:
                    improvements.append({
                        "name": pattern.get("skill_name", "unknown_skill"),
                        "procedure": pattern.get("refined_procedure", ""),
                        "improvement": pattern.get("success_rate", 0.8) - 0.5,
                        "reason": f"Высокая успешность: {pattern.get('success_rate', 0)*100:.0f}%"
                    })
        
        return improvements
    
    async def _extract_lessons(
        self,
        reflection: ReflectionResult
    ) -> List[str]:
        """Извлечь уроки из рефлексии"""
        lessons = []
        
        # Из рекомендаций
        lessons.extend(reflection.recommendations)
        
        # Из инсайтов
        for insight in reflection.insights[:3]:  # Топ-3 инсайта
            lessons.append(f"Урок: {insight}")
        
        return lessons
    
    def _calculate_knowledge_confidence(
        self,
        effectiveness: float,
        facts_count: int,
        skills_count: int
    ) -> float:
        """Рассчитать уверенность в извлеченных знаниях"""
        base_confidence = effectiveness
        
        # Повышаем уверенность если много фактов
        if facts_count > 3:
            base_confidence = min(base_confidence * 1.1, 1.0)
        
        # Повышаем если есть улучшения навыков
        if skills_count > 0:
            base_confidence = min(base_confidence * 1.05, 1.0)
        
        return round(base_confidence, 2)
    
    async def _archive_old_memories(self) -> int:
        """Архивировать старые воспоминания"""
        try:
            # Graphiti-only: логируем плановую архивацию как эпизод без прямых операций на Neo4j
            archived_count = 0
            await self.memory.save_episode(
                situation="Плановая архивация (Graphiti-only)",
                actions_taken=[
                    "Проверка давности записей",
                    "Планирование архивации"
                ],
                outcome="success",
                reasoning="Архивация через Graphiti-процессы",
                lesson_learned="Поддержание производительности без прямых запросов",
                satisfaction=0.9,
                metadata={"archived_count": archived_count, "action": "memory_archival"}
            )
            return archived_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка архивации: {e}")
            return 0
    
    async def _update_learning_stats(self):
        """Обновить статистику обучения"""
        try:
            # Получаем текущую статистику
            stats = await self.memory.get_memory_stats()
            
            # Сохраняем статистику как факт
            await self.memory.save_fact(
                subject="learning_system",
                predicate="stats_updated",
                object=json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "total_facts": stats.get("facts", 0),
                    "total_episodes": stats.get("episodes", 0),
                    "total_skills": stats.get("skills", 0),
                    "last_cycle": self.stats
                }),
                confidence=1.0,
                source="reap_cycle"
            )
            
            logger.info(f"📊 Статистика обновлена: {stats}")
            
        except Exception as e:
            logger.error(f"Ошибка обновления статистики: {e}")


# Глобальный экземпляр
reap_cycle = REAPLearningCycle(
    AdvancedMemoryAdapter(graphiti_adapter)
)