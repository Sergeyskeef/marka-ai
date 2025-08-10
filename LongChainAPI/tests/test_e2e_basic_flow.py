#!/usr/bin/env python3
"""
E2E тест базового потока: бот → план → сохранение → подтверждение
"""

import asyncio
import pytest
import requests
import time
from typing import Dict, Any

# URL для тестирования
APP_URL = "http://localhost:8000"
BOT_URL = "http://bot:8001"

class TestE2EBasicFlow:
    """Тестирование базового E2E потока"""
    
    def test_health_checks(self):
        """Проверка здоровья всех сервисов"""
        # Проверяем FastAPI приложение
        response = requests.get(f"{APP_URL}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        
        # Проверяем бота
        response = requests.get(f"{BOT_URL}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_tools_registry(self):
        """Проверка регистрации инструментов"""
        response = requests.get(f"{APP_URL}/tools", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "tools" in data
        assert "total" in data
        assert "categories" in data
        
        # Проверяем, что есть хотя бы один инструмент
        assert data["total"] > 0
        assert len(data["tools"]) > 0
    
    def test_memory_operations(self):
        """Проверка операций с памятью"""
        # Добавляем информацию в память
        memory_data = {
            "text": "Тестовое сообщение для E2E теста",
            "metadata": {
                "test": True,
                "timestamp": time.time(),
                "source": "e2e_test"
            }
        }
        
        response = requests.post(f"{APP_URL}/memory", json=memory_data, timeout=10)
        assert response.status_code == 200
        
        # Ищем информацию в памяти
        search_query = "тестовое сообщение"
        response = requests.get(f"{APP_URL}/search?q={search_query}", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        
        # Проверяем, что наш тестовый элемент найден
        found = False
        for item in data["items"]:
            if "тестовое сообщение" in item.get("text", "").lower():
                found = True
                break
        
        assert found, "Тестовое сообщение не найдено в памяти"
    
    def test_chat_with_memory(self):
        """Проверка чата с использованием памяти"""
        # Сначала добавляем информацию о пользователе
        user_info = {
            "text": "Меня зовут Тестовый Пользователь, я разработчик Python",
            "metadata": {
                "chat_id": 12345,
                "type": "user_info"
            }
        }
        
        response = requests.post(f"{APP_URL}/memory", json=user_info, timeout=10)
        assert response.status_code == 200
        
        # Задаем вопрос, который должен использовать память
        chat_request = {
            "question": "Как меня зовут и чем я занимаюсь?",
            "chat_id": 12345,
            "mode": "chat"
        }
        
        response = requests.post(f"{APP_URL}/chat/ask", json=chat_request, timeout=30)
        assert response.status_code == 200
        
        data = response.json()
        assert "answer" in data
        assert "context_used" in data
        assert "memory_added" in data
        
        # Проверяем, что контекст был использован
        assert data["context_used"] == True
        
        # Проверяем, что ответ содержит информацию о пользователе
        answer = data["answer"].lower()
        assert "тестовый" in answer or "пользователь" in answer or "разработчик" in answer
    
    def test_prompt_modes(self):
        """Проверка различных режимов промптов"""
        modes = ["chat", "code", "plan"]
        
        for mode in modes:
            chat_request = {
                "question": "Привет!",
                "chat_id": 99999,
                "mode": mode
            }
            
            response = requests.post(f"{APP_URL}/chat/ask", json=chat_request, timeout=30)
            assert response.status_code == 200
            
            data = response.json()
            assert "answer" in data
            assert len(data["answer"]) > 0
    
    def test_metrics_endpoints(self):
        """Проверка endpoints метрик"""
        # Проверяем Prometheus метрики
        response = requests.get(f"{APP_URL}/metrics/prometheus", timeout=10)
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        
        # Проверяем сводку метрик
        response = requests.get(f"{APP_URL}/metrics/summary", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "uptime_seconds" in data
        assert "metrics" in data

def run_e2e_tests():
    """Запуск всех E2E тестов"""
    print("🧪 Запуск E2E тестов...")
    
    test_instance = TestE2EBasicFlow()
    
    # Запускаем тесты по порядку
    tests = [
        ("Проверка здоровья сервисов", test_instance.test_health_checks),
        ("Регистрация инструментов", test_instance.test_tools_registry),
        ("Операции с памятью", test_instance.test_memory_operations),
        ("Чат с памятью", test_instance.test_chat_with_memory),
        ("Режимы промптов", test_instance.test_prompt_modes),
        ("Endpoints метрик", test_instance.test_metrics_endpoints),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            print(f"  🔍 {test_name}...")
            test_func()
            print(f"  ✅ {test_name} - УСПЕХ")
            results.append((test_name, True, None))
        except Exception as e:
            print(f"  ❌ {test_name} - ОШИБКА: {e}")
            results.append((test_name, False, str(e)))
    
    # Выводим итоги
    print("\n📊 Результаты E2E тестов:")
    successful = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅" if success else "❌"
        print(f"  {status} {test_name}")
        if error:
            print(f"     Ошибка: {error}")
    
    print(f"\n🎯 Итого: {successful}/{total} тестов прошли успешно")
    
    if successful == total:
        print("🎉 Все E2E тесты прошли успешно!")
        return True
    else:
        print("⚠️ Некоторые тесты не прошли")
        return False

if __name__ == "__main__":
    success = run_e2e_tests()
    exit(0 if success else 1) 