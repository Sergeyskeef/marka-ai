import logging
from typing import Optional, Dict, Any
from neo4j import GraphDatabase
from langchain_api.core.graphiti_config import get_graphiti_config

logger = logging.getLogger(__name__)

def get_user_pref(user_id: str, key: str) -> Optional[str]:
    """
    Получает значение предпочтения пользователя из Neo4j
    
    Args:
        user_id: ID пользователя
        key: Ключ предпочтения (например, 'style', 'detail_level')
        
    Returns:
        Значение предпочтения или None, если не найдено
    """
    try:
        config = get_graphiti_config()
        driver = GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {id: $user_id})-[:PREFERS]->(p:Preference {key: $key})
                RETURN p.value as value
                LIMIT 1
            """, user_id=user_id, key=key)
            
            record = result.single()
            if record:
                logger.info(f"✅ Получено предпочтение {key}={record['value']} для пользователя {user_id}")
                return record['value']
            else:
                logger.info(f"ℹ️ Предпочтение {key} не найдено для пользователя {user_id}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Ошибка получения предпочтения {key} для пользователя {user_id}: {e}")
        return None
    finally:
        if 'driver' in locals():
            driver.close()

def upsert_user_pref(user_id: str, key: str, value: str) -> bool:
    """
    Создает или обновляет предпочтение пользователя в Neo4j
    
    Args:
        user_id: ID пользователя
        key: Ключ предпочтения
        value: Значение предпочтения
        
    Returns:
        True если операция успешна, False в случае ошибки
    """
    try:
        config = get_graphiti_config()
        driver = GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver.session() as session:
            # Создаем или обновляем пользователя
            session.run("""
                MERGE (u:User {id: $user_id})
                SET u.updated_at = datetime()
            """, user_id=user_id)
            
            # Создаем или обновляем предпочтение
            session.run("""
                MERGE (p:Preference {key: $key})
                SET p.value = $value, p.updated_at = datetime()
            """, key=key, value=value)
            
            # Создаем связь между пользователем и предпочтением
            session.run("""
                MATCH (u:User {id: $user_id})
                MATCH (p:Preference {key: $key})
                MERGE (u)-[:PREFERS]->(p)
            """, user_id=user_id, key=key)
            
            logger.info(f"✅ Предпочтение {key}={value} сохранено для пользователя {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения предпочтения {key}={value} для пользователя {user_id}: {e}")
        return False
    finally:
        if 'driver' in locals():
            driver.close()

def get_all_user_prefs(user_id: str) -> Dict[str, str]:
    """
    Получает все предпочтения пользователя
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Словарь {ключ: значение} всех предпочтений пользователя
    """
    try:
        config = get_graphiti_config()
        driver = GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {id: $user_id})-[:PREFERS]->(p:Preference)
                RETURN p.key as key, p.value as value
            """, user_id=user_id)
            
            prefs = {record['key']: record['value'] for record in result}
            logger.info(f"✅ Получено {len(prefs)} предпочтений для пользователя {user_id}")
            return prefs
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения предпочтений для пользователя {user_id}: {e}")
        return {}
    finally:
        if 'driver' in locals():
            driver.close()

def delete_user_pref(user_id: str, key: str) -> bool:
    """
    Удаляет предпочтение пользователя
    
    Args:
        user_id: ID пользователя
        key: Ключ предпочтения
        
    Returns:
        True если операция успешна, False в случае ошибки
    """
    try:
        config = get_graphiti_config()
        driver = GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_username, config.neo4j_password))
        with driver.session() as session:
            result = session.run("""
                MATCH (u:User {id: $user_id})-[r:PREFERS]->(p:Preference {key: $key})
                WITH count(r) as deleted_count, p, r
                DELETE r
                WITH p, deleted_count
                OPTIONAL MATCH (p)
                WHERE NOT (p)<-[:PREFERS]-()
                DELETE p
                RETURN deleted_count as deleted
            """, user_id=user_id, key=key)
            
            deleted_count = result.single()['deleted']
            if deleted_count > 0:
                logger.info(f"✅ Предпочтение {key} удалено для пользователя {user_id}")
                return True
            else:
                logger.info(f"ℹ️ Предпочтение {key} не найдено для пользователя {user_id}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка удаления предпочтения {key} для пользователя {user_id}: {e}")
        return False
    finally:
        if 'driver' in locals():
            driver.close() 