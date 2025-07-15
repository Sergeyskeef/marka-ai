#!/usr/bin/env python3
"""
Инициализация Neo4j: индексы, constraints и настройки
"""
import logging
import os

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


def init_neo4j_constraints_and_indexes():
    """Инициализация constraints и индексов в Neo4j"""

    # Подключение к Neo4j
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://graphiti-neo4j:7687")
    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))

        with driver.session() as session:
            # 1. Уникальный constraint на id эпизода
            logger.info("Создание уникального constraint на id эпизода...")
            session.run("""
                CREATE CONSTRAINT episode_id_unique IF NOT EXISTS
                FOR (e:Episode) REQUIRE e.id IS UNIQUE
            """)

            # 2. Индекс на timestamp для быстрой сортировки
            logger.info("Создание индекса на timestamp...")
            session.run("""
                CREATE INDEX episode_timestamp IF NOT EXISTS
                FOR (e:Episode) ON (e.timestamp)
            """)

            # 3. Индекс на created_at для сортировки по времени создания
            logger.info("Создание индекса на created_at...")
            session.run("""
                CREATE INDEX episode_created_at IF NOT EXISTS
                FOR (e:Episode) ON (e.created_at)
            """)

            # 4. Индекс на msg для быстрого поиска по тексту
            logger.info("Создание индекса на msg...")
            session.run("""
                CREATE INDEX episode_msg IF NOT EXISTS
                FOR (e:Episode) ON (e.msg)
            """)

            # 5. Составной индекс на source + priority для фильтрации
            logger.info("Создание составного индекса на source + priority...")
            session.run("""
                CREATE INDEX episode_source_priority IF NOT EXISTS
                FOR (e:Episode) ON (e.source, e.priority)
            """)

            # 6. Полнотекстовый индекс для поиска по содержимому (только Enterprise)
            try:
                logger.info("Создание полнотекстового индекса...")
                session.run("""
                    CALL db.index.fulltext.createNodeIndex(
                        'episode_fulltext',
                        ['Episode'],
                        ['msg']
                    ) YIELD indexName
                """)
                logger.info("✅ Полнотекстовый индекс создан (Enterprise Edition)")
            except Exception as e:
                if "ProcedureNotFound" in str(e):
                    logger.warning("⚠️ Полнотекстовый индекс недоступен в Community Edition")
                    logger.info("ℹ️ Используется обычный индекс на msg для поиска")
                else:
                    raise e

            # 7. Проверка статуса индексов
            logger.info("Проверка статуса индексов...")
            result = session.run("SHOW INDEXES WHERE state = 'ONLINE'")
            online_indexes = [record["name"] for record in result]
            logger.info(f"Онлайн индексы: {online_indexes}")

            # 8. Проверка constraints
            logger.info("Проверка constraints...")
            result = session.run("SHOW CONSTRAINTS")
            constraints = [record["name"] for record in result]
            logger.info(f"Constraints: {constraints}")

        driver.close()
        logger.info("✅ Инициализация Neo4j завершена успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Neo4j: {e}")
        raise


def check_neo4j_health():
    """Проверка здоровья Neo4j"""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://graphiti-neo4j:7687")
    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))

        with driver.session() as session:
            # Проверка подключения
            result = session.run("RETURN 1 as test")
            result.single()["test"]

            # Проверка количества узлов
            result = session.run("MATCH (n:Episode) RETURN count(n) as count")
            episode_count = result.single()["count"]

            # Проверка индексов
            result = session.run("SHOW INDEXES WHERE state = 'ONLINE'")
            online_indexes = [record["name"] for record in result]

            logger.info(f"✅ Neo4j здоров: {episode_count} эпизодов, {len(online_indexes)} онлайн индексов")

        driver.close()
        return True

    except Exception as e:
        logger.error(f"❌ Neo4j недоступен: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("🚀 Инициализация Neo4j...")
    init_neo4j_constraints_and_indexes()

    print("🔍 Проверка здоровья...")
    check_neo4j_health()

    print("✅ Готово!")
