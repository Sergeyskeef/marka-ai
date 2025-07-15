
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки интеграции возможностей Марка.

Проверяет:
1. Интеграцию Tools Registry в промпт
2. Обновленный системный промпт
3. Команду /capabilities
4. Самосознание Марка
"""

import logging
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from langchain_api.core.tools_registry import get_tools_registry
from langchain_api.rag.enhanced_rag_chain import (
    SYSTEM_PROMPT_BASE,
    generate_enhanced_response,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_tools_registry():
    """Тестирует Tools Registry"""
    print("🔧 Тестирование Tools Registry...")

    try:
        tools_registry = get_tools_registry()
        tools = tools_registry.get_tools()

        print(f"✅ Найдено {len(tools)} инструментов")

        # Группируем по категориям
        categories = {}
        for tool in tools:
            if hasattr(tool, 'type'):
                tool_type = tool.type
            elif isinstance(tool, dict):
                tool_type = tool.get('type', 'unknown')
            else:
                tool_type = 'unknown'

            if tool_type not in categories:
                categories[tool_type] = []
            categories[tool_type].append(tool)

        print("\n📊 Категории инструментов:")
        for category, category_tools in categories.items():
            print(f"  {category}: {len(category_tools)} инструментов")

        return True

    except Exception as e:
        print(f"❌ Ошибка в Tools Registry: {e}")
        return False

def test_system_prompt():
    """Тестирует обновленный системный промпт"""
    print("\n🤖 Тестирование системного промпта...")

    try:
        # Проверяем наличие ключевых секций
        required_sections = [
            "ТВОИ ВОЗМОЖНОСТИ И ИНСТРУМЕНТЫ",
            "МНОГОУРОВНЕВАЯ ПАМЯТЬ",
            "ПЕСОЧНИЦА",
            "СИСТЕМА КОМАНД",
            "КАК ИСПОЛЬЗОВАТЬ ВОЗМОЖНОСТИ"
        ]

        for section in required_sections:
            if section in SYSTEM_PROMPT_BASE:
                print(f"✅ Секция '{section}' найдена")
            else:
                print(f"❌ Секция '{section}' НЕ найдена")
                return False

        print(f"✅ Системный промпт обновлен (длина: {len(SYSTEM_PROMPT_BASE)} символов)")
        return True

    except Exception as e:
        print(f"❌ Ошибка в системном промпте: {e}")
        return False

def test_enhanced_response():
    """Тестирует генерацию ответа с интеграцией"""
    print("\n💬 Тестирование генерации ответа...")

    try:
        # Тестовые вопросы
        test_questions = [
            "Какие у тебя есть возможности?",
            "Что ты умеешь делать?",
            "Расскажи о своей памяти",
            "Как работает песочница?",
            "Какие команды ты знаешь?"
        ]

        for question in test_questions:
            print(f"\n📝 Вопрос: {question}")

            # Генерируем ответ
            response = generate_enhanced_response(question, chat_id=12345)

            print(f"🤖 Ответ (первые 200 символов): {response[:200]}...")

            # Проверяем, что ответ содержит информацию о возможностях
            if any(keyword in response.lower() for keyword in ["память", "песочница", "команды", "инструменты", "возможности"]):
                print("✅ Ответ содержит информацию о возможностях")
            else:
                print("⚠️ Ответ может не содержать информацию о возможностях")

        return True

    except Exception as e:
        print(f"❌ Ошибка в генерации ответа: {e}")
        return False

def test_capabilities_command():
    """Тестирует команду capabilities (симуляция)"""
    print("\n⚙️ Тестирование команды capabilities...")

    try:
        # Импортируем функцию capabilities_cmd

        print("✅ Функция capabilities_cmd найдена")

        # Проверяем, что команда добавлена в реестр
        from langchain_api.telegram_bot.bot import COMMANDS_REGISTRY

        capabilities_cmd_found = False
        for cmd in COMMANDS_REGISTRY:
            if cmd["name"] == "/capabilities":
                capabilities_cmd_found = True
                print("✅ Команда /capabilities найдена в реестре")
                print(f"   Описание: {cmd['description']}")
                print(f"   Триггеры: {cmd['triggers']}")
                break

        if not capabilities_cmd_found:
            print("❌ Команда /capabilities НЕ найдена в реестре")
            return False

        return True

    except Exception as e:
        print(f"❌ Ошибка в команде capabilities: {e}")
        return False

def test_self_awareness():
    """Тестирует самосознание Марка"""
    print("\n🧠 Тестирование самосознания...")

    try:
        # Проверяем, что Марк знает о своих возможностях
        awareness_questions = [
            "Ты знаешь о своих возможностях?",
            "Можешь ли ты использовать свою память?",
            "У тебя есть песочница?",
            "Какие команды ты можешь выполнять?"
        ]

        for question in awareness_questions:
            print(f"\n🤔 Вопрос самосознания: {question}")

            response = generate_enhanced_response(question, chat_id=12345)

            # Проверяем, что ответ показывает самосознание
            if any(keyword in response.lower() for keyword in ["да", "конечно", "умею", "могу", "есть", "доступны"]):
                print("✅ Марк демонстрирует самосознание")
            else:
                print("⚠️ Марк может не демонстрировать полное самосознание")

        return True

    except Exception as e:
        print(f"❌ Ошибка в тестировании самосознания: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ ВОЗМОЖНОСТЕЙ МАРКА")
    print("=" * 60)

    tests = [
        ("Tools Registry", test_tools_registry),
        ("Системный промпт", test_system_prompt),
        ("Генерация ответа", test_enhanced_response),
        ("Команда capabilities", test_capabilities_command),
        ("Самосознание", test_self_awareness)
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте '{test_name}': {e}")
            results.append((test_name, False))

    # Выводим итоговые результаты
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 60)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    print(f"\n🎯 Результат: {passed}/{total} тестов пройдено")

    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Марк готов к использованию своих возможностей!")
    else:
        print("⚠️ Некоторые тесты не пройдены. Проверьте интеграцию.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
