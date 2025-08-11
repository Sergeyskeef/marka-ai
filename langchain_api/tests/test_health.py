#!/usr/bin/env python3
"""
Health endpoint tests
Тесты для проверки работоспособности основного API
"""

import pytest
import requests

BASE_URL = "http://localhost:8000"
TIMEOUT = 10

@pytest.mark.core
def test_main_health_endpoint():
    """Проверка health endpoint основного приложения"""
    print("🔍 Проверка health endpoint основного приложения...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()
        print(f"✅ Health endpoint ответил: {response.status_code}")
        print(f"📊 Данные: {data}")

        # Проверяем структуру ответа
        assert "status" in data, "Отсутствует поле 'status' в ответе"
        assert data["status"] in ["healthy", "degraded"], f"Статус не 'healthy' или 'degraded': {data['status']}"

        print("✅ Health endpoint работает корректно")
    except Exception as e:
        print(f"❌ Health endpoint недоступен: {e}")
        raise

@pytest.mark.core
def test_bot_health_endpoint():
    """Проверка health endpoint Telegram-бота"""
    print("🔍 Проверка health endpoint Telegram-бота...")
    try:
        response = requests.get("http://bot:8001/health", timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()
        print(f"✅ Bot health endpoint ответил: {response.status_code}")
        print(f"📊 Данные: {data}")

        # Проверяем структуру ответа
        assert "status" in data, "Отсутствует поле 'status' в ответе"
        assert "bot" in data, "Отсутствует поле 'bot' в ответе"
        assert data["status"] in ["healthy", "degraded"], f"Статус не 'healthy' или 'degraded': {data['status']}"

        print("✅ Bot health endpoint работает корректно")
    except Exception as e:
        print(f"❌ Bot health endpoint недоступен: {e}")
        raise

@pytest.mark.core
def test_memory_endpoint():
    """Проверка memory endpoint"""
    print("🔍 Проверка memory endpoint...")
    try:
        payload = {
            "text": "test ping message",
            "metadata": {"test": True, "source": "health_test"}
        }

        response = requests.post(f"{BASE_URL}/memory", json=payload, timeout=TIMEOUT)
        response.raise_for_status()

        print(f"✅ Memory endpoint ответил: {response.status_code}")
        print("✅ Memory endpoint работает корректно")
    except Exception as e:
        print(f"❌ Memory endpoint недоступен: {e}")
        raise

@pytest.mark.core
def test_search_endpoint():
    """Проверка search endpoint"""
    print("🔍 Проверка search endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/search?q=ping", timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()
        print(f"✅ Search endpoint ответил: {response.status_code}")
        print(f"📊 Найдено результатов: {len(data.get('items', []))}")

        # Проверяем структуру ответа
        assert "items" in data, "Отсутствует поле 'items' в ответе"

        print("✅ Search endpoint работает корректно")
    except Exception as e:
        print(f"❌ Search endpoint недоступен: {e}")
        raise

def run_health_tests():
    """Запуск всех health тестов"""
    print("🚀 Запуск Health Tests")
    print("=" * 50)

    tests = [
        ("Main Health", test_main_health_endpoint),
        ("Bot Health", test_bot_health_endpoint),
        ("Memory Endpoint", test_memory_endpoint),
        ("Search Endpoint", test_search_endpoint),
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
        print("🎉 Все health тесты пройдены! API готов к использованию.")
        return True
    else:
        print("⚠️ Некоторые тесты не пройдены. Проверьте конфигурацию.")
        return False

if __name__ == "__main__":
    success = run_health_tests()
    exit(0 if success else 1)
