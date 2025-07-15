#!/usr/bin/env python3
"""
GraphitiMemory pytest smoke tests
Pytest совместимые тесты для валидации GraphitiMemory
"""
import pytest
import requests
import uuid
import time
import json
from typing import Dict, Any

BASE_URL = "http://localhost:7878"
TIMEOUT = 10

@pytest.fixture(scope="module")
def graphiti_service():
    """Фикстура для проверки доступности GraphitiMemory сервиса"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        response.raise_for_status()
        return True
    except Exception as e:
        pytest.skip(f"GraphitiMemory сервис недоступен: {e}")

class TestGraphitiMemorySmoke:
    """Smoke тесты для GraphitiMemory"""
    
    def test_graphiti_health(self, graphiti_service):
        """Тест health endpoint GraphitiMemory"""
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        assert response.status_code == 200
        print("✅ Health endpoint работает корректно")
    
    def test_graphiti_version(self, graphiti_service):
        """Тест версии GraphitiMemory"""
        response = requests.get(f"{BASE_URL}/version", timeout=TIMEOUT)
        
        # Version endpoint может быть недоступен в некоторых версиях
        if response.status_code == 200:
            version_data = response.json()
            assert isinstance(version_data, dict)
            print(f"✅ GraphitiMemory версия: {version_data}")
        else:
            print("⚠️ Version endpoint недоступен (не критично)")
    
    def test_put_get_node(self, graphiti_service):
        """Основной smoke тест: создание и получение узла"""
        # Создание уникального узла
        node_id = str(uuid.uuid4())
        payload = {
            "id": node_id,
            "type": "TestNode",
            "properties": {
                "msg": "hello GraphitiMemory",
                "timestamp": time.time(),
                "test_run": True,
                "pytest_test": True
            }
        }
        
        # PUT операция - создание узла
        response = requests.post(f"{BASE_URL}/nodes", json=payload, timeout=TIMEOUT)
        assert response.status_code == 201, f"Неожиданный статус создания узла: {response.status_code}"
        
        # GET операция - получение узла
        get_response = requests.get(f"{BASE_URL}/nodes/{node_id}", timeout=TIMEOUT)
        assert get_response.status_code == 200, f"Неожиданный статус получения узла: {get_response.status_code}"
        
        # Валидация данных
        data = get_response.json()
        assert data.get("properties", {}).get("msg") == "hello GraphitiMemory"
        assert data.get("properties", {}).get("pytest_test") == True
        assert data.get("type") == "TestNode"
        
        print(f"✅ Узел {node_id[:8]} создан и получен корректно")
    
    def test_neo4j_connectivity(self, graphiti_service):
        """Тест подключения к Neo4j через GraphitiMemory"""
        # Попытка получить статистику графа
        response = requests.get(f"{BASE_URL}/stats", timeout=TIMEOUT)
        
        # Stats endpoint может быть недоступен в некоторых версиях
        if response.status_code == 200:
            stats = response.json()
            assert isinstance(stats, dict)
            print(f"✅ Neo4j подключение работает, статистика: {stats}")
        else:
            # Альтернативная проверка - попытка создать простой узел
            test_node_id = str(uuid.uuid4())
            test_payload = {
                "id": test_node_id,
                "type": "ConnectivityTest",
                "properties": {"test": "neo4j_connectivity"}
            }
            
            conn_response = requests.post(f"{BASE_URL}/nodes", json=test_payload, timeout=TIMEOUT)
            assert conn_response.status_code == 201, "Neo4j подключение не работает"
            print("✅ Neo4j подключение работает (проверено через создание узла)")
    
    def test_graphiti_endpoints_discovery(self, graphiti_service):
        """Тест обнаружения доступных endpoints GraphitiMemory"""
        # Список потенциальных endpoints для проверки
        endpoints_to_check = [
            ("/health", "Health check"),
            ("/version", "Version info"),
            ("/stats", "Graph statistics"),
            ("/nodes", "Nodes management"),
        ]
        
        available_endpoints = []
        
        for endpoint, description in endpoints_to_check:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=TIMEOUT)
                if response.status_code in [200, 405]:  # 405 = Method Not Allowed, но endpoint существует
                    available_endpoints.append((endpoint, description))
            except:
                pass
        
        assert len(available_endpoints) >= 2, "Слишком мало доступных endpoints"
        print(f"✅ Найдено доступных endpoints: {len(available_endpoints)}")
        
        for endpoint, description in available_endpoints:
            print(f"  - {endpoint}: {description}")

class TestGraphitiMemoryIntegration:
    """Интеграционные тесты GraphitiMemory"""
    
    def test_multiple_nodes_crud(self, graphiti_service):
        """Тест CRUD операций с несколькими узлами"""
        node_ids = []
        
        # Создание нескольких узлов
        for i in range(3):
            node_id = str(uuid.uuid4())
            payload = {
                "id": node_id,
                "type": "BatchTestNode",
                "properties": {
                    "batch_index": i,
                    "msg": f"batch node {i}",
                    "timestamp": time.time()
                }
            }
            
            response = requests.post(f"{BASE_URL}/nodes", json=payload, timeout=TIMEOUT)
            assert response.status_code == 201, f"Ошибка создания узла {i}"
            node_ids.append(node_id)
        
        # Проверка существования всех узлов
        for i, node_id in enumerate(node_ids):
            response = requests.get(f"{BASE_URL}/nodes/{node_id}", timeout=TIMEOUT)
            assert response.status_code == 200, f"Узел {i} не найден"
            
            data = response.json()
            assert data.get("properties", {}).get("batch_index") == i
        
        print(f"✅ Batch CRUD операции с {len(node_ids)} узлами выполнены успешно")

# Интеграция с pytest discovery
def test_graphiti_smoke_discovery():
    """Тест обнаружения GraphitiMemory для pytest discovery"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ GraphitiMemory обнаружен и доступен")
        else:
            pytest.skip("GraphitiMemory недоступен")
    except:
        pytest.skip("GraphitiMemory недоступен")

if __name__ == "__main__":
    # Для запуска напрямую
    pytest.main([__file__, "-v"]) 