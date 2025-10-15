"""
Advanced Memory Adapter - расширенный адаптер для работы с тремя типами памяти
"""

import json
import logging
import uuid
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from core.memory.graphiti_adapter import GraphitiMemoryAdapter
from core.memory.graphiti_adapter import graphiti_adapter as default_graphiti_adapter
from .neo4j_direct import neo4j_client
from app.utils import id_generator, IDType
import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Конфигурация из единого места
from app.config import settings

USE_DIRECT_NEO4J = settings.USE_DIRECT_NEO4J
SYNC_TO_GRAPHITI = settings.SYNC_TO_GRAPHITI

logger.info(f"🔧 Конфигурация памяти: USE_DIRECT_NEO4J={USE_DIRECT_NEO4J}, SYNC_TO_GRAPHITI={SYNC_TO_GRAPHITI}")


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
        graphiti_adapter: Optional[GraphitiMemoryAdapter] = None,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        # Позволяем инициализацию без явной передачи адаптера
        self.graphiti = graphiti_adapter or default_graphiti_adapter
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
        Сохранить факт в память (Graphiti-only)
        """
        try:
            fact_id = id_generator.generate(IDType.FACT)
            fact_text = f"{subject} {predicate} {object}"

            embedding = await self._get_embedding(fact_text)

            fact_data = {
                "id": fact_id,
                "type": MemoryType.FACT.value,
                "subject": subject,
                "predicate": predicate,
                "object": object,
                "confidence": confidence,
                "learned_at": datetime.now().isoformat(),
                "source": source,
                "embedding": embedding,
                "text": fact_text,
                **(metadata or {})
            }

            result = await self.graphiti.create_episode(
                text=fact_text,
                metadata=fact_data
            )
            if result.get("success"):
                logger.info(f"✅ Факт сохранен через Graphiti: {fact_id} - {fact_text}")
            else:
                logger.error(f"❌ Ошибка сохранения факта через Graphiti: {result.get('error')}")
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
            # Graphiti-only: логируем изменение уверенности как новый эпизод
            await self.save_episode(
                situation=f"Обновление уверенности в факте {fact_id}",
                actions_taken=["Анализ новых данных", "Корректировка уверенности"],
                outcome="success",
                reasoning=reason,
                lesson_learned=f"Уверенность изменена на {new_confidence}",
                satisfaction=0.9,
                metadata={"fact_id": fact_id, "action": "confidence_update", "new_confidence": new_confidence}
            )
            logger.info(f"✅ (Graphiti) Уверенность факта {fact_id} зафиксирована эпизодом: {new_confidence}")
            return {"success": True, "fact_id": fact_id, "new_confidence": new_confidence}
                
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
            
            # Graphiti-only: логируем замену факта как эпизод
            new_fact_data = {
                "subject": new_subject,
                "predicate": new_predicate,
                "object": new_object,
                "confidence": 0.9,
                "source": "fact_update",
                "embedding": embedding,
                "reason": reason
            }

            await self.save_episode(
                situation=f"Замена устаревшего факта {old_fact_id}",
                actions_taken=["Анализ изменений", "Создание нового факта"],
                outcome="success",
                reasoning=reason,
                lesson_learned="Факты могут устаревать и требовать обновления",
                satisfaction=0.9,
                metadata={
                    "old_fact_id": old_fact_id,
                    "new_fact": new_fact_data,
                    "action": "fact_supersede"
                }
            )
            return {"success": True, "old_fact_id": old_fact_id, "new_fact": new_fact_data}
            
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
        Сохранить эпизод в память (Graphiti-only)
        """
        try:
            episode_id = id_generator.generate(IDType.EPISODE)
            episode_text = f"Ситуация: {situation}. Результат: {outcome}. Урок: {lesson_learned}"

            embedding = await self._get_embedding(episode_text)

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
                "text": episode_text,
                **(metadata or {})
            }

            result = await self.graphiti.create_episode(
                text=episode_text,
                metadata=episode_data
            )
            if result.get("success"):
                logger.info(f"✅ Эпизод сохранен через Graphiti: {episode_id}")
            else:
                logger.error(f"❌ Ошибка сохранения эпизода через Graphiti: {result.get('error')}")
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
        trigger_patterns: Optional[List[str]] = None,
        procedure: str = "",
        system_prompt: str = "",
        performance_score: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Сохранить навык в память (Graphiti-only)
        """
        try:
            skill_id = id_generator.generate(IDType.SKILL)
            skill_text = f"Навык: {name}. Процедура: {procedure}"

            embedding = await self._get_embedding(skill_text)

            serialized_triggers = json.dumps(trigger_patterns or [], ensure_ascii=False)

            skill_data = {
                "id": skill_id,
                "type": MemoryType.SKILL.value,
                "name": name,
                "trigger_patterns": serialized_triggers,
                "procedure": procedure,
                "system_prompt": system_prompt,
                "version": 1,
                "performance_score": performance_score,
                "usage_count": 0,
                "created_at": datetime.now().isoformat(),
                "last_used": None,
                "embedding": embedding,
                "text": skill_text,
                **(metadata or {})
            }

            result = await self.graphiti.create_episode(
                text=skill_text,
                metadata=skill_data
            )
            if result.get("success"):
                logger.info(f"✅ Навык сохранен через Graphiti: {skill_id}")
            else:
                logger.error(f"❌ Ошибка сохранения навыка через Graphiti: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения навыка: {e}")
            return {"success": False, "error": str(e)}

    async def save_project_plan(
        self,
        plan_name: str,
        plan: Dict[str, Any],
        project_description: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Сохранить план проекта как процедурный навык."""

        triggers = [
            f"project_plan::{plan_name}",
            project_description,
            plan.get("description", ""),
        ]
        triggers = [pattern for pattern in triggers if pattern]

        base_metadata = {
            "skill_category": "project_plan",
            "plan": plan,
            "project_description": project_description,
        }
        combined_metadata: Dict[str, Any] = {**base_metadata, **(metadata or {})}

        return await self.save_skill(
            name=f"Project Plan: {plan_name}",
            trigger_patterns=triggers or [plan_name],
            procedure=json.dumps(plan, ensure_ascii=False),
            system_prompt="Use this project plan as guidance for similar future projects.",
            metadata=combined_metadata,
        )

    async def save_code_example(
        self,
        description: str,
        code: str,
        language: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Сохранить пример кода как процедурный навык."""

        triggers = [
            f"code_example::{language}",
            description,
        ]
        triggers = [pattern for pattern in triggers if pattern]

        base_metadata = {
            "skill_category": "code_example",
            "code": code,
            "description": description,
            "language": language,
        }
        combined_metadata: Dict[str, Any] = {**base_metadata, **(metadata or {})}

        prompt_language = language or "unknown language"
        prompt_description = description or "code example"

        return await self.save_skill(
            name=f"Code Example: {prompt_language} :: {prompt_description[:40]}",
            trigger_patterns=triggers or [prompt_description],
            procedure=code,
            system_prompt=(
                f"Reusable {prompt_language} code example generated for: {prompt_description}."
            ),
            metadata=combined_metadata,
        )
    
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

    # --- New upsert & logging APIs ---
    async def upsert_person(self, user_id: str, name: str | None = None, preferences_patch: dict | None = None) -> dict[str, Any]:
        """Создать/обновить реальный узел Person и опционально применить preferences_patch."""
        try:
            node_id = f"person:{user_id}"
            props: dict[str, Any] = {"user_id": user_id}
            if name:
                props["name"] = name
            # Идемпотентное создание/обновление Person
            res = await self.graphiti.upsert_node(node_id=node_id, node_type="Person", properties=props)
            # Частичное обновление preferences
            if preferences_patch:
                await self.graphiti.update_node_properties(node_id=node_id, properties_patch={"preferences": preferences_patch})
            return {"success": True, "id": node_id, "upsert": res}
        except Exception as e:
            logger.error(f"❌ Ошибка upsert_person: {e}")
            return {"success": False, "error": str(e)}

    async def upsert_project(self, project_id: str, name: str | None = None, domains_patch: dict | None = None) -> dict[str, Any]:
        """Создать/обновить реальный узел Project и обновить домены при необходимости."""
        try:
            node_id = f"project:{project_id}"
            props: dict[str, Any] = {"project_id": project_id}
            if name:
                props["name"] = name
            res = await self.graphiti.upsert_node(node_id=node_id, node_type="Project", properties=props)
            if domains_patch:
                await self.graphiti.update_node_properties(node_id=node_id, properties_patch={"domains": domains_patch})
            return {"success": True, "id": node_id, "upsert": res}
        except Exception as e:
            logger.error(f"❌ Ошибка upsert_project: {e}")
            return {"success": False, "error": str(e)}

    async def log_incident(self, kind: str, params: dict | None = None, error: str | None = None, project_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        payload = {
            "type": "incident",
            "kind": kind,
            "params": params or {},
            "error": error,
            "project_id": project_id,
            "user_id": user_id,
            "status": "open"
        }
        text = f"[INCIDENT] kind={kind} error={(error or '')[:140]}"
        return await self.graphiti.create_episode(text=text, metadata=payload)

    async def upsert_skill(self, name: str, recipe: dict, applies_to: dict | None = None) -> dict[str, Any]:
        """Создать/обновить реальный узел Skill с процедурой и привязками."""
        try:
            import re
            key = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()) or "skill"
            node_id = f"skill:{key}"
            props: dict[str, Any] = {
                "name": name,
                "recipe": recipe,
                "applies_to": applies_to or {},
                "version": 1,
                "success_count": 0,
                "last_used": None,
            }
            res = await self.graphiti.upsert_node(node_id=node_id, node_type="Skill", properties=props)
            return {"success": True, "id": node_id, "upsert": res}
        except Exception as e:
            logger.error(f"❌ Ошибка upsert_skill: {e}")
            return {"success": False, "error": str(e)}