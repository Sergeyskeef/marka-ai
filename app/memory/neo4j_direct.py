"""
Neo4j Direct Client - прямая работа с графовой базой данных
"""

import logging
import uuid
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
from neo4j import AsyncGraphDatabase
import os

logger = logging.getLogger(__name__)


class Neo4jDirectClient:
    """
    Клиент для прямой работы с Neo4j
    Реализует все операции с типизированными узлами (Fact, Episode, Skill)
    """
    
    def __init__(
        self,
        uri: str = None,
        username: str = None,
        password: str = None
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://graphiti-neo4j:7687")
        self.username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        self._connect_lock = asyncio.Lock()
        logger.info(f"🔌 Neo4jDirectClient инициализирован для {self.uri}")
    
    async def connect(self):
        """Подключение к Neo4j"""
        async with self._connect_lock:
            if not self.driver:
                try:
                    self.driver = AsyncGraphDatabase.driver(
                        self.uri,
                        auth=(self.username, self.password)
                    )
                    # Проверяем подключение
                    async with self.driver.session() as session:
                        await session.run("RETURN 1")
                    logger.info("✅ Подключено к Neo4j")
                except Exception as e:
                    logger.error(f"❌ Ошибка подключения к Neo4j: {e}")
                    raise
    
    async def close(self):
        """Закрыть подключение"""
        if self.driver:
            await self.driver.close()
            self.driver = None
    
    async def _ensure_connected(self):
        """Убедиться что подключение активно"""
        if not self.driver:
            await self.connect()
    
    # === ОПЕРАЦИИ С ФАКТАМИ ===
    
    async def create_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 0.9,
        source: str = "agent",
        embedding: List[float] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Создать новый факт"""
        await self._ensure_connected()
        
        fact_id = f"fact-{uuid.uuid4()}"
        query = """
        CREATE (f:Fact {
            id: $id,
            subject: $subject,
            predicate: $predicate,
            object: $object,
            confidence: $confidence,
            valid_from: datetime(),
            valid_to: null,
            learned_at: datetime(),
            source: $source,
            embedding: $embedding,
            metadata: $metadata
        })
        RETURN f
        """
        
        params = {
            "id": fact_id,
            "subject": subject,
            "predicate": predicate,
            "object": object,
            "confidence": confidence,
            "source": source,
            "embedding": embedding or [],
            "metadata": json.dumps(metadata or {})
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                fact_node = dict(record["f"])
                logger.info(f"✅ Создан факт: {fact_id}")
                return {
                    "success": True,
                    "id": fact_id,
                    "fact": fact_node
                }
            
        return {"success": False, "error": "Failed to create fact"}
    
    async def update_fact_confidence(
        self,
        fact_id: str,
        new_confidence: float,
        reason: str = ""
    ) -> Dict[str, Any]:
        """Обновить уверенность в факте"""
        await self._ensure_connected()
        
        query = """
        MATCH (f:Fact {id: $fact_id})
        SET f.confidence = $new_confidence,
            f.confidence_updated_at = datetime(),
            f.confidence_update_reason = $reason
        RETURN f
        """
        
        params = {
            "fact_id": fact_id,
            "new_confidence": new_confidence,
            "reason": reason
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                fact_node = dict(record["f"])
                logger.info(f"✅ Обновлена уверенность факта {fact_id}: {new_confidence}")
                return {
                    "success": True,
                    "fact": fact_node
                }
            
        return {"success": False, "error": f"Fact {fact_id} not found"}
    
    async def supersede_fact(
        self,
        old_fact_id: str,
        new_fact_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Заменить устаревший факт новым"""
        await self._ensure_connected()
        
        new_fact_id = f"fact-{uuid.uuid4()}"
        query = """
        MATCH (old:Fact {id: $old_id})
        CREATE (new:Fact {
            id: $new_id,
            subject: $subject,
            predicate: $predicate,
            object: $object,
            confidence: $confidence,
            valid_from: datetime(),
            valid_to: null,
            learned_at: datetime(),
            source: $source,
            embedding: $embedding
        })
        SET old.valid_to = datetime()
        CREATE (new)-[:SUPERSEDES {
            reason: $reason,
            timestamp: datetime()
        }]->(old)
        RETURN new, old
        """
        
        params = {
            "old_id": old_fact_id,
            "new_id": new_fact_id,
            **new_fact_data
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                new_fact = dict(record["new"])
                old_fact = dict(record["old"])
                logger.info(f"✅ Факт {old_fact_id} заменен на {new_fact_id}")
                return {
                    "success": True,
                    "new_fact": new_fact,
                    "old_fact": old_fact
                }
                
        return {"success": False, "error": f"Failed to supersede fact {old_fact_id}"}
    
    # === ОПЕРАЦИИ С ЭПИЗОДАМИ ===
    
    async def create_episode(
        self,
        situation: str,
        actions_taken: List[str],
        outcome: str,
        reasoning: str,
        lesson_learned: str = "",
        satisfaction: float = 0.5,
        embedding: List[float] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Создать новый эпизод"""
        await self._ensure_connected()
        
        episode_id = f"episode-{uuid.uuid4()}"
        query = """
        CREATE (e:Episode {
            id: $id,
            occurred_at: datetime(),
            recorded_at: datetime(),
            situation: $situation,
            actions_taken: $actions_taken,
            outcome: $outcome,
            reasoning: $reasoning,
            lesson_learned: $lesson_learned,
            satisfaction: $satisfaction,
            embedding: $embedding,
            metadata: $metadata
        })
        RETURN e
        """
        
        params = {
            "id": episode_id,
            "situation": situation,
            "actions_taken": json.dumps(actions_taken, ensure_ascii=False),
            "outcome": outcome,
            "reasoning": reasoning,
            "lesson_learned": lesson_learned,
            "satisfaction": satisfaction,
            "embedding": embedding or [],
            "metadata": json.dumps(metadata or {})
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                episode_node = dict(record["e"])
                logger.info(f"✅ Создан эпизод: {episode_id}")
                return {
                    "success": True,
                    "id": episode_id,
                    "episode": episode_node
                }
            
        return {"success": False, "error": "Failed to create episode"}
    
    async def link_episode_to_fact(
        self,
        episode_id: str,
        fact_id: str,
        relationship_type: str = "USED_FACT"
    ) -> bool:
        """Связать эпизод с фактом"""
        await self._ensure_connected()
        
        query = f"""
        MATCH (e:Episode {{id: $episode_id}})
        MATCH (f:Fact {{id: $fact_id}})
        CREATE (e)-[:{relationship_type} {{timestamp: datetime()}}]->(f)
        RETURN e, f
        """
        
        params = {
            "episode_id": episode_id,
            "fact_id": fact_id
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                logger.info(f"✅ Связаны эпизод {episode_id} и факт {fact_id}")
                return True
                
        return False
    
    # === ОПЕРАЦИИ С НАВЫКАМИ ===
    
    async def create_skill(
        self,
        name: str,
        trigger_patterns: List[str],
        procedure: str,
        system_prompt: str,
        version: int = 1,
        performance_score: float = 0.5,
        embedding: List[float] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Создать новый навык"""
        await self._ensure_connected()
        
        skill_id = f"skill-{uuid.uuid4()}"
        query = """
        CREATE (s:Skill {
            id: $id,
            name: $name,
            trigger_patterns: $trigger_patterns,
            procedure: $procedure,
            system_prompt: $system_prompt,
            version: $version,
            performance_score: $performance_score,
            usage_count: 0,
            created_at: datetime(),
            last_used: null,
            embedding: $embedding,
            metadata: $metadata
        })
        RETURN s
        """
        
        params = {
            "id": skill_id,
            "name": name,
            "trigger_patterns": json.dumps(trigger_patterns, ensure_ascii=False),
            "procedure": procedure,
            "system_prompt": system_prompt,
            "version": version,
            "performance_score": performance_score,
            "embedding": embedding or [],
            "metadata": json.dumps(metadata or {})
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                skill_node = dict(record["s"])
                logger.info(f"✅ Создан навык: {skill_id} - {name}")
                return {
                    "success": True,
                    "id": skill_id,
                    "skill": skill_node
                }
            
        return {"success": False, "error": "Failed to create skill"}
    
    async def evolve_skill(
        self,
        old_skill_id: str,
        improved_procedure: str,
        improved_prompt: str,
        performance_improvement: float,
        reason: str
    ) -> Dict[str, Any]:
        """Эволюционировать навык"""
        await self._ensure_connected()
        
        # Сначала получаем старый навык
        get_query = """
        MATCH (old:Skill {id: $old_id})
        RETURN old
        """
        
        async with self.driver.session() as session:
            result = await session.run(get_query, {"old_id": old_skill_id})
            record = await result.single()
            
            if not record:
                return {"success": False, "error": f"Skill {old_skill_id} not found"}
            
            old_skill = dict(record["old"])
            
            # Создаем новую версию
            new_skill_id = f"skill-{uuid.uuid4()}"
            evolve_query = """
            MATCH (old:Skill {id: $old_id})
            CREATE (new:Skill {
                id: $new_id,
                name: old.name,
                trigger_patterns: old.trigger_patterns,
                procedure: $improved_procedure,
                system_prompt: $improved_prompt,
                version: old.version + 1,
                performance_score: old.performance_score + $performance_improvement,
                usage_count: 0,
                created_at: datetime(),
                last_used: null,
                embedding: old.embedding,
                evolved_from: $old_id
            })
            CREATE (new)-[:EVOLVED_FROM {
                reason: $reason,
                improvement: $performance_improvement,
                timestamp: datetime()
            }]->(old)
            RETURN new, old
            """
            
            params = {
                "old_id": old_skill_id,
                "new_id": new_skill_id,
                "improved_procedure": improved_procedure,
                "improved_prompt": improved_prompt,
                "performance_improvement": performance_improvement,
                "reason": reason
            }
            
            result = await session.run(evolve_query, params)
            record = await result.single()
            
            if record:
                new_skill = dict(record["new"])
                logger.info(f"✅ Навык {old_skill_id} эволюционировал в {new_skill_id}")
                return {
                    "success": True,
                    "new_skill": new_skill,
                    "old_skill": old_skill,
                    "improvement": performance_improvement
                }
                
        return {"success": False, "error": "Failed to evolve skill"}
    
    async def update_skill_usage(
        self,
        skill_id: str,
        performance_rating: float
    ) -> bool:
        """Обновить статистику использования навыка"""
        await self._ensure_connected()
        
        query = """
        MATCH (s:Skill {id: $skill_id})
        SET s.usage_count = s.usage_count + 1,
            s.last_used = datetime(),
            s.performance_score = (s.performance_score * s.usage_count + $rating) / (s.usage_count + 1)
        RETURN s
        """
        
        params = {
            "skill_id": skill_id,
            "rating": performance_rating
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                logger.info(f"✅ Обновлена статистика навыка {skill_id}")
                return True
                
        return False
    
    # === ПОИСКОВЫЕ ОПЕРАЦИИ ===
    
    async def get_node_by_id(
        self,
        node_id: str,
        node_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Получить узел по ID"""
        await self._ensure_connected()
        
        if node_type:
            query = f"MATCH (n:{node_type} {{id: $id}}) RETURN n"
        else:
            query = "MATCH (n {id: $id}) RETURN n"
        
        async with self.driver.session() as session:
            result = await session.run(query, {"id": node_id})
            record = await result.single()
            
            if record:
                return dict(record["n"])
                
        return None
    
    async def search_facts_by_subject(
        self,
        subject: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Поиск фактов по субъекту"""
        await self._ensure_connected()
        
        query = """
        MATCH (f:Fact)
        WHERE f.subject CONTAINS $subject
        AND (f.valid_to IS NULL OR f.valid_to > datetime())
        RETURN f
        ORDER BY f.confidence DESC
        LIMIT $limit
        """
        
        params = {
            "subject": subject,
            "limit": limit
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            facts = []
            async for record in result:
                facts.append(dict(record["f"]))
            
            return facts
    
    async def get_skill_by_name(
        self,
        name: str,
        latest_version: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Получить навык по имени"""
        await self._ensure_connected()
        
        if latest_version:
            query = """
            MATCH (s:Skill {name: $name})
            WITH s
            ORDER BY s.version DESC
            LIMIT 1
            RETURN s
            """
        else:
            query = """
            MATCH (s:Skill {name: $name})
            RETURN s
            ORDER BY s.version DESC
            """
        
        async with self.driver.session() as session:
            result = await session.run(query, {"name": name})
            record = await result.single()
            
            if record:
                return dict(record["s"])
                
        return None
    
    # === УТИЛИТЫ ===
    
    async def update_node_embedding(
        self,
        node_id: str,
        embedding: List[float]
    ) -> bool:
        """Обновить embedding узла"""
        await self._ensure_connected()
        
        query = """
        MATCH (n {id: $id})
        SET n.embedding = $embedding,
            n.embedding_updated_at = datetime()
        RETURN n
        """
        
        params = {
            "id": node_id,
            "embedding": embedding
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                logger.info(f"✅ Обновлен embedding для {node_id}")
                return True
                
        return False
    
    async def archive_old_memories(
        self,
        days_threshold: int = 90
    ) -> int:
        """Архивировать старые воспоминания"""
        await self._ensure_connected()
        
        query = """
        MATCH (n)
        WHERE (n:Fact OR n:Episode OR n:Skill)
        AND n.created_at < datetime() - duration({days: $days})
        AND NOT (n)<-[:SUPERSEDES]-()
        AND NOT (n)<-[:EVOLVED_FROM]-()
        SET n:Archived, n.archived_at = datetime()
        RETURN count(n) as archived_count
        """
        
        params = {
            "days": days_threshold
        }
        
        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            
            if record:
                count = record["archived_count"]
                logger.info(f"✅ Архивировано {count} узлов")
                return count
                
        return 0
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Получить статистику памяти"""
        await self._ensure_connected()
        
        query = """
        MATCH (n)
        WHERE n:Fact OR n:Episode OR n:Skill
        WITH labels(n) as node_labels, count(n) as count
        RETURN node_labels, count
        ORDER BY count DESC
        """
        
        async with self.driver.session() as session:
            result = await session.run(query)
            stats = {
                "total": 0,
                "by_type": {}
            }
            
            async for record in result:
                labels = record["node_labels"]
                count = record["count"]
                
                # Находим основной тип (не Archived)
                main_type = None
                for label in labels:
                    if label in ["Fact", "Episode", "Skill"]:
                        main_type = label
                        break
                
                if main_type:
                    stats["by_type"][main_type] = count
                    stats["total"] += count
            
            return stats
    
    async def run_custom_query(
        self,
        query: str,
        params: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Выполнить произвольный Cypher запрос"""
        await self._ensure_connected()
        
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            records = []
            async for record in result:
                records.append(dict(record))
            
            return records


# Глобальный экземпляр
neo4j_client = Neo4jDirectClient()