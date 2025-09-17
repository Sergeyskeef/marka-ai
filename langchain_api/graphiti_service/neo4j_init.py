#!/usr/bin/env python3
"""
Скрипт инициализации Neo4j для Graphiti
Создает индексы, constraints и настройки для работы с Graphiti
"""

import os
import logging
import time
from neo4j import GraphDatabase
from typing import Optional

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DDL для создания индексов и constraints
_DDL_STATEMENTS = [
    # Episode
    "CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE;",
    "CREATE INDEX episode_msg IF NOT EXISTS FOR (e:Episode) ON (e.msg);",
    "CREATE INDEX episode_timestamp IF NOT EXISTS FOR (e:Episode) ON (e.timestamp);",
    "CREATE INDEX episode_chat_id IF NOT EXISTS FOR (e:Episode) ON (e.chat_id);",
    "CREATE INDEX episode_metadata IF NOT EXISTS FOR (e:Episode) ON (e.metadata);",

    # Message
    "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE;",
    "CREATE INDEX message_msg IF NOT EXISTS FOR (m:Message) ON (m.msg);",
    "CREATE INDEX message_session_id IF NOT EXISTS FOR (m:Message) ON (m.session_id);",
    "CREATE INDEX message_role IF NOT EXISTS FOR (m:Message) ON (m.role);",
    "CREATE INDEX message_created_at IF NOT EXISTS FOR (m:Message) ON (m.created_at);",

    # Fact / Skill (если будут использоваться как отдельные метки в будущем)
    "CREATE INDEX fact_subject IF NOT EXISTS FOR (f:Fact) ON (f.subject);",
    "CREATE INDEX fact_predicate IF NOT EXISTS FOR (f:Fact) ON (f.predicate);",
    "CREATE INDEX fact_object IF NOT EXISTS FOR (f:Fact) ON (f.object);",

    # Fulltext индексы (безопасные вызовы, если доступно)
    "CALL db.index.fulltext.createNodeIndex('fulltext_messages', ['Message'], ['msg'])",
    "CALL db.index.fulltext.createNodeIndex('fulltext_episodes', ['Episode'], ['msg'])",

    # Fractal node types
    "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;",
    "CREATE INDEX person_user_id IF NOT EXISTS FOR (p:Person) ON (p.user_id);",
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE;",
    "CREATE INDEX project_name IF NOT EXISTS FOR (p:Project) ON (p.name);",
    "CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE;",
    "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name);",
    "CREATE CONSTRAINT incident_id IF NOT EXISTS FOR (i:Incident) REQUIRE i.id IS UNIQUE;",
    "CREATE CONSTRAINT goal_id IF NOT EXISTS FOR (g:Goal) REQUIRE g.id IS UNIQUE;",
    "CREATE CONSTRAINT strategy_id IF NOT EXISTS FOR (s:Strategy) REQUIRE s.id IS UNIQUE;",

    # Relationship property indexes (Neo4j 5 supports property indexes on rels)
    "CREATE INDEX rel_scale IF NOT EXISTS FOR ()-[r]-() ON (r.scale)",
    # --- Graph Schema v1 (для тестов) ---
    # User
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;",
    "CREATE INDEX user_email IF NOT EXISTS FOR (u:User) ON (u.email);",
    "CREATE INDEX user_created_at IF NOT EXISTS FOR (u:User) ON (u.created_at);",
    # Preference
    "CREATE CONSTRAINT preference_id IF NOT EXISTS FOR (p:Preference) REQUIRE p.id IS UNIQUE;",
    "CREATE INDEX preference_key IF NOT EXISTS FOR (p:Preference) ON (p.key);",
    # ToolCall
    "CREATE CONSTRAINT toolcall_id IF NOT EXISTS FOR (t:ToolCall) REQUIRE t.id IS UNIQUE;",
    "CREATE INDEX toolcall_user_tool IF NOT EXISTS FOR (t:ToolCall) ON (t.user_id, t.tool_name);",
    "CREATE INDEX toolcall_started_at IF NOT EXISTS FOR (t:ToolCall) ON (t.started_at);",
    "CREATE INDEX toolcall_status IF NOT EXISTS FOR (t:ToolCall) ON (t.status);",
    # Outcome
    "CREATE CONSTRAINT outcome_id IF NOT EXISTS FOR (o:Outcome) REQUIRE o.id IS UNIQUE;",
    "CREATE INDEX outcome_toolcall IF NOT EXISTS FOR (o:Outcome) ON (o.toolcall_id);",
    "CREATE INDEX outcome_success IF NOT EXISTS FOR (o:Outcome) ON (o.success);",
    "CREATE INDEX outcome_created_at IF NOT EXISTS FOR (o:Outcome) ON (o.created_at);",
    # DiaryEntry
    "CREATE CONSTRAINT diary_entry_id IF NOT EXISTS FOR (d:DiaryEntry) REQUIRE d.id IS UNIQUE;",
    "CREATE INDEX diary_user IF NOT EXISTS FOR (d:DiaryEntry) ON (d.user_id);",
    "CREATE INDEX diary_timestamp IF NOT EXISTS FOR (d:DiaryEntry) ON (d.timestamp);",
    "CREATE INDEX diary_content IF NOT EXISTS FOR (d:DiaryEntry) ON (d.content);",
    # Concept
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;",
    "CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name);",
    "CREATE INDEX concept_category IF NOT EXISTS FOR (c:Concept) ON (c.category);",
    "CREATE INDEX concept_description IF NOT EXISTS FOR (c:Concept) ON (c.description);",
    # Relationship index: User-Preference (по требованию тестов)
    "CREATE INDEX user_pref_relationship IF NOT EXISTS FOR ()-[r:PREFERS]-() ON (r.created_at)",
]

