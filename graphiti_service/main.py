#!/usr/bin/env python3
"""
GraphitiMemory Validation Service
Простой FastAPI сервер для валидации GraphitiMemory интеграции
"""
import os
import uuid
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from neo4j import GraphDatabase
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic модели
class NodeProperties(BaseModel):
    """Свойства узла"""
    msg: Optional[str] = None
    timestamp: Optional[float] = None
    test_run: Optional[bool] = None
    pytest_test: Optional[bool] = None

class Node(BaseModel):
    """Модель узла GraphitiMemory"""
    id: str = Field(..., description="Уникальный идентификатор узла")
    type: str = Field(..., description="Тип узла")
    properties: NodeProperties = Field(default_factory=NodeProperties, description="Свойства узла")

class NodeResponse(BaseModel):
    """Ответ при получении узла"""
    id: str
    type: str
    properties: Dict[str, Any]
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
    node_types: Dict[str, int] = {}
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
    neo4j_connected = init_neo4j()
    
    if neo4j_connected:
        logger.info("✅ Neo4j подключение установлено")
    else:
        logger.warning("⚠️ Neo4j недоступен, используется in-memory режим")

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
    
    # Проверка на существование
    if node_id in in_memory_nodes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Узел с ID {node_id} уже существует"
        )
    
    # Создание узла
    node_data = {
        "id": node_id,
        "type": node.type,
        "properties": node.properties.dict(),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    # Сохранение в Neo4j или in-memory
    if check_neo4j_connection():
        try:
            with neo4j_driver.session() as session:
                session.run(
                    "CREATE (n:GraphitiNode {id: $id, type: $type, properties: $properties, created_at: $created_at})",
                    id=node_id,
                    type=node.type,
                    properties=node.properties.dict(),
                    created_at=datetime.now().isoformat()
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
                    "MATCH (n:GraphitiNode {id: $id}) RETURN n",
                    id=node_id
                )
                record = result.single()
                if record:
                    node = record["n"]
                    return NodeResponse(
                        id=node["id"],
                        type=node["type"],
                        properties=node.get("properties", {}),
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
async def list_nodes(limit: int = 10, offset: int = 0):
    """Получение списка узлов"""
    # Пока только in-memory
    nodes_list = list(in_memory_nodes.values())
    
    # Пагинация
    start = offset
    end = offset + limit
    paginated_nodes = nodes_list[start:end]
    
    return {
        "nodes": paginated_nodes,
        "total": len(nodes_list),
        "limit": limit,
        "offset": offset
    }

@app.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id: str):
    """Удаление узла"""
    
    # Удаление из Neo4j
    if check_neo4j_connection():
        try:
            with neo4j_driver.session() as session:
                result = session.run(
                    "MATCH (n:GraphitiNode {id: $id}) DELETE n RETURN count(n) as deleted",
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