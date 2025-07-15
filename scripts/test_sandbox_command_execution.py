#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функции выполнения команд в песочнице.
Проверяет интеграцию execute_sandbox_command в промпте Марка.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_api.rag.enhanced_rag_chain import (
    execute_sandbox_command,
    process_function_calls,
)


def test_execute_sandbox_command():
    """Тестирует функцию выполнения команд в песочнице."""
    print("🧪 Тестирование execute_sandbox_command...")

    # Тест 1: Безопасная команда
    print("\n1. Тест безопасной команды 'ls -la':")
    result = execute_sandbox_command("ls -la")
    print(f"Результат: {result[:200]}...")

    # Тест 2: Запрещенная команда
    print("\n2. Тест запрещенной команды 'rm -rf /':")
    result = execute_sandbox_command("rm -rf /")
    print(f"Результат: {result}")

    # Тест 3: Пустая команда
    print("\n3. Тест пустой команды:")
    result = execute_sandbox_command("")
    print(f"Результат: {result}")

    # Тест 4: Команда для проверки статуса
    print("\n4. Тест команды 'pwd':")
    result = execute_sandbox_command("pwd")
    print(f"Результат: {result}")

def test_process_function_calls():
    """Тестирует обработку вызовов функций в ответе LLM."""
    print("\n🧪 Тестирование process_function_calls...")

    # Тест 1: Ответ с вызовом функции
    test_answer = """Привет! Давайте проверим состояние проекта.
execute_sandbox_command("ls -la")
Это покажет нам структуру файлов."""

    print("\n1. Тест обработки вызова функции:")
    print(f"Исходный ответ: {test_answer}")
    processed = process_function_calls(test_answer)
    print(f"Обработанный ответ: {processed[:300]}...")

    # Тест 2: Ответ без вызовов функций
    test_answer2 = "Простой ответ без вызовов функций."
    print("\n2. Тест ответа без вызовов функций:")
    processed2 = process_function_calls(test_answer2)
    print(f"Результат: {processed2}")

    # Тест 3: Ответ с несколькими вызовами
    test_answer3 = """Проверим несколько вещей:
execute_sandbox_command("pwd")
execute_sandbox_command("ls -la")
execute_sandbox_command("whoami")"""

    print("\n3. Тест нескольких вызовов функций:")
    processed3 = process_function_calls(test_answer3)
    print(f"Обработанный ответ: {processed3[:500]}...")

def test_integration_with_rag():
    """Тестирует интеграцию с RAG системой."""
    print("\n🧪 Тестирование интеграции с RAG...")

    # Имитируем вопрос, который должен вызвать выполнение команды
    question = "Проверь текущее состояние проекта и покажи структуру файлов"

    print(f"Вопрос: {question}")
    print("Этот тест показывает, как Марк должен реагировать на такие запросы.")
    print("В реальном использовании Марк должен предложить выполнить команду.")

def main():
    """Основная функция тестирования."""
    print("🚀 Запуск тестов функции выполнения команд в песочнице")
    print("=" * 60)

    try:
        test_execute_sandbox_command()
        test_process_function_calls()
        test_integration_with_rag()

        print("\n✅ Все тесты завершены успешно!")
        print("\n📝 Рекомендации:")
        print("1. Протестируйте функцию через Telegram бота")
        print("2. Проверьте, что Марк предлагает выполнить команды")
        print("3. Убедитесь, что запрещенные команды блокируются")

    except Exception as e:
        print(f"\n❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