def wait_for_neo4j(driver, max_retries: int = 30, delay: int = 2) -> bool:
    """Ожидание готовности Neo4j"""
    for attempt in range(max_retries):
        try:
            with driver.session() as session:
                session.run("RETURN 1")
                logger.info("✅ Neo4j готов к работе")
                return True
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1}/{max_retries}: Neo4j еще не готов: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
    return False

def init_neo4j():
    """Инициализация Neo4j для Graphiti"""
    # Получаем параметры подключения
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://graphiti-neo4j:7687")
    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    env = os.getenv("ENV", "dev")
    
    logger.info(f"🔧 Инициализация Neo4j для Graphiti (ENV: {env})")
    logger.info(f"📡 Подключение к: {neo4j_uri}")
    
    try:
        # Создаем драйвер
        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_username, neo4j_password)
        )
        
        # Ждем готовности Neo4j
        if not wait_for_neo4j(driver):
            logger.error("❌ Neo4j не готов после всех попыток")
            if env == "prod":
                logger.error("🚨 В prod режиме завершаем работу")
                exit(1)
            else:
                logger.warning("⚠️ В dev режиме продолжаем без Neo4j")
                return False
        
        # Выполняем DDL операции
        with driver.session() as session:
            for statement in _DDL_STATEMENTS:
                try:
                    result = session.run(statement)
                    logger.info(f"✅ Выполнено: {statement[:50]}...")
                except Exception as e:
                    # Игнорируем ошибки "уже существует"
                    if "already exists" in str(e).lower() or "already exists" in str(e).lower():
                        logger.info(f"ℹ️ Уже существует: {statement[:50]}...")
                    else:
                        logger.warning(f"⚠️ Ошибка при выполнении: {statement[:50]}... - {e}")
        
        # Проверяем созданные индексы
        with driver.session() as session:
            result = session.run("SHOW INDEXES")
            indexes = [record["name"] for record in result]
            logger.info(f"📊 Созданные индексы: {indexes}")
        
        logger.info("✅ Инициализация Neo4j завершена успешно")
        # Тестовые данные для Graph Schema v1 (dev)
        if env != "prod":
            try:
                with driver.session() as session:
                    session.run(
                        "MERGE (u:User {id: 'test_user_001'}) SET u.email='test@example.com', u.created_at=timestamp()"
                    )
                    session.run(
                        "MERGE (p:Preference {id: 'pref_001'}) SET p.key='theme', p.value='dark'"
                    )
                    session.run(
                        "MERGE (d:DiaryEntry {id: 'diary_001'}) SET d.user_id='test_user_001', d.timestamp=timestamp(), d.content='Test entry'"
                    )
                    session.run(
                        "MATCH (u:User {id:'test_user_001'}), (p:Preference {id:'pref_001'}) MERGE (u)-[:PREFERS]->(p)"
                    )
                    session.run(
                        "MATCH (u:User {id:'test_user_001'}), (d:DiaryEntry {id:'diary_001'}) MERGE (u)-[:WRITES]->(d)"
                    )
                logger.info("✅ Тестовые данные Graph Schema v1 созданы")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось создать тестовые данные Graph Schema v1: {e}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Neo4j: {e}")
        if env == "prod":
            logger.error("🚨 В prod режиме завершаем работу")
            exit(1)
        else:
            logger.warning("⚠️ В dev режиме продолжаем без Neo4j")
            return False
    finally:
        if 'driver' in locals():
            driver.close()

if __name__ == "__main__":
    init_neo4j() 