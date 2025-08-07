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
            
            # Сохраняем через базовый API
            result = await self.graphiti.add_episode(
                text=fact_text,
                metadata=fact_data
            )
            
            logger.info(f"✅ Факт сохранен: {fact_id} - {fact_text}")
            return {"success": True, "id": fact_id, "fact": fact_text}
            
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
        # TODO: Реализовать обновление через Cypher запрос
        pass
    
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
            # Сохраняем новый факт
            new_fact = await self.save_fact(
                subject=new_subject,
                predicate=new_predicate,
                object=new_object,
                source="fact_update",
                metadata={"supersedes": old_fact_id, "reason": reason}
            )
            
            # TODO: Создать связь SUPERSEDES в Neo4j
            # TODO: Установить valid_to для старого факта
            
            return new_fact
            
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
            
            # Сохраняем через базовый API
            result = await self.graphiti.add_episode(
                text=episode_text,
                metadata=episode_data
            )
            
            logger.info(f"✅ Эпизод сохранен: {episode_id}")
            return {"success": True, "id": episode_id, "outcome": outcome}
            
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
            
            # Сохраняем через базовый API
            result = await self.graphiti.add_episode(
                text=skill_text,
                metadata=skill_data
            )
            
            logger.info(f"✅ Навык сохранен: {skill_id} - {name}")
            return {"success": True, "id": skill_id, "name": name}
            
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
        # TODO: Реализовать через Cypher запрос
        # 1. Получить текущий навык
        # 2. Создать новую версию с version+1
        # 3. Создать связь EVOLVED_FROM
        pass
    
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
            # TODO: Реализовать через Cypher запрос
            # MATCH (n) WHERE n:Fact OR n:Episode OR n:Skill
            # RETURN labels(n)[0] as type, count(n) as count
            
            return {
                "facts": 0,
                "episodes": 0,
                "skills": 0,
                "total": 0
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}