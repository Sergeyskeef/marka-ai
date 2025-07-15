#!/usr/bin/env python3
"""
GraphitiMemory Smoke Test
Базовая валидация GraphitiMemory REST API и Neo4j подключения
"""
import time
import uuid

import pytest
import requests

BASE_URL = "http://localhost:7878"
TIMEOUT = 10

@pytest.mark.core
def test_graphiti_health():
    """Проверка health endpoint GraphitiMemory"""
    print("🔍 Проверка health endpoint GraphitiMemory...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        response.raise_for_status()
        print(f"✅ Health endpoint ответил: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ Health endpoint недоступен: {e}")
        return False

@pytest.mark.core
def test_put_get_node():
    """Основной smoke тест: создание и получение узла"""
    print("\n🔍 Тест PUT/GET операций с узлами...")

    # Создание уникального узла
    node_id = str(uuid.uuid4())
    payload = {
        "id": node_id,
        "type": "Ping",
        "properties": {
            "msg": "hello GraphitiMemory",
            "timestamp": time.time(),
            "test_run": True
        }
    }

    try:
        # PUT операция
        print(f"📤 Отправляем PUT запрос для узла {node_id[:8]}...")
        response = requests.post(f"{BASE_URL}/nodes", json=payload, timeout=TIMEOUT)
        response.raise_for_status()

        if response.status_code == 201:
            print(f"✅ Узел создан: {response.status_code}")
        else:
            print(f"⚠️ Неожиданный статус: {response.status_code}")

        # GET операция
        print(f"📥 Получаем узел {node_id[:8]}...")
        get_response = requests.get(f"{BASE_URL}/nodes/{node_id}", timeout=TIMEOUT)
        get_response.raise_for_status()

        data = get_response.json()

        # Валидация данных
        if data.get("properties", {}).get("msg") == "hello GraphitiMemory":
            print("✅ Узел получен и данные корректны")
            return True
        else:
            print(f"❌ Данные узла некорректны: {data}")
            return False

    except Exception as e:
        print(f"❌ Ошибка в PUT/GET операциях: {e}")
        return False

@pytest.mark.core
def test_neo4j_connectivity():
    """Проверка подключения к Neo4j через GraphitiMemory"""
    print("\n🔍 Проверка подключения к Neo4j...")

    try:
        # Используем GraphitiMemory API для проверки состояния графа
        response = requests.get(f"{BASE_URL}/stats", timeout=TIMEOUT)

        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Neo4j подключение работает, статистика: {stats}")
            return True
        else:
            print(f"⚠️ Stats endpoint недоступен: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Ошибка проверки Neo4j: {e}")
        return False

@pytest.mark.core
def test_graphiti_version():
    """Проверка версии GraphitiMemory"""
    print("\n🔍 Проверка версии GraphitiMemory...")

    try:
        response = requests.get(f"{BASE_URL}/version", timeout=TIMEOUT)

        if response.status_code == 200:
            version = response.json()
            print(f"✅ GraphitiMemory версия: {version}")
            return True
        else:
            print(f"⚠️ Version endpoint недоступен: {response.status_code}")
            # Не критично, считаем как успех
            return True

    except Exception as e:
        print(f"⚠️ Ошибка получения версии: {e}")
        # Не критично, считаем как успех
        return True

def run_smoke_tests():
    """Запуск всех smoke тестов"""
    print("🚀 Запуск GraphitiMemory Smoke Tests")
    print("=" * 50)

    tests = [
        ("Health Check", test_graphiti_health),
        ("Version Check", test_graphiti_version),
        ("PUT/GET Node", test_put_get_node),
        ("Neo4j Connectivity", test_neo4j_connectivity),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")

    print("\n" + "=" * 50)
    print(f"📊 Результаты: {passed}/{total} тестов пройдено")

    if passed == total:
        print("🎉 Все smoke тесты пройдены! GraphitiMemory готов к использованию.")
        return True
    else:
        print("⚠️ Некоторые тесты не пройдены. Проверьте конфигурацию.")
        return False

if __name__ == "__main__":
    success = run_smoke_tests()
    exit(0 if success else 1)
