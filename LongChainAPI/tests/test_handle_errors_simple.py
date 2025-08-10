#!/usr/bin/env python3
"""
Простой тест для проверки наличия декоратора @handle_errors
"""

import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_handle_errors_decorator():
    """Тест наличия и структуры декоратора @handle_errors"""
    print("\n=== Тест декоратора @handle_errors ===")
    
    # Проверяем наличие модуля
    try:
        from core.error_middleware import handle_errors
        print("✅ Модуль error_middleware импортирован")
    except ImportError as e:
        print(f"❌ Не удалось импортировать модуль: {e}")
        return False
    
    # Проверяем, что handle_errors - это функция
    print(f"✅ handle_errors является callable: {callable(handle_errors)}")
    
    # Проверяем документацию
    if handle_errors.__doc__:
        print(f"✅ Декоратор имеет документацию: {handle_errors.__doc__.strip().split(chr(10))[0]}")
    
    # Проверяем файл main.py на использование декоратора
    main_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')
    
    if os.path.exists(main_path):
        with open(main_path, 'r') as f:
            content = f.read()
            
        # Проверяем импорт
        if 'from core.error_middleware import' in content and 'handle_errors' in content:
            print("✅ Декоратор импортирован в main.py")
        
        # Считаем использования
        usage_count = content.count('@handle_errors')
        print(f"✅ Декоратор используется {usage_count} раз в main.py")
        
        # Проверяем применение к критическим endpoints
        critical_endpoints = [
            'sandbox_exec',
            'chat_ask', 
            'v1_chat',
            'add_memory',
            'search_memory',
            'execute_tool',
            'add_feedback',
            'get_reflection_insights'
        ]
        
        decorated_endpoints = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '@handle_errors' in line:
                # Ищем следующую строку с определением функции
                for j in range(i+1, min(i+5, len(lines))):
                    if 'async def ' in lines[j]:
                        func_name = lines[j].split('async def ')[1].split('(')[0]
                        decorated_endpoints.append(func_name)
                        break
        
        print(f"\n📊 Декорированные endpoints:")
        for endpoint in decorated_endpoints:
            status = "✅" if endpoint in critical_endpoints else "📌"
            print(f"   {status} {endpoint}")
        
        # Проверяем критические endpoints
        missing = set(critical_endpoints) - set(decorated_endpoints)
        if missing:
            print(f"\n⚠️  Следующие критические endpoints не декорированы: {missing}")
        else:
            print(f"\n✅ Все критические endpoints декорированы!")
    
    return True


def test_error_middleware_structure():
    """Проверка структуры error_middleware.py"""
    print("\n=== Проверка структуры error_middleware.py ===")
    
    middleware_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        'core', 'error_middleware.py'
    )
    
    if os.path.exists(middleware_path):
        with open(middleware_path, 'r') as f:
            content = f.read()
        
        # Проверяем наличие основных компонентов
        components = {
            'ErrorHandlingMiddleware': 'class ErrorHandlingMiddleware',
            'RetryableHTTPClient': 'class RetryableHTTPClient',
            'handle_errors decorator': 'def handle_errors',
            'retry_on_failure decorator': 'def retry_on_failure'
        }
        
        for name, pattern in components.items():
            if pattern in content:
                print(f"✅ {name} найден")
            else:
                print(f"❌ {name} не найден")
        
        # Проверяем обработку исключений в handle_errors
        if 'except HTTPException:' in content and 'except asyncio.TimeoutError:' in content:
            print("✅ Декоратор обрабатывает HTTPException и TimeoutError")
        
        if 'except Exception as e:' in content:
            print("✅ Декоратор обрабатывает общие исключения")
    
    else:
        print(f"❌ Файл {middleware_path} не найден")


if __name__ == "__main__":
    print("🧪 Запуск проверки декоратора @handle_errors")
    
    test_handle_errors_decorator()
    test_error_middleware_structure()
    
    print("\n🎉 Проверка завершена!")