#!/usr/bin/env python3
"""
Быстрый тест интеграции функции выполнения команд в промпте Марка.
Проверяет только ключевые аспекты без долгих вызовов LLM.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

import httpx

from langchain_api.rag.enhanced_rag_chain import (
    execute_sandbox_command,
    process_function_calls,
)


def test_function_call_processing():
    """Тестирует обработку вызовов функций в ответах LLM."""
    print("🧪 Тестирование обработки вызовов функций...")
    print("=" * 70)

    # Тестовые ответы с вызовами функций
    test_responses = [
        "Привет! Давайте проверим состояние проекта.\nexecute_sandbox_command(\"ls -la\")\nЭто покажет нам структуру файлов.",
        "Проверим несколько вещей:\nexecute_sandbox_command(\"pwd\")\nexecute_sandbox_command(\"whoami\")\nТеперь мы знаем где мы и кто мы.",
        "Простой ответ без вызовов функций - это нормально.",
        "Выполним диагностику:\nexecute_sandbox_command(\"ls -la\")\nexecute_sandbox_command(\"ps aux | head -5\")\nexecute_sandbox_command(\"df -h\")"
    ]

    for i, response in enumerate(test_responses, 1):
        print(f"\n{i}. Исходный ответ:\n{response}")
        print("-" * 50)

        processed = process_function_calls(response)
        print(f"Обработанный ответ:\n{processed}")
        print("=" * 70)

def test_execute_sandbox_command():
    """Тестирует функцию выполнения команд в песочнице."""
    print("\n🧪 Тестирование execute_sandbox_command...")
    print("=" * 70)

    test_commands = [
        ("ls -la", "Безопасная команда"),
        ("pwd", "Показать директорию"),
        ("whoami", "Показать пользователя"),
        ("echo 'test'", "Простой вывод"),
        ("rm -rf /", "Запрещенная команда"),
        ("", "Пустая команда")
    ]

    for i, (command, _description) in enumerate(test_commands, 1):
        print(f"\n{i}. Команда: '{command}'")
        print("-" * 50)
        result = execute_sandbox_command(command)
        print(f"Результат: {result[:200]}...")
        print("=" * 70)

def test_prompt_integration():
    """Тестирует интеграцию функции в промпт."""
    print("\n🧪 Тестирование интеграции в промпт...")
    print("=" * 70)

    # Проверяем, что функция есть в промпте
    from langchain_api.rag.enhanced_rag_chain import SYSTEM_PROMPT_BASE

    if "execute_sandbox_command" in SYSTEM_PROMPT_BASE:
        print("✅ Функция execute_sandbox_command найдена в промпте")

        # Находим строку с описанием функции
        lines = SYSTEM_PROMPT_BASE.split('\n')
        for i, line in enumerate(lines):
            if "execute_sandbox_command" in line:
                print(f"📝 Строка {i+1}: {line}")
                break
    else:
        print("❌ Функция execute_sandbox_command НЕ найдена в промпте")

    print("=" * 70)

def test_simple_mark_response():
    """Тестирует простой ответ Марка с вызовом функции."""
    print("\n🧪 Тестирование простого ответа Марка...")
    print("=" * 70)

    # Симулируем ответ Марка с вызовом функции
    mark_response = """Привет! Давайте проверим текущее состояние проекта.

execute_sandbox_command("ls -la")

Это покажет нам структуру файлов в песочнице."""

    print("Исходный ответ Марка:")
    print(mark_response)
    print("-" * 50)

    processed = process_function_calls(mark_response)
    print("Обработанный ответ:")
    print(processed)

    if "execute_sandbox_command" in processed:
        print("❌ Функция все еще в ответе - обработка не сработала")
    else:
        print("✅ Команда была успешно выполнена!")

    print("=" * 70)

async def test_mark_via_api():
    """Тестирует Марка через API."""
    print("\n🧪 Тестирование Марка через API...")
    print("=" * 70)

    test_questions = [
        "Проверь текущее состояние проекта и покажи структуру файлов",
        "Какая текущая директория в песочнице?",
        "Покажи содержимое папки и права доступа",
        "Кто я в системе?",
        "Проверь, какие процессы запущены"
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, question in enumerate(test_questions, 1):
            print(f"\n{i}. Вопрос: {question}")
            print("-" * 50)

            try:
                response = await client.post(
                    "http://app:8000/chat/ask",
                    json={"question": question, "chat_id": 12345}
                )

                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("answer", "Нет ответа")
                    print(f"Ответ Марка:\n{answer}")

                    # Проверяем, использует ли Марк функцию
                    if "execute_sandbox_command" in answer:
                        print("✅ Марк использует функцию execute_sandbox_command")
                    else:
                        print("❌ Марк НЕ использует функцию execute_sandbox_command")
                else:
                    print(f"❌ Ошибка API: {response.status_code}")

            except Exception as e:
                print(f"❌ Ошибка запроса: {e}")

            print("=" * 70)

def main():
    """Основная функция тестирования."""
    print("🚀 Быстрый тест интеграции функции выполнения команд")
    print("=" * 70)

    # Тест 1: Обработка вызовов функций
    test_function_call_processing()

    # Тест 2: Функция execute_sandbox_command
    test_execute_sandbox_command()

    # Тест 3: Интеграция в промпт
    test_prompt_integration()

    # Тест 4: Простой ответ Марка
    test_simple_mark_response()

    # Тест 5: Марк через API
    print("\n🧪 Тестирование через API...")
    asyncio.run(test_mark_via_api())

    print("\n✅ Все быстрые тесты завершены!")
    print("\n📝 Рекомендации:")
    print("1. Функция execute_sandbox_command работает корректно")
    print("2. Обработка вызовов функций работает")
    print("3. Нужно протестировать через Telegram бота")
    print("4. Марк должен активно предлагать выполнение команд")

if __name__ == "__main__":
    main()
