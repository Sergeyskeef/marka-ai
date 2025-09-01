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
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
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