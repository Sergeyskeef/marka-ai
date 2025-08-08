#!/usr/bin/env python3
"""
Скрипт миграции старых данных в новый формат
Нормализует ID и переносит данные из Graphiti в Neo4j
"""

import asyncio
import logging
import sys
import os
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.memory.neo4j_direct import neo4j_client
from app.utils import id_generator, IDType
from core.memory.memory_manager import memory_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataMigrator:
    """Мигратор данных из старого формата в новый"""
    
    def __init__(self):
        self.migrated_count = 0
        self.failed_count = 0
        self.id_mapping = {}  # old_id -> new_id
    
    async def migrate_all(self):
        """Основной метод миграции"""
        logger.info("🚀 Начинаем миграцию данных...")
        
        # 1. Подключаемся к Neo4j
        await neo4j_client.connect()
        
        try:
            # 2. Получаем все записи из Graphiti
            logger.info("📥 Загружаем данные из Graphiti...")
            all_items = await self._load_all_graphiti_data()
            logger.info(f"📊 Найдено {len(all_items)} записей для миграции")
            
            # 3. Классифицируем записи
            classified = self._classify_items(all_items)
            
            # 4. Мигрируем каждый тип
            await self._migrate_facts(classified['facts'])
            await self._migrate_episodes(classified['episodes'])
            await self._migrate_skills(classified['skills'])
            
            # 5. Отчет о миграции
            self._print_report()
            
        finally:
            await neo4j_client.close()
    
    async def _load_all_graphiti_data(self) -> List[Dict[str, Any]]:
        """Загружает все данные из Graphiti"""
        all_items = []
        
        # Пытаемся загрузить большое количество записей
        search_result = await memory_manager.search_episodes("", limit=1000)
        
        if search_result.get("items"):
            all_items.extend(search_result["items"])
        
        return all_items
    
    def _classify_items(self, items: List[Dict[str, Any]]) -> Dict[str, List]:
        """Классифицирует записи по типам"""
        classified = {
            'facts': [],
            'episodes': [],
            'skills': [],
            'unknown': []
        }
        
        for item in items:
            metadata = item.get("metadata", {})
            item_type = metadata.get("type", "").lower()
            
            # Пытаемся определить тип по содержимому
            if item_type == "fact" or all(key in metadata for key in ["subject", "predicate", "object"]):
                classified['facts'].append(item)
            elif item_type == "episode" or "outcome" in metadata:
                classified['episodes'].append(item)
            elif item_type == "skill" or "trigger_patterns" in metadata:
                classified['skills'].append(item)
            else:
                # Пытаемся определить по тексту
                text = item.get("text", "").lower()
                if "факт:" in text or "fact:" in text:
                    classified['facts'].append(item)
                elif "эпизод:" in text or "ситуация:" in text:
                    classified['episodes'].append(item)
                elif "навык:" in text or "skill:" in text:
                    classified['skills'].append(item)
                else:
                    classified['unknown'].append(item)
        
        logger.info(f"📊 Классификация: Facts={len(classified['facts'])}, "
                   f"Episodes={len(classified['episodes'])}, "
                   f"Skills={len(classified['skills'])}, "
                   f"Unknown={len(classified['unknown'])}")
        
        return classified
    
    async def _migrate_facts(self, facts: List[Dict[str, Any]]):
        """Мигрирует факты"""
        logger.info(f"🔄 Мигрируем {len(facts)} фактов...")
        
        for fact in facts:
            try:
                metadata = fact.get("metadata", {})
                
                # Извлекаем данные
                subject = metadata.get("subject", "Unknown")
                predicate = metadata.get("predicate", "is")
                obj = metadata.get("object", fact.get("text", "Unknown"))
                confidence = metadata.get("confidence", 0.7)
                source = metadata.get("source", "migration")
                embedding = metadata.get("embedding", [])
                
                # Создаем новый факт
                result = await neo4j_client.create_fact(
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    confidence=confidence,
                    source=source,
                    embedding=embedding,
                    metadata={"migrated": True, "old_id": fact.get("id")}
                )
                
                if result["success"]:
                    self.migrated_count += 1
                    self.id_mapping[fact.get("id")] = result["id"]
                else:
                    self.failed_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Ошибка миграции факта: {e}")
                self.failed_count += 1
    
    async def _migrate_episodes(self, episodes: List[Dict[str, Any]]):
        """Мигрирует эпизоды"""
        logger.info(f"🔄 Мигрируем {len(episodes)} эпизодов...")
        
        for episode in episodes:
            try:
                metadata = episode.get("metadata", {})
                
                # Извлекаем данные
                situation = metadata.get("situation", episode.get("text", "Unknown situation"))
                actions = metadata.get("actions_taken", [])
                if isinstance(actions, str):
                    import json
                    try:
                        actions = json.loads(actions)
                    except:
                        actions = [actions]
                
                outcome = metadata.get("outcome", "unknown")
                reasoning = metadata.get("reasoning", "")
                lesson = metadata.get("lesson_learned", "")
                satisfaction = metadata.get("satisfaction", 0.5)
                embedding = metadata.get("embedding", [])
                
                # Создаем новый эпизод
                result = await neo4j_client.create_episode(
                    situation=situation,
                    actions_taken=actions,
                    outcome=outcome,
                    reasoning=reasoning,
                    lesson_learned=lesson,
                    satisfaction=satisfaction,
                    embedding=embedding,
                    metadata={"migrated": True, "old_id": episode.get("id")}
                )
                
                if result["success"]:
                    self.migrated_count += 1
                    self.id_mapping[episode.get("id")] = result["id"]
                else:
                    self.failed_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Ошибка миграции эпизода: {e}")
                self.failed_count += 1
    
    async def _migrate_skills(self, skills: List[Dict[str, Any]]):
        """Мигрирует навыки"""
        logger.info(f"🔄 Мигрируем {len(skills)} навыков...")
        
        for skill in skills:
            try:
                metadata = skill.get("metadata", {})
                
                # Извлекаем данные
                name = metadata.get("name", f"skill_{skill.get('id', 'unknown')}")
                trigger_patterns = metadata.get("trigger_patterns", [])
                if isinstance(trigger_patterns, str):
                    import json
                    try:
                        trigger_patterns = json.loads(trigger_patterns)
                    except:
                        trigger_patterns = [trigger_patterns]
                
                procedure = metadata.get("procedure", skill.get("text", ""))
                system_prompt = metadata.get("system_prompt", "")
                performance_score = metadata.get("performance_score", 0.5)
                embedding = metadata.get("embedding", [])
                
                # Создаем новый навык
                result = await neo4j_client.create_skill(
                    name=name,
                    trigger_patterns=trigger_patterns,
                    procedure=procedure,
                    system_prompt=system_prompt,
                    performance_score=performance_score,
                    embedding=embedding,
                    metadata={"migrated": True, "old_id": skill.get("id")}
                )
                
                if result["success"]:
                    self.migrated_count += 1
                    self.id_mapping[skill.get("id")] = result["id"]
                else:
                    self.failed_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Ошибка миграции навыка: {e}")
                self.failed_count += 1
    
    def _print_report(self):
        """Выводит отчет о миграции"""
        logger.info("\n" + "="*50)
        logger.info("📊 ОТЧЕТ О МИГРАЦИИ")
        logger.info("="*50)
        logger.info(f"✅ Успешно мигрировано: {self.migrated_count}")
        logger.info(f"❌ Ошибок миграции: {self.failed_count}")
        logger.info(f"🔄 Создано маппингов ID: {len(self.id_mapping)}")
        logger.info("="*50)
        
        if self.failed_count > 0:
            logger.warning("⚠️ Некоторые записи не удалось мигрировать. Проверьте логи.")
        else:
            logger.info("🎉 Миграция завершена успешно!")


async def main():
    """Основная функция"""
    migrator = DataMigrator()
    await migrator.migrate_all()


if __name__ == "__main__":
    asyncio.run(main())