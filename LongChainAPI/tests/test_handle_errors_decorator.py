#!/usr/bin/env python3
"""
Тесты для декоратора @handle_errors
"""

import asyncio
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from core.error_middleware import handle_errors


# Тестовые функции с декоратором
@handle_errors
async def test_success():
    """Функция, которая работает успешно"""
    return {"status": "success", "data": "test"}


@handle_errors
async def test_http_exception():
    """Функция, которая бросает HTTPException"""
    raise HTTPException(status_code=404, detail="Not found")


@handle_errors
async def test_timeout():
    """Функция, которая вызывает таймаут"""
    raise asyncio.TimeoutError("Request timed out")


@handle_errors
async def test_generic_exception():
    """Функция с общей ошибкой"""
    raise ValueError("Something went wrong")


@handle_errors
async def test_division_by_zero():
    """Функция с ошибкой деления на ноль"""
    return 1 / 0


async def run_tests():
    """Запускает тесты декоратора"""
    print("\n=== Тесты декоратора @handle_errors ===")
    
    # Тест 1: Успешное выполнение
    print("\n1. Тест успешного выполнения:")
    try:
        result = await test_success()
        print(f"   ✅ Результат: {result}")
        assert result == {"status": "success", "data": "test"}
    except Exception as e:
        print(f"   ❌ Неожиданная ошибка: {e}")
        assert False
    
    # Тест 2: HTTPException пробрасывается как есть
    print("\n2. Тест HTTPException:")
    try:
        await test_http_exception()
        print("   ❌ Должна была быть ошибка")
        assert False
    except HTTPException as e:
        print(f"   ✅ HTTPException поймана: {e.status_code} - {e.detail}")
        assert e.status_code == 404
        assert e.detail == "Not found"
    
    # Тест 3: Таймаут преобразуется в 504
    print("\n3. Тест таймаута:")
    try:
        await test_timeout()
        print("   ❌ Должна была быть ошибка")
        assert False
    except HTTPException as e:
        print(f"   ✅ Таймаут преобразован в HTTP 504: {e.detail}")
        assert e.status_code == 504
        assert "timeout" in e.detail.lower()
    
    # Тест 4: Общая ошибка преобразуется в 500
    print("\n4. Тест общей ошибки:")
    try:
        await test_generic_exception()
        print("   ❌ Должна была быть ошибка")
        assert False
    except HTTPException as e:
        print(f"   ✅ Ошибка преобразована в HTTP 500: {e.detail}")
        assert e.status_code == 500
        assert "Something went wrong" in e.detail
    
    # Тест 5: Ошибка деления на ноль
    print("\n5. Тест деления на ноль:")
    try:
        await test_division_by_zero()
        print("   ❌ Должна была быть ошибка")
        assert False
    except HTTPException as e:
        print(f"   ✅ Ошибка преобразована в HTTP 500: {e.detail}")
        assert e.status_code == 500
        assert "division by zero" in e.detail
    
    print("\n✅ Все тесты пройдены успешно!")


# Тест работы с реальным endpoint
async def test_with_fastapi():
    """Тест интеграции с FastAPI"""
    print("\n=== Тест интеграции с FastAPI ===")
    
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    app = FastAPI()
    
    @app.get("/test/success")
    @handle_errors
    async def endpoint_success():
        return {"status": "ok"}
    
    @app.get("/test/error")
    @handle_errors
    async def endpoint_error():
        raise ValueError("Test error")
    
    @app.get("/test/timeout")
    @handle_errors
    async def endpoint_timeout():
        raise asyncio.TimeoutError()
    
    client = TestClient(app)
    
    # Тест успешного endpoint
    response = client.get("/test/success")
    print(f"\n1. Успешный endpoint: {response.status_code}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    
    # Тест endpoint с ошибкой
    response = client.get("/test/error")
    print(f"2. Endpoint с ошибкой: {response.status_code}")
    assert response.status_code == 500
    assert "Test error" in response.json()["detail"]
    
    # Тест endpoint с таймаутом
    response = client.get("/test/timeout")
    print(f"3. Endpoint с таймаутом: {response.status_code}")
    assert response.status_code == 504
    assert "timeout" in response.json()["detail"].lower()
    
    print("\n✅ Интеграция с FastAPI работает корректно!")


if __name__ == "__main__":
    print("🧪 Запуск тестов декоратора @handle_errors")
    asyncio.run(run_tests())
    asyncio.run(test_with_fastapi())
    print("\n🎉 Все тесты завершены!")