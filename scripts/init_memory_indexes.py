#!/usr/bin/env python3
"""
Инициализация дополнительных индексов для оптимизации памяти
"""

import os
import time
import logging
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_memory_indexes():
    """Создает дополнительные индексы для улучшения производительности"""
    
    # Параметры подключения
    neo4j_url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Попытка подключения к Neo4j ({attempt + 1}/{max_retries})...")
            driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
            
            with driver.session() as session:
                # Проверяем соединение
                session.run("RETURN 1")
                logger.info("✅ Подключение к Neo4j установлено")
                
                # Создаем полнотекстовый индекс для поиска
                logger.info("Создание полнотекстового индекса...")
                session.run("""
                    CALL db.index.fulltext.createNodeIndex(
                        'episode_text_search',
                        ['Episode'],
                        ['msg', 'source', 'tags'],
                        {analyzer: 'russian'}
                    )
                """)
                
                # Индекс на user_id для фильтрации по пользователю
                logger.info("Создание индекса на user_id...")
                session.run("""
                    CREATE INDEX episode_user_id IF NOT EXISTS
                    FOR (e:Episode) ON (e.user_id)
                """)
                
                # Индекс на type для фильтрации по типу
                logger.info("Создание индекса на type...")
                session.run("""
                    CREATE INDEX episode_type IF NOT EXISTS
                    FOR (e:Episode) ON (e.type)
                """)
                
                # Композитный индекс для частых запросов
                logger.info("Создание композитного индекса...")
                session.run("""
                    CREATE INDEX episode_user_timestamp IF NOT EXISTS
                    FOR (e:Episode) ON (e.user_id, e.created_at)
                """)
                
                # Индекс на importance для приоритетного поиска
                logger.info("Создание индекса на importance...")
                session.run("""
                    CREATE INDEX episode_importance IF NOT EXISTS
                    FOR (e:Episode) ON (e.importance)
                """)
                
                # === НОВЫЕ ОПТИМИЗИРОВАННЫЕ ИНДЕКСЫ ===
                
                # Композитный индекс для Entity
                logger.info("Создание композитного индекса для Entity...")
                try:
                    session.run("""
                        CREATE INDEX entity_name_type IF NOT EXISTS
                        FOR (n:Entity) ON (n.name, n.type)
                    """)
                except Exception as e:
                    logger.warning(f"Индекс entity_name_type: {e}")
                
                # Индекс для отношений MENTIONS
                logger.info("Создание индекса для отношений MENTIONS...")
                try:
                    session.run("""
                        CREATE INDEX rel_mentions IF NOT EXISTS
                        FOR ()-[r:MENTIONS]-() ON (r.confidence)
                    """)
                except Exception as e:
                    logger.warning(f"Индекс rel_mentions: {e}")
                
                # Полнотекстовый индекс с расширенными настройками
                logger.info("Создание оптимизированного полнотекстового индекса...")
                try:
                    session.run("""
                        CALL db.index.fulltext.createNodeIndex(
                            'episode_search_optimized',
                            ['Episode'],
                            ['msg', 'source', 'tags', 'summary'],
                            {
                                analyzer: 'russian',
                                eventually_consistent: true
                            }
                        )
                    """)
                except Exception as e:
                    logger.warning(f"Полнотекстовый оптимизированный индекс: {e}")
                
                # Индекс для временных запросов
                logger.info("Создание индекса для временных запросов...")
                session.run("""
                    CREATE INDEX episode_timestamp IF NOT EXISTS
                    FOR (e:Episode) ON (e.created_at)
                """)
                
                # Векторный индекс для эмбеддингов (если поддерживается)
                logger.info("Попытка создания векторного индекса...")
                try:
                    session.run("""
                        CALL db.index.vector.createNodeIndex(
                            'episode_embeddings',
                            'Episode',
                            'embedding',
                            1536,
                            'cosine'
                        )
                    """)
                    logger.info("✅ Векторный индекс создан")
                except Exception as e:
                    logger.warning(f"⚠️ Векторный индекс не создан (возможно, не поддерживается): {e}")
                
                logger.info("✅ Все индексы успешно созданы")
                driver.close()
                return True
                
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")
            if "already exists" in str(e):
                logger.info("Некоторые индексы уже существуют, это нормально")
                return True
            
            if attempt < max_retries - 1:
                logger.info(f"Повторная попытка через {retry_delay} секунд...")
                time.sleep(retry_delay)
            else:
                logger.error("❌ Не удалось создать индексы после всех попыток")
                return False
    
    return False


if __name__ == "__main__":
    logger.info("🚀 Запуск инициализации индексов памяти...")
    
    if create_memory_indexes():
        logger.info("✅ Инициализация завершена успешно")
    else:
        logger.error("❌ Инициализация завершена с ошибками")
        exit(1)