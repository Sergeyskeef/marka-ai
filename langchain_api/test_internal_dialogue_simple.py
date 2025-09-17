#!/usr/bin/env python3
"""
Простой тест системы внутреннего диалога

Запуск: python test_internal_dialogue_simple.py
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_internal_dialogue():
    """Тестирует основные компоненты системы внутреннего диалога"""
    
    print("🧪 Тестирование системы внутреннего диалога...")
    
    try:
        # Тест 1: Импорт модулей
        print("\n1️⃣ Тест импорта модулей...")
        
        from app.internal_dialogue.manager import InternalDialogueManager
        from app.internal_dialogue.thinking_handler import ThinkingMessageHandler
        from app.internal_dialogue.auto_solver import AutoProblemSolver
        from app.internal_dialogue.dialogue_state import DialogueState
        
        print("✅ Все модули успешно импортированы")
        
        # Тест 2: Создание компонентов
        print("\n2️⃣ Тест создания компонентов...")
        
        # Создаем моки
        class MockAgent:
            def __init__(self):
                self.model = "gpt-4.1-mini"
        
        class MockMemory:
            async def save_episode(self, *args, **kwargs):
                return {"id": "test_episode"}
            
            async def find_similar_episodes(self, *args, **kwargs):
                return []
        
        # Создаем компоненты
        thinking_handler = ThinkingMessageHandler()
        auto_solver = AutoProblemSolver(MockAgent(), MockMemory())
        dialogue_state = DialogueState()
        
        print("✅ Все компоненты успешно созданы")
        
        # Тест 3: Тест ThinkingMessageHandler
        print("\n3️⃣ Тест ThinkingMessageHandler...")
        
        # Запускаем обработчик
        await thinking_handler.start()
        
        # Тестируем показ сообщений
        message_id = await thinking_handler.show_thinking_step(
            chat_id=123,
            text="Тестовое сообщение мышления",
            lifetime=5
        )
        
        print(f"✅ Сообщение мышления отправлено, ID: {message_id}")
        
        # Тестируем прогресс
        progress_id = await thinking_handler.show_progress(
            chat_id=123,
            current_step=2,
            total_steps=5,
            description="Тестовый шаг"
        )
        
        print(f"✅ Прогресс показан, ID: {progress_id}")
        
        # Проверяем статистику
        active_count = thinking_handler.get_active_messages_count()
        queue_length = thinking_handler.get_queue_length()
        
        print(f"📊 Активных сообщений: {active_count}, в очереди: {queue_length}")
        
        # Тест 4: Тест AutoProblemSolver
        print("\n4️⃣ Тест AutoProblemSolver...")
        
        # Тестируем авторешение
        has_solution = await auto_solver.has_solution("привет, как дела?")
        print(f"✅ Проверка авторешения: {has_solution}")
        
        # Тестируем решение проблемы
        solution = await auto_solver.solve_problem("привет!")
        print(f"✅ Авторешение: {solution.success}, метод: {solution.method}")
        
        # Тестируем статистику паттернов
        patterns_stats = auto_solver.get_patterns_stats()
        print(f"📊 Статистика паттернов: {patterns_stats['total_patterns']} паттернов")
        
        # Тест 5: Тест DialogueState
        print("\n5️⃣ Тест DialogueState...")
        
        # Создаем сессию
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        print(f"✅ Сессия создана: {session_id}")
        
        # Обновляем сессию
        dialogue_state.update_session(
            session_id,
            message_processed=True,
            auto_solved=True,
            success=True,
            duration=5.0
        )
        
        # Завершаем сессию
        dialogue_state.end_session(session_id)
        
        # Получаем статистику
        stats = dialogue_state.get_performance_stats()
        print(f"📊 Общая статистика: {stats['total_sessions']} сессий")
        
        # Тест 6: Тест InternalDialogueManager
        print("\n6️⃣ Тест InternalDialogueManager...")
        
        # Создаем менеджер
        manager = InternalDialogueManager(
            mark_agent=MockAgent(),
            memory_adapter=MockMemory(),
            thinking_handler=thinking_handler,
            auto_solver=auto_solver
        )
        
        print("✅ Менеджер внутреннего диалога создан")
        
        # Тестируем обработку простого сообщения
        result = await manager.process_with_thinking(
            user_message="привет!",
            chat_id=123,
            user_id=456
        )
        
        print(f"✅ Обработка завершена: {result.success}")
        print(f"📊 Авторешено: {result.auto_solved}")
        print(f"⏱️ Время: {result.total_duration:.2f}с")
        print(f"🧠 Шагов: {len(result.thinking_steps)}")
        
        # Тестируем статистику
        dialogue_stats = await manager.get_dialogue_stats()
        print(f"📊 Статистика диалогов: {dialogue_stats}")
        
        # Очищаем и останавливаем
        await thinking_handler.clear_all_messages()
        await thinking_handler.stop()
        
        print("\n🎉 Все тесты пройдены успешно!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Основная функция"""
    print("🚀 Запуск тестирования системы внутреннего диалога Марка")
    print("=" * 60)
    
    success = await test_internal_dialogue()
    
    print("=" * 60)
    if success:
        print("🎯 Тестирование завершено успешно!")
        print("✅ Система внутреннего диалога готова к работе")
    else:
        print("💥 Тестирование завершено с ошибками")
        print("❌ Требуется исправление проблем")
    
    return success

if __name__ == "__main__":
    # Запускаем тест
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
