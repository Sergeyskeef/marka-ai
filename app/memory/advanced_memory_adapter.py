"""
Advanced Memory Adapter - расширенный адаптер для работы с тремя типами памяти
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from core.memory.graphiti_adapter import GraphitiMemoryAdapter
from .neo4j_direct import neo4j_client
import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Типы памяти"""
    FACT = "Fact"
    EPISODE = "Episode"
    SKILL = "Skill"


class AdvancedMemoryAdapter:
    """
    Расширенный адаптер для работы с продвинутой системой памяти
    Поддерживает три типа памяти: факты, эпизоды, навыки
    """
    
    def __init__(
        self,
        graphiti_adapter: GraphitiMemoryAdapter,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        self.graphiti = graphiti_adapter
        self.openai_client = openai_client or AsyncOpenAI()
        logger.info("🧠 AdvancedMemoryAdapter инициализирован")
    
    # === ФАКТЫ (Семантическая память) ===
    
    async def save_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 0.9,
        source: str = "agent_reasoning",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Сохранить факт в семантическую память
        
        Args:
            subject: Субъект факта (о ком/чем)
            predicate: Предикат (отношение/действие)
            object: Объект факта (что/кого)
            confidence: Уверенность в факте (0-1)
            source: Источник факта
            metadata: Дополнительные метаданные
        """
        try:
            fact_id = f"fact-{uuid.uuid4()}"
            fact_text = f"{subject} {predicate} {object}"
            
            # Получаем embedding
            embedding = await self._get_embedding(fact_text)
            
            # Подготавливаем данные
            fact_data = {
                "id": fact_id,
                "type": MemoryType.FACT.value,
                "subject": subject,
                "predicate": predicate,
                "object": object,
                "confidence": confidence,
                "valid_from": datetime.now().isoformat(),
                "valid_to": None,
                "learned_at": datetime.now().isoformat(),
                "source": source,
                "embedding": embedding,
                "text": fact_text,  # Для совместимости с базовым API
                **(metadata or {})
            }
            
            # Сохраняем через прямой Neo4j
            result = await neo4j_client.create_fact(
                subject=subject,
                predicate=predicate,
                object=object,
                confidence=confidence,
                source=source,
                embedding=embedding,
                metadata=metadata
            )
            
            if result["success"]:
                # Также сохраняем в Graphiti для совместимости
                await self.graphiti.add_episode(
                    text=fact_text,
                    metadata=fact_data
                )
                
                logger.info(f"✅ Факт сохранен: {result['id']} - {fact_text}")
                return {"success": True, "id": result["id"], "fact": fact_text}
            else:
                return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения факта: {e}")
            return {"success": False, "error": str(e)}
    
    async def update_fact_confidence(
        self,
        fact_id: str,
        new_confidence: float,
        reason: str = ""
    ) -> Dict[str, Any]:
        """Обновить уверенность в факте"""
        try:
            # Обновляем через прямой Neo4j клиент
            result = await neo4j_client.update_fact_confidence(
                fact_id=fact_id,
                new_confidence=new_confidence,
                reason=reason
            )
            
            if result["success"]:
                # Создаем эпизод об обновлении для отслеживания
                await self.save_episode(
                    situation=f"Обновление уверенности в факте {fact_id}",
                    actions_taken=["Анализ новых данных", "Корректировка уверенности"],
                    outcome="success",
                    reasoning=reason,
                    lesson_learned=f"Уверенность изменена с ? на {new_confidence}",
                    satisfaction=0.9,
                    metadata={"fact_id": fact_id, "action": "confidence_update"}
                )
                
                logger.info(f"✅ Уверенность факта {fact_id} обновлена: {new_confidence}")
                return result
            else:
                return result
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления уверенности: {e}")
            return {"success": False, "error": str(e)}
    
    async def supersede_fact(
        self,
        old_fact_id: str,
        new_subject: str,
        new_predicate: str,
        new_object: str,
        reason: str
    ) -> Dict[str, Any]:
        """Заменить устаревший факт новым"""
        try:
            # Получаем embedding для нового факта
            new_fact_text = f"{new_subject} {new_predicate} {new_object}"
            embedding = await self._get_embedding(new_fact_text)
            
            # Используем прямой Neo4j для создания связи SUPERSEDES
            new_fact_data = {
                "subject": new_subject,
                "predicate": new_predicate,
                "object": new_object,
                "confidence": 0.9,
                "source": "fact_update",
                "embedding": embedding,
                "reason": reason
            }
            
            result = await neo4j_client.supersede_fact(
                old_fact_id=old_fact_id,
                new_fact_data=new_fact_data
            )
            
            if result["success"]:
                logger.info(f"✅ Факт {old_fact_id} заменен новым")
                
                # Создаем эпизод о замене факта
                await self.save_episode(
                    situation=f"Замена устаревшего факта {old_fact_id}",
                    actions_taken=["Анализ изменений", "Создание нового факта", "Установка связи SUPERSEDES"],
                    outcome="success",
                    reasoning=reason,
                    lesson_learned="Факты могут устаревать и требовать обновления",
                    satisfaction=0.9,
                    metadata={
                        "old_fact_id": old_fact_id,
                        "new_fact_id": result["new_fact"]["id"],
                        "action": "fact_supersede"
                    }
                )
                
                return {
                    "success": True,
                    "id": result["new_fact"]["id"],
                    "old_fact_id": old_fact_id,
                    "fact": f"{new_subject} {new_predicate} {new_object}"
                }
            else:
                return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка замены факта: {e}")
            return {"success": False, "error": str(e)}
    
    # === ЭПИЗОДЫ (Эпизодическая память) ===
    
    async def save_episode(
        self,
        situation: str,
        actions_taken: List[str],
        outcome: str,
        reasoning: str,
        lesson_learned: str = "",
        satisfaction: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Сохранить эпизод в эпизодическую память
        
        Args:
            situation: Описание ситуации
            actions_taken: Список предпринятых действий
            outcome: Результат (success/failure/partial)
            reasoning: Ход рассуждений
            lesson_learned: Извлеченный урок
            satisfaction: Оценка результата (0-1)
            metadata: Дополнительные метаданные
        """
        try:
            episode_id = f"episode-{uuid.uuid4()}"
            episode_text = f"Ситуация: {situation}. Результат: {outcome}. Урок: {lesson_learned}"
            
            # Получаем embedding
            embedding = await self._get_embedding(episode_text)
            
            # Подготавливаем данные
            episode_data = {
                "id": episode_id,
                "type": MemoryType.EPISODE.value,
                "occurred_at": datetime.now().isoformat(),
                "recorded_at": datetime.now().isoformat(),
                "situation": situation,
                "actions_taken": json.dumps(actions_taken, ensure_ascii=False),
                "outcome": outcome,
                "reasoning": reasoning,
                "lesson_learned": lesson_learned,
                "satisfaction": satisfaction,
                "embedding": embedding,
                "text": episode_text,  # Для совместимости
                **(metadata or {})
            }
            
            # Сохраняем через прямой Neo4j
            result = await neo4j_client.create_episode(
                situation=situation,
                actions_taken=actions_taken,
                outcome=outcome,
                reasoning=reasoning,
                lesson_learned=lesson_learned,
                satisfaction=satisfaction,
                embedding=embedding,
                metadata=metadata
            )
            
            if result["success"]:
                # Также сохраняем в Graphiti для совместимости
                await self.graphiti.add_episode(
                    text=episode_text,
                    metadata=episode_data
                )
                
                logger.info(f"✅ Эпизод сохранен: {result['id']}")
                return {"success": True, "id": result["id"], "outcome": outcome}
            else:
                return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения эпизода: {e}")
            return {"success": False, "error": str(e)}
    
    async def find_similar_episodes(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Найти похожие эпизоды"""
        try:
            # Используем базовый поиск
            results = await self.graphiti.search_episodes(query, limit)
            
            # Фильтруем по типу
            episodes = []
            for item in results.get("items", []):
                if item.get("metadata", {}).get("type") == MemoryType.EPISODE.value:
                    episodes.append(item)
            
            return episodes
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска эпизодов: {e}")
            return []
    
    # === НАВЫКИ (Процедурная память) ===
    
    async def save_skill(
        self,
        name: str,
        trigger_patterns: List[str],
        procedure: str,
        system_prompt: str,
        performance_score: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Сохранить навык в процедурную память
        
        Args:
            name: Название навыка
            trigger_patterns: Паттерны для активации
            procedure: Описание процедуры
            system_prompt: Системный промпт для LLM
            performance_score: Начальная оценка эффективности
            metadata: Дополнительные метаданные
        """
        try:
            skill_id = f"skill-{uuid.uuid4()}"
            skill_text = f"Навык: {name}. Процедура: {procedure}"
            
            # Получаем embedding
            embedding = await self._get_embedding(skill_text)
            
            # Подготавливаем данные
            skill_data = {
                "id": skill_id,
                "type": MemoryType.SKILL.value,
                "name": name,
                "trigger_patterns": json.dumps(trigger_patterns, ensure_ascii=False),
                "procedure": procedure,
                "system_prompt": system_prompt,
                "version": 1,
                "performance_score": performance_score,
                "usage_count": 0,
                "created_at": datetime.now().isoformat(),
                "last_used": None,
                "embedding": embedding,
                "text": skill_text,  # Для совместимости
                **(metadata or {})
            }
            
            # Сохраняем через прямой Neo4j
            result = await neo4j_client.create_skill(
                name=name,
                trigger_patterns=trigger_patterns,
                procedure=procedure,
                system_prompt=system_prompt,
                version=1,
                performance_score=performance_score,
                embedding=embedding,
                metadata=metadata
            )
            
            if result["success"]:
                # Также сохраняем в Graphiti для совместимости
                await self.graphiti.add_episode(
                    text=skill_text,
                    metadata=skill_data
                )
                
                logger.info(f"✅ Навык сохранен: {result['id']} - {name}")
                return {"success": True, "id": result["id"], "name": name}
            else:
                return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения навыка: {e}")
            return {"success": False, "error": str(e)}
    
    async def evolve_skill(
        self,
        skill_id: str,
        improved_procedure: str,
        improved_prompt: str,
        performance_improvement: float,
        reason: str
    ) -> Dict[str, Any]:
        """Эволюционировать навык на основе опыта"""
        try:
            # Используем прямой Neo4j клиент для эволюции
            result = await neo4j_client.evolve_skill(
                old_skill_id=skill_id,
                improved_procedure=improved_procedure,
                improved_prompt=improved_prompt,
                performance_improvement=performance_improvement,
                reason=reason
            )
            
            if result["success"]:
                logger.info(f"✅ Навык {skill_id} эволюционировал")
                
                # Создаем эпизод об эволюции навыка
                await self.save_episode(
                    situation=f"Эволюция навыка {result['old_skill'].get('name', skill_id)}",
                    actions_taken=[
                        "Анализ производительности",
                        "Оптимизация процедуры",
                        "Улучшение промпта",
                        "Создание новой версии"
                    ],
                    outcome="success",
                    reasoning=reason,
                    lesson_learned=f"Навыки можно улучшать на основе опыта. Прирост эффективности: {performance_improvement}",
                    satisfaction=0.95,
                    metadata={
                        "old_skill_id": skill_id,
                        "new_skill_id": result["new_skill"]["id"],
                        "improvement": performance_improvement,
                        "action": "skill_evolution"
                    }
                )
                
                return {
                    "success": True,
                    "new_skill_id": result["new_skill"]["id"],
                    "old_skill_id": skill_id,
                    "version": result["new_skill"].get("version", 2),
                    "improvement": performance_improvement
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"❌ Ошибка эволюции навыка: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_relevant_skill(
        self,
        situation: str
    ) -> Optional[Dict[str, Any]]:
        """Найти подходящий навык для ситуации"""
        try:
            # Ищем навыки
            results = await self.graphiti.search_episodes(situation, limit=10)
            
            # Фильтруем навыки
            skills = []
            for item in results.get("items", []):
                if item.get("metadata", {}).get("type") == MemoryType.SKILL.value:
                    skills.append(item)
            
            # Возвращаем самый релевантный
            if skills:
                return skills[0]
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска навыка: {e}")
            return None
    
    # === УТИЛИТЫ ===
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Получить векторное представление текста"""
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"❌ Ошибка получения embedding: {e}")
            # Возвращаем заглушку
            return [0.0] * 1536
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Получить статистику памяти по типам"""
        try:
            # Получаем статистику через прямой Neo4j клиент
            stats = await neo4j_client.get_memory_stats()
            
            return {
                "facts": stats["by_type"].get("Fact", 0),
                "episodes": stats["by_type"].get("Episode", 0),
                "skills": stats["by_type"].get("Skill", 0),
                "total": stats["total"]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                "facts": 0,
                "episodes": 0,
                "skills": 0,
                "total": 0
            }