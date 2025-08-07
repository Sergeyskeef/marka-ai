#!/usr/bin/env python3
"""
Инициализация продвинутой структуры памяти в Neo4j
Создает три типа узлов: Fact, Episode, Skill с индексами и ограничениями
"""

import asyncio
import logging
from neo4j import AsyncGraphDatabase
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://graphiti-neo4j:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


async def init_constraints(session):
    """Создание ограничений уникальности"""
    constraints = [
        # Факты
        "CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE",
        
        # Эпизоды
        "CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE",
        
        # Навыки
        "CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT skill_name_version IF NOT EXISTS FOR (s:Skill) REQUIRE (s.name, s.version) IS UNIQUE",
    ]
    
    for constraint in constraints:
        try:
            await session.run(constraint)
            logger.info(f"✅ Создано ограничение: {constraint.split('CONSTRAINT')[1].split('IF')[0].strip()}")
        except Exception as e:
            if "already exists" in str(e):
                logger.info(f"⏭️  Ограничение уже существует")
            else:
                logger.error(f"❌ Ошибка создания ограничения: {e}")


async def init_indexes(session):
    """Создание индексов для производительности"""
    indexes = [
        # Индексы для Fact
        "CREATE INDEX fact_subject IF NOT EXISTS FOR (f:Fact) ON (f.subject)",
        "CREATE INDEX fact_predicate IF NOT EXISTS FOR (f:Fact) ON (f.predicate)",
        "CREATE INDEX fact_temporal IF NOT EXISTS FOR (f:Fact) ON (f.valid_from, f.valid_to)",
        "CREATE INDEX fact_learned IF NOT EXISTS FOR (f:Fact) ON (f.learned_at)",
        
        # Индексы для Episode
        "CREATE INDEX episode_occurred IF NOT EXISTS FOR (e:Episode) ON (e.occurred_at)",
        "CREATE INDEX episode_outcome IF NOT EXISTS FOR (e:Episode) ON (e.outcome)",
        "CREATE INDEX episode_satisfaction IF NOT EXISTS FOR (e:Episode) ON (e.satisfaction)",
        
        # Индексы для Skill
        "CREATE INDEX skill_name IF NOT EXISTS FOR (s:Skill) ON (s.name)",
        "CREATE INDEX skill_performance IF NOT EXISTS FOR (s:Skill) ON (s.performance_score)",
        "CREATE INDEX skill_usage IF NOT EXISTS FOR (s:Skill) ON (s.usage_count)",
        
        # Полнотекстовые индексы
        "CREATE TEXT INDEX fact_search IF NOT EXISTS FOR (f:Fact) ON (f.subject, f.object)",
        "CREATE TEXT INDEX episode_search IF NOT EXISTS FOR (e:Episode) ON (e.situation, e.lesson_learned)",
        "CREATE TEXT INDEX skill_search IF NOT EXISTS FOR (s:Skill) ON (s.name, s.procedure)",
    ]
    
    for index in indexes:
        try:
            await session.run(index)
            logger.info(f"✅ Создан индекс: {index.split('INDEX')[1].split('IF')[0].strip()}")
        except Exception as e:
            if "already exists" in str(e):
                logger.info(f"⏭️  Индекс уже существует")
            else:
                logger.error(f"❌ Ошибка создания индекса: {e}")


async def init_vector_indexes(session):
    """Создание векторных индексов для семантического поиска"""
    # Проверяем, поддерживает ли Neo4j векторные индексы
    try:
        # Пробуем создать векторный индекс
        vector_indexes = [
            """
            CREATE VECTOR INDEX fact_embeddings IF NOT EXISTS
            FOR (f:Fact) ON f.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 1536,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """,
            """
            CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
            FOR (e:Episode) ON e.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 1536,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """,
            """
            CREATE VECTOR INDEX skill_embeddings IF NOT EXISTS
            FOR (s:Skill) ON s.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 1536,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """
        ]
        
        for v_index in vector_indexes:
            try:
                await session.run(v_index)
                logger.info(f"✅ Создан векторный индекс")
            except Exception as e:
                if "already exists" in str(e):
                    logger.info(f"⏭️  Векторный индекс уже существует")
                else:
                    logger.warning(f"⚠️  Векторные индексы не поддерживаются: {e}")
                    
    except Exception as e:
        logger.warning(f"⚠️  Векторные индексы недоступны в этой версии Neo4j: {e}")
        logger.info("💡 Рекомендуется обновить Neo4j до версии 5.11+ для поддержки векторного поиска")


async def create_sample_data(session):
    """Создание примеров данных для тестирования"""
    
    # Пример факта
    fact_query = """
    MERGE (f:Fact {id: 'fact-sample-001'})
    SET f += {
        subject: 'Пользователь',
        predicate: 'предпочитает',
        object: 'Python для разработки',
        confidence: 0.95,
        valid_from: datetime(),
        valid_to: null,
        learned_at: datetime(),
        source: 'user_statement',
        embedding: [0.1, 0.2, 0.3]  // Заглушка для embedding
    }
    RETURN f
    """
    
    # Пример эпизода
    episode_query = """
    MERGE (e:Episode {id: 'episode-sample-001'})
    SET e += {
        occurred_at: datetime() - duration('PT1H'),
        recorded_at: datetime(),
        situation: 'Пользователь попросил написать функцию сортировки',
        actions_taken: ['Анализ требований', 'Написание кода', 'Тестирование'],
        outcome: 'success',
        reasoning: 'Использовал встроенную функцию sorted() как оптимальное решение',
        lesson_learned: 'Встроенные функции Python обычно оптимальнее самописных',
        satisfaction: 0.9,
        embedding: [0.4, 0.5, 0.6]
    }
    RETURN e
    """
    
    # Пример навыка
    skill_query = """
    MERGE (s:Skill {id: 'skill-sample-001'})
    SET s += {
        name: 'python_code_generation',
        trigger_patterns: ['написать код', 'создать функцию', 'реализовать алгоритм'],
        procedure: 'Анализировать требования, выбрать оптимальный подход, написать чистый код',
        system_prompt: 'Ты опытный Python разработчик. Пиши чистый, эффективный код.',
        version: 1,
        performance_score: 0.85,
        usage_count: 42,
        last_used: datetime(),
        created_at: datetime() - duration('P30D')
    }
    RETURN s
    """
    
    # Создание связей между примерами
    relation_query = """
    MATCH (e:Episode {id: 'episode-sample-001'})
    MATCH (f:Fact {id: 'fact-sample-001'})
    MATCH (s:Skill {id: 'skill-sample-001'})
    MERGE (e)-[:USED_FACT]->(f)
    MERGE (e)-[:LEARNED_SKILL]->(s)
    RETURN e, f, s
    """
    
    try:
        await session.run(fact_query)
        logger.info("✅ Создан пример факта")
        
        await session.run(episode_query)
        logger.info("✅ Создан пример эпизода")
        
        await session.run(skill_query)
        logger.info("✅ Создан пример навыка")
        
        await session.run(relation_query)
        logger.info("✅ Созданы связи между примерами")
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания примеров: {e}")


async def verify_setup(session):
    """Проверка созданной структуры"""
    
    # Проверка типов узлов
    node_count_query = """
    MATCH (n)
    WHERE n:Fact OR n:Episode OR n:Skill
    RETURN labels(n)[0] as type, count(n) as count
    ORDER BY type
    """
    
    # Проверка индексов
    index_query = "SHOW INDEXES"
    
    # Проверка ограничений
    constraint_query = "SHOW CONSTRAINTS"
    
    try:
        # Количество узлов
        result = await session.run(node_count_query)
        nodes = await result.values()
        
        logger.info("\n📊 Статистика узлов:")
        for node_type, count in nodes:
            logger.info(f"   {node_type}: {count}")
        
        # Индексы
        result = await session.run(index_query)
        indexes = await result.values()
        logger.info(f"\n📑 Создано индексов: {len(indexes)}")
        
        # Ограничения
        result = await session.run(constraint_query)
        constraints = await result.values()
        logger.info(f"🔒 Создано ограничений: {len(constraints)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки: {e}")


async def main():
    """Главная функция"""
    logger.info("🚀 Инициализация продвинутой структуры памяти в Neo4j")
    logger.info(f"📍 Подключение к {NEO4J_URI}")
    
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    
    try:
        async with driver.session() as session:
            # 1. Создаем ограничения
            logger.info("\n1️⃣ Создание ограничений...")
            await init_constraints(session)
            
            # 2. Создаем индексы
            logger.info("\n2️⃣ Создание индексов...")
            await init_indexes(session)
            
            # 3. Создаем векторные индексы
            logger.info("\n3️⃣ Создание векторных индексов...")
            await init_vector_indexes(session)
            
            # 4. Создаем примеры данных
            logger.info("\n4️⃣ Создание примеров данных...")
            await create_sample_data(session)
            
            # 5. Проверяем результат
            logger.info("\n5️⃣ Проверка структуры...")
            await verify_setup(session)
            
        logger.info("\n✅ Инициализация завершена успешно!")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())