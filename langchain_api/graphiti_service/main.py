#!/usr/bin/env python3
"""
GraphitiMemory Validation Service
Простой FastAPI сервер для валидации GraphitiMemory интеграции
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, status
from neo4j import GraphDatabase
from pydantic import BaseModel, Field

# Импортируем утилиты для сериализации
from utils import process_properties, restore_properties

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic модели
class NodeProperties(BaseModel):
    """Свойства узла"""
    msg: str | None = None
    timestamp: float | None = None
    test_run: bool | None = None
    pytest_test: bool | None = None

    class Config:
        extra = "allow"  # ← разрешить любые дополнительные ключи

class Node(BaseModel):
    """Модель узла GraphitiMemory"""
    id: str = Field(..., description="Уникальный идентификатор узла")
    type: str = Field(..., description="Тип узла")
    properties: NodeProperties = Field(default_factory=NodeProperties, description="Свойства узла")

class NodeResponse(BaseModel):
    """Ответ при получении узла"""
    id: str
    type: str
    properties: dict[str, Any]
    created_at: datetime
    updated_at: datetime

class HealthResponse(BaseModel):
    """Ответ health check"""
    status: str = "healthy"
    timestamp: datetime
    neo4j_connected: bool = False
    version: str = "0.3.0-validation"

class StatsResponse(BaseModel):
    """Статистика GraphitiMemory"""
    total_nodes: int = 0
    total_relationships: int = 0
    node_types: dict[str, int] = {}
    last_updated: datetime

# FastAPI приложение
app = FastAPI(
    title="GraphitiMemory Validation Service",
    description="Сервис для валидации GraphitiMemory интеграции в проекте Марк v2",
    version="0.3.0-validation"
)

# Глобальные переменные
neo4j_driver = None
in_memory_nodes = {}

def init_neo4j():
    """Инициализация Neo4j подключения"""
    global neo4j_driver

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://graphiti-neo4j:7687")
    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
        # Проверка подключения
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1 as test")
            result.single()
        logger.info("Neo4j подключение установлено")
        return True
    except Exception as e:
        logger.error(f"Ошибка подключения к Neo4j: {e}")
        return False

def check_neo4j_connection():
    """Проверка подключения к Neo4j"""
    if not neo4j_driver:
        return False

    try:
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1 as test")
            result.single()
        return True
    except Exception as e:
        logger.error(f"Neo4j недоступен: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    logger.info("Запуск GraphitiMemory Validation Service...")
    env = os.getenv("ENV", "dev")
    neo4j_connected = init_neo4j()

    if neo4j_connected:
        logger.info("✅ Neo4j подключение установлено")

        # Инициализация индексов и constraints
        try:
            import sys
            sys.path.append(os.path.dirname(__file__))
            from neo4j_init import init_neo4j as init_neo4j_indexes
            init_neo4j_indexes()
            logger.info("✅ Индексы и constraints инициализированы")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка инициализации индексов: {e}")
    else:
        if env == "prod":
            logger.error("🚨 Neo4j недоступен в prod режиме - завершаем работу")
            import sys
            sys.exit(1)
        else:
            logger.warning("⚠️ Neo4j недоступен в dev режиме, используется in-memory режим")

@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при остановке"""
    global neo4j_driver
    if neo4j_driver:
        neo4j_driver.close()
        logger.info("Neo4j подключение закрыто")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    neo4j_connected = check_neo4j_connection()
    env = os.getenv("ENV", "dev")
    
    # В prod режиме проверяем, что backend = neo4j
    if env == "prod" and not neo4j_connected:
        logger.error("🚨 Health check failed: Neo4j недоступен в prod режиме")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j backend недоступен в prod режиме"
        )

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        neo4j_connected=neo4j_connected,
        version="0.3.0-validation"
    )

@app.get("/version")
async def get_version():
    """Получение версии GraphitiMemory"""
    return {
        "version": "0.3.0-validation",
        "service": "GraphitiMemory Validation Service",
        "python_version": "3.10",
        "neo4j_support": check_neo4j_connection()
    }

@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Получение статистики GraphitiMemory"""
    # Подсчет узлов по типам
    node_types = {}
    for node in in_memory_nodes.values():
        node_type = node.get("type", "unknown")
        node_types[node_type] = node_types.get(node_type, 0) + 1

    return StatsResponse(
        total_nodes=len(in_memory_nodes),
        total_relationships=0,  # Пока без связей
        node_types=node_types,
        last_updated=datetime.now()
    )

@app.post("/nodes", status_code=status.HTTP_201_CREATED)
async def create_node(node: Node):
    """Создание узла"""
    node_id = node.id
    logger.info(f"Создание узла {node_id} типа {node.type}")
    logger.info(f"Полученные свойства: {node.properties}")

    # --- КОРРЕКТНАЯ ОБРАБОТКА extra-полей Pydantic v1 ---
    base_props = node.properties.dict(exclude_none=True)
    extra_props = getattr(node.properties, "__dict__", {}).get("_pydantic_extra", {})
    props = {**base_props, **extra_props}
    
    # Используем утилиты для сериализации
    props = process_properties(props)
    logger.info(f"PROPS to Neo4j → {props}")

    # Проверка на существование (в in-memory режиме)
    if node_id in in_memory_nodes:
        # Идемпотентность: возвращаем 409, но формально это не ошибка клиента
        return {"message": f"Узел {node_id} уже существует", "id": node_id}

    node_data = {
        "id": node_id,
        "type": node.type,
        "properties": props,
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }

    # Сохранение в Neo4j или in-memory
    if check_neo4j_connection():
        try:
            with neo4j_driver.session() as session:
                # Идемпотентное создание: пытаемся MERGE по id
                session.run(
                    f"MERGE (n:{node.type} {{id: $id}}) SET n += $props",
                    id=node_id,
                    props=props
                )
            logger.info(f"Узел {node_id} создан в Neo4j")
        except Exception as e:
            logger.error(f"Ошибка создания узла в Neo4j: {e}")
            # Fallback to in-memory
            in_memory_nodes[node_id] = node_data
    else:
        # In-memory storage
        in_memory_nodes[node_id] = node_data

    return {"message": f"Узел {node_id} создан", "id": node_id}

@app.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str):
    """Получение узла по ID"""

    # Поиск в Neo4j
    if check_neo4j_connection():
        try:
            with neo4j_driver.session() as session:
                result = session.run(
                    "MATCH (n {id: $id}) RETURN n",
                    id=node_id
                )
                record = result.single()
                if record:
                    node = record["n"]
                    # Десериализуем свойства
                    node_props = dict(node)
                    restored_props = restore_properties(node_props)
                    
                    return NodeResponse(
                        id=node.get("id", node_id),
                        type=list(node.labels)[0] if node.labels else "Unknown",
                        properties=restored_props,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
        except Exception as e:
            logger.error(f"Ошибка поиска узла в Neo4j: {e}")

    # Поиск в in-memory
    if node_id in in_memory_nodes:
        node_data = in_memory_nodes[node_id]
        return NodeResponse(
            id=node_data["id"],
            type=node_data["type"],
            properties=node_data["properties"],
            created_at=node_data["created_at"],
            updated_at=node_data["updated_at"]
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Узел с ID {node_id} не найден"
    )

@app.get("/nodes")
async def list_nodes(limit: int = 10, offset: int = 0, search: str | None = None):
    """Получение списка узлов с опциональным поиском"""
    nodes_list = []

    # Чтение из Neo4j
    if check_neo4j_connection():
        try:
            with neo4j_driver.session() as session:
                if search:
                    # Поиск по тексту (с fallback для Community Edition)
                    logger.info(f"Выполняется поиск: '{search}'")
                    try:
                        # Пробуем полнотекстовый поиск (Enterprise Edition)
                        result = session.run("""
                            CALL db.index.fulltext.queryNodes('episode_fulltext', $search)
                            YIELD node, score
                            RETURN node, score
                            ORDER BY score DESC
                            SKIP $offset LIMIT $limit
                        """, search=search, offset=offset, limit=limit)

                        for record in result:
                            node = record["node"]
                            score = record["score"]
                            node_data = {
                                "id": node.get("id", str(uuid.uuid4())),
                                "type": list(node.labels)[0] if node.labels else "Unknown",
                                "properties": dict(node),
                                "score": score,
                                "created_at": datetime.now(),
                                "updated_at": datetime.now()
                            }
                            nodes_list.append(node_data)

                        # Общее количество для поиска
                        count_result = session.run("""
                            CALL db.index.fulltext.queryNodes('episode_fulltext', $search)
                            YIELD node
                            RETURN count(node) as total
                        """, search=search)
                        total = count_result.single()["total"]

                    except Exception as e:
                        if "ProcedureNotFound" in str(e) or "There is no such fulltext schema index" in str(e):
                            # Fallback для Community Edition - поиск через LIKE
                            logger.info("Используется LIKE поиск (Community Edition)")
                            result = session.run("""
                                MATCH (n:Episode)
                                WHERE toLower(n.msg) CONTAINS toLower($search)
                                RETURN n
                                ORDER BY n.created_at DESC
                                SKIP $offset LIMIT $limit
                            """, search=search, offset=offset, limit=limit)

                            for record in result:
                                node = record["n"]
                                node_data = {
                                    "id": node.get("id", str(uuid.uuid4())),
                                    "type": list(node.labels)[0] if node.labels else "Unknown",
                                    "properties": dict(node),
                                    "score": 1.0,  # Нет score для LIKE поиска
                                    "created_at": datetime.now(),
                                    "updated_at": datetime.now()
                                }
                                nodes_list.append(node_data)

                            # Общее количество для поиска
                            count_result = session.run("""
                                MATCH (n:Episode)
                                WHERE toLower(n.msg) CONTAINS toLower($search)
                                RETURN count(n) as total
                            """, search=search)
                            total = count_result.single()["total"]
                        else:
                            raise e
                else:
                    # Обычный список узлов
                    result = session.run(
                        "MATCH (n) RETURN n ORDER BY n.created_at DESC SKIP $offset LIMIT $limit",
                        offset=offset, limit=limit
                    )
                    for record in result:
                        node = record["n"]
                        node_data = {
                            "id": node.get("id", str(uuid.uuid4())),
                            "type": list(node.labels)[0] if node.labels else "Unknown",
                            "properties": dict(node),
                            "created_at": datetime.now(),
                            "updated_at": datetime.now()
                        }
                        nodes_list.append(node_data)

                    # Общее количество
                    count_result = session.run("MATCH (n) RETURN count(n) as total")
                    total = count_result.single()["total"]

                logger.info(f"Загружено {len(nodes_list)} узлов из Neo4j")
                return {
                    "nodes": nodes_list,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "search": search
                }
        except Exception as e:
            logger.error(f"Ошибка чтения узлов из Neo4j: {e}")

    # Fallback to in-memory
    nodes_list = list(in_memory_nodes.values())
    start = offset
    end = offset + limit
    paginated_nodes = nodes_list[start:end]

    return {
        "nodes": paginated_nodes,
        "total": len(nodes_list),
        "limit": limit,
        "offset": offset,
        "search": search
    }

@app.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id: str):
    """Удаление узла"""

    # Удаление из Neo4j
    if check_neo4j_connection():
        try:
            with neo4j_driver.session() as session:
                result = session.run(
                    "MATCH (n {id: $id}) DELETE n RETURN count(n) as deleted",
                    id=node_id
                )
                record = result.single()
                if record and record["deleted"] > 0:
                    logger.info(f"Узел {node_id} удален из Neo4j")
                    return
        except Exception as e:
            logger.error(f"Ошибка удаления узла из Neo4j: {e}")

    # Удаление из in-memory
    if node_id in in_memory_nodes:
        del in_memory_nodes[node_id]
        return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Узел с ID {node_id} не найден"
    )

@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "service": "GraphitiMemory Validation Service",
        "version": "0.3.0-validation",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "version": "/version",
            "stats": "/stats",
            "nodes": "/nodes",
            "create_node": "POST /nodes",
            "get_node": "GET /nodes/{node_id}",
            "delete_node": "DELETE /nodes/{node_id}"
        }
    }

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("GRAPHITI_API_HOST", "0.0.0.0")
    port = int(os.getenv("GRAPHITI_API_PORT", "7878"))

    uvicorn.run(app, host=host, port=port)
