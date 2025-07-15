#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Демонстрация системы автономной разработки Марка.
Показывает полный цикл разработки: анализ → план → код → тесты → валидация.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_api.sandbox.autonomous_development_system import AutonomousDevelopmentSystem

def demo_autonomous_development():
    """Демонстрация автономной разработки."""
    print("🚀 ДЕМОНСТРАЦИЯ СИСТЕМЫ АВТОНОМНОЙ РАЗРАБОТКИ МАРКА")
    print("=" * 60)
    
    # Инициализация системы
    dev_system = AutonomousDevelopmentSystem()
    
    # Пример задачи для разработки
    task_description = "Создать функцию для работы с JSON файлами: чтение, запись, валидация"
    
    print(f"📋 Задача: {task_description}")
    print("-" * 60)
    
    # 1. Анализ требований
    print("🔍 1. Анализ требований...")
    requirements = dev_system.task_analyzer.analyze_task(task_description)
    print(f"Результат анализа:\n{requirements}")
    print()
    
    # 2. Создание плана реализации
    print("📋 2. Создание плана реализации...")
    plan = dev_system.implementation_planner.create_plan(task_description)
    print(f"План реализации:\n{plan}")
    print()
    
    # 3. Генерация кода
    print("⚒️ 3. Генерация кода...")
    code_result = dev_system.code_generator.generate_code(task_description)
    print(f"Результат генерации кода:\n{code_result}")
    print()
    
    # 4. Автоматическое тестирование
    print("🧪 4. Автоматическое тестирование...")
    test_result = dev_system.auto_tester.run_tests(".")
    print(f"Результат тестирования:\n{test_result}")
    print()
    
    # 5. Валидация качества
    print("✅ 5. Валидация качества кода...")
    quality_result = dev_system.quality_validator.validate_code(".")
    print(f"Результат валидации:\n{quality_result}")
    print()
    
    # 6. Код-ревью
    print("👀 6. Автоматический код-ревью...")
    review_result = dev_system.code_reviewer.review_code(".")
    print(f"Результат код-ревью:\n{review_result}")
    print()
    
    # 7. Полный цикл разработки
    print("🚀 7. Полный цикл автономной разработки...")
    full_result = dev_system.develop_feature(task_description)
    print(f"Результат полного цикла:\n{full_result}")
    print()
    
    print("✅ Демонстрация завершена!")
    print("=" * 60)

def demo_individual_components():
    """Демонстрация отдельных компонентов."""
    print("\n🔧 ДЕМОНСТРАЦИЯ ОТДЕЛЬНЫХ КОМПОНЕНТОВ")
    print("=" * 60)
    
    dev_system = AutonomousDevelopmentSystem()
    
    # Демонстрация TaskAnalyzer
    print("📊 TaskAnalyzer - анализ сложности:")
    complexity = dev_system.task_analyzer.estimate_complexity("Создать простую функцию")
    print(f"Сложность: {complexity}")
    
    # Демонстрация декомпозиции
    print("\n📋 Декомпозиция задачи:")
    requirements = dev_system.task_analyzer.analyze_task("Создать веб-приложение")
    subtasks = dev_system.task_analyzer.decompose_task(requirements)
    print(f"Подзадачи: {len(subtasks)} найдено")
    
    print("\n✅ Демонстрация компонентов завершена!")

if __name__ == "__main__":
    try:
        demo_autonomous_development()
        demo_individual_components()
        print("\n🎉 Все демонстрации прошли успешно!")
    except Exception as e:
        print(f"❌ Ошибка в демонстрации: {e}")
        import traceback
        traceback.print_exc() 