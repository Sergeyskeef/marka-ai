#!/usr/bin/env python3
"""
Демонстрационный скрипт для проверки работы LLM Integration Hub.

Показывает основные возможности:
- Инициализация хаба
- Получение системного контекста
- Обработка запросов
- Выполнение инструментов
- Анализ состояния системы
"""

import asyncio
import json
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/app/langchain_api')

from core.llm_integration_hub import (
    LLMIntegrationHub,
    LLMRequest,
    LLMResponse,
    get_llm_hub,
    shutdown_llm_hub
)


async def test_llm_integration_hub():
    """Тестирование LLM Integration Hub."""
    print("🚀 Демонстрация LLM Integration Hub")
    print("=" * 50)
    
    try:
        # Получаем глобальный экземпляр хаба
        print("📡 Инициализация LLM Integration Hub...")
        hub = await get_llm_hub()
        
        print(f"✅ Хаб инициализирован: {hub.is_initialized}")
        print(f"📊 Счетчик запросов: {hub.request_count}")
        print(f"📊 Счетчик ответов: {hub.response_count}")
        
        # Получаем системный контекст
        print("\n🔍 Получение системного контекста...")
        system_context = await hub.get_system_context()
        
        print(f"📋 Активные задачи: {len(system_context.active_tasks)}")
        print(f"📋 Последние действия: {len(system_context.recent_actions)}")
        print(f"📋 Доступные инструменты: {len(system_context.available_tools)}")
        print(f"📋 Инсайты: {len(system_context.insights)}")
        
        # Обрабатываем тестовый запрос
        print("\n💬 Обработка тестового запроса...")
        request = LLMRequest(
            prompt="Привет! Расскажи о возможностях системы.",
            priority=0.8,
            temperature=0.7
        )
        
        response = await hub.process_request(request)
        
        print(f"📝 Ответ получен:")
        print(f"   Содержание: {response.content}")
        print(f"   Уверенность: {response.confidence}")
        print(f"   Рассуждение: {response.reasoning}")
        if response.suggestions:
            print(f"   Предложения: {response.suggestions}")
        
        # Получаем доступные инструменты
        print("\n🛠️ Получение доступных инструментов...")
        tools = await hub.get_available_tools()
        
        print(f"📋 Найдено инструментов: {len(tools)}")
        if tools:
            print("   Первые 5 инструментов:")
            for i, tool in enumerate(tools[:5]):
                print(f"   {i+1}. {tool.get('name', 'Unknown')} ({tool.get('type', 'Unknown')})")
        
        # Тестируем выполнение инструмента
        print("\n⚙️ Тестирование выполнения инструмента...")
        tool_call = {
            "name": "test_tool",
            "arguments": {"param1": "value1", "param2": "value2"}
        }
        
        result = await hub.execute_tool_call(tool_call)
        print(f"📊 Результат выполнения: {result}")
        
        # Анализируем состояние системы
        print("\n📈 Анализ состояния системы...")
        system_state = await hub.analyze_system_state()
        
        print(f"📊 Метрики производительности:")
        metrics = system_state.get('performance_metrics', {})
        print(f"   Запросов: {metrics.get('request_count', 0)}")
        print(f"   Ответов: {metrics.get('response_count', 0)}")
        print(f"   Успешность: {metrics.get('success_rate', 0):.2%}")
        
        print(f"📊 Статус компонентов:")
        components = system_state.get('component_status', {})
        for component, status in components.items():
            print(f"   {component}: {status}")
        
        # Получаем текущий контекст
        print("\n🧠 Получение текущего контекста...")
        context = await hub.get_context()
        
        print(f"📋 Размер контекста: {len(str(context))} символов")
        if context:
            print("   Ключи контекста:")
            for key in list(context.keys())[:5]:
                print(f"   - {key}")
        
        # Обновляем контекст
        print("\n🔄 Обновление контекста...")
        updates = {
            "demo_mode": True,
            "last_demo_time": "2024-07-01T12:00:00",
            "demo_metrics": {
                "requests_processed": hub.request_count,
                "responses_generated": hub.response_count
            }
        }
        
        await hub.update_context(updates)
        print("✅ Контекст обновлен")
        
        print("\n🎉 Демонстрация завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка в демонстрации: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Завершаем работу хаба
        print("\n🛑 Завершение работы LLM Integration Hub...")
        await shutdown_llm_hub()
        print("✅ Работа завершена")


async def test_llm_request_processing():
    """Тестирование обработки различных типов запросов."""
    print("\n🧪 Тестирование обработки запросов")
    print("=" * 40)
    
    try:
        hub = await get_llm_hub()
        
        # Тест 1: Простой запрос
        print("\n📝 Тест 1: Простой запрос")
        request1 = LLMRequest(
            prompt="Как дела?",
            priority=0.5
        )
        response1 = await hub.process_request(request1)
        print(f"   Ответ: {response1.content[:100]}...")
        
        # Тест 2: Запрос с контекстом
        print("\n📝 Тест 2: Запрос с контекстом")
        request2 = LLMRequest(
            prompt="Анализируй систему",
            context={"analysis_type": "performance", "depth": "detailed"},
            priority=0.9
        )
        response2 = await hub.process_request(request2)
        print(f"   Ответ: {response2.content[:100]}...")
        
        # Тест 3: Запрос с инструментами
        print("\n📝 Тест 3: Запрос с инструментами")
        request3 = LLMRequest(
            prompt="Покажи доступные инструменты",
            tools=["get_available_tools", "analyze_system_state"],
            priority=0.7
        )
        response3 = await hub.process_request(request3)
        print(f"   Ответ: {response3.content[:100]}...")
        
        print("\n✅ Тестирование запросов завершено")
        
    except Exception as e:
        print(f"❌ Ошибка в тестировании запросов: {e}")
    
    finally:
        await shutdown_llm_hub()


async def test_error_handling():
    """Тестирование обработки ошибок."""
    print("\n🛡️ Тестирование обработки ошибок")
    print("=" * 40)
    
    try:
        hub = await get_llm_hub()
        
        # Тест обработки некорректного запроса
        print("\n📝 Тест обработки некорректного запроса")
        request = LLMRequest(
            prompt="",  # Пустой запрос
            priority=1.5  # Некорректный приоритет
        )
        response = await hub.process_request(request)
        print(f"   Обработан: {response.content[:100]}...")
        
        # Тест выполнения несуществующего инструмента
        print("\n📝 Тест выполнения несуществующего инструмента")
        result = await hub.execute_tool_call({
            "name": "nonexistent_tool",
            "arguments": {}
        })
        print(f"   Результат: {result}")
        
        print("\n✅ Тестирование обработки ошибок завершено")
        
    except Exception as e:
        print(f"❌ Ошибка в тестировании обработки ошибок: {e}")
    
    finally:
        await shutdown_llm_hub()


async def main():
    """Основная функция демонстрации."""
    print("🎯 Демонстрация LLM Integration Hub")
    print("=" * 60)
    
    # Основная демонстрация
    await test_llm_integration_hub()
    
    # Тестирование обработки запросов
    await test_llm_request_processing()
    
    # Тестирование обработки ошибок
    await test_error_handling()
    
    print("\n🎉 Все демонстрации завершены!")


if __name__ == "__main__":
    # Запускаем демонстрацию
    asyncio.run(main()) 