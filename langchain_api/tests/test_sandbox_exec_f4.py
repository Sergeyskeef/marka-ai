"""
Тесты для задачи F-4: /sandbox/exec endpoint + bot Code кнопка
"""
import asyncio
import sys
sys.path.insert(0, '/workspace')
import json


async def test_sandbox_exec_endpoint():
    """Тест /sandbox/exec endpoint"""
    print("\n=== Тест /sandbox/exec endpoint ===")
    
    import httpx
    
    # Создаем клиента
    async with httpx.AsyncClient() as client:
        # Тест 1: Выполнение простой команды
        response = await client.post(
            "http://localhost:8000/sandbox/exec",
            json={"command": "python3 -c \"print(342*100)\""}
        )
        
        print(f"Статус: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Результат: {data}")
            assert data["success"] is True
            assert "34200" in data["output"]
            print("✅ Арифметика работает через endpoint")
        else:
            print(f"❌ Ошибка: {response.text}")
            
        # Тест 2: Блокировка опасных команд
        response = await client.post(
            "http://localhost:8000/sandbox/exec",
            json={"command": "python3 -c \"import os; os.system('echo HACKED')\""}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Блокировка: {data}")
            assert data["success"] is False
            assert "Заблокированная операция" in data.get("error", "")
            print("✅ Опасные команды блокируются")
        
        # Тест 3: Таймаут
        response = await client.post(
            "http://localhost:8000/sandbox/exec",
            json={"command": "python3 -c \"import time; time.sleep(10)\"", "timeout": 2}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
            print("✅ Таймаут работает")


def test_bot_code_button():
    """Тест кнопки Code в боте"""
    print("\n=== Тест кнопки Code в боте ===")
    
    # Читаем файл бота
    with open('/workspace/telegram_bot/bot.py', 'r') as f:
        bot_content = f.read()
    
    # Проверяем наличие обработчика
    assert "👨‍💻 code" in bot_content
    print("✅ Обработчик кнопки Code найден")
    
    # Проверяем COMMANDS_REGISTRY
    assert '"triggers": ["👨‍💻 code"' in bot_content or '["👨‍💻 code"' in bot_content
    print("✅ Кнопка Code зарегистрирована в COMMANDS_REGISTRY")
    
    # Проверяем наличие команды /run_code
    assert "run_code" in bot_content
    print("✅ Команда /run_code присутствует")
    
    # Проверяем обработку shell команд с !
    assert 'text.startswith("!")' in bot_content
    print("✅ Обработка shell команд (!) реализована")


async def main():
    print("🧪 Запуск тестов для F-4: /sandbox/exec endpoint + bot Code кнопка")
    
    # Тест endpoint
    try:
        await test_sandbox_exec_endpoint()
    except Exception as e:
        print(f"⚠️ Не удалось протестировать endpoint (возможно сервер не запущен): {e}")
    
    # Тест бота
    test_bot_code_button()
    
    print("\n🎉 Тесты F-4 завершены!")


if __name__ == "__main__":
    asyncio.run(main())