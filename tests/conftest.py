import time

import httpx
import pytest
from neo4j import GraphDatabase


@pytest.fixture(scope="session", autouse=True)
def wait_graphiti():
    url = "http://graphiti:7878/health"
    for _ in range(30):  # 30 × 2 s = 1 мин
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    pytest.exit("Graphiti did not become healthy in time", returncode=1)


@pytest.fixture(scope="function")
def seed_test_data():
    """Фикстура для создания тестовых данных в Neo4j"""
    driver = GraphDatabase.driver(
        "bolt://graphiti-neo4j:7687",
        auth=("neo4j", "password")
    )
    
    with driver.session() as session:
        # Создаем тестовые данные
        session.run("""
            MERGE (u:User {
                id: 'test_user_001',
                email: 'test@example.com',
                name: 'Test User',
                created_at: datetime(),
                is_active: true
            })
        """)
        
        session.run("""
            MERGE (p:Preference {
                id: 'pref_001',
                key: 'response_style',
                value: 'detailed',
                created_at: datetime()
            })
        """)
        
        session.run("""
            MERGE (d:DiaryEntry {
                id: 'diary_001',
                user_id: 'test_user_001',
                content: 'Сегодня я протестировал новую систему памяти Graphiti с Neo4j',
                timestamp: datetime(),
                mood: 'excited',
                tags: ['testing', 'graphiti', 'neo4j']
            })
        """)
        
        session.run("""
            MATCH (u:User {id: 'test_user_001'})
            MATCH (p:Preference {id: 'pref_001'})
            MERGE (u)-[:PREFERS {created_at: datetime()}]->(p)
        """)
        
        session.run("""
            MATCH (u:User {id: 'test_user_001'})
            MATCH (d:DiaryEntry {id: 'diary_001'})
            MERGE (u)-[:WRITES]->(d)
        """)
    
    yield driver
    
    # Очищаем тестовые данные после теста
    with driver.session() as session:
        session.run("""
            MATCH (u:User {id: 'test_user_001'})
            MATCH (p:Preference {id: 'pref_001'})
            MATCH (d:DiaryEntry {id: 'diary_001'})
            DETACH DELETE u, p, d
        """)
    
    driver.close()
