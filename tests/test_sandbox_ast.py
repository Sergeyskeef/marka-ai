#!/usr/bin/env python3
"""
Тесты для проверки AST анализа в SandboxManager
"""

import asyncio
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox.sandbox_manager import SandboxManager


async def test_ast_checks():
    """Тестирует проверку Python кода через AST"""
    print("\n=== Тест AST проверок в SandboxManager ===")
    
    sandbox_manager = SandboxManager()
    
    # Тест 1: Безопасный код
    print("\n1. Тест безопасного кода:")
    result = await sandbox_manager.execute_command('python3 -c "print(342 * 100)"')
    print(f"   Результат: {result.output.strip()}")
    print(f"   Успех: {result.success}")
    assert result.success, "Безопасный код должен выполняться"
    assert "34200" in result.output, "Должен быть правильный результат"
    
    # Тест 2: Блокировка импорта os
    print("\n2. Тест блокировки импорта os:")
    result = await sandbox_manager.execute_command('python3 -c "import os; print(os.getcwd())"')
    print(f"   Ошибка: {result.error}")
    print(f"   Успех: {result.success}")
    assert not result.success, "Импорт os должен быть заблокирован"
    assert "Заблокирован импорт модуля: os" in result.error
    
    # Тест 3: Блокировка os.system
    print("\n3. Тест блокировки os.system:")
    result = await sandbox_manager.execute_command('python3 -c "import os; os.system(\'ls\')"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "os.system должен быть заблокирован"
    
    # Тест 4: Блокировка subprocess
    print("\n4. Тест блокировки subprocess:")
    result = await sandbox_manager.execute_command('python3 -c "import subprocess; subprocess.run([\'ls\'])"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "subprocess должен быть заблокирован"
    assert "subprocess" in result.error
    
    # Тест 5: Блокировка eval
    print("\n5. Тест блокировки eval:")
    result = await sandbox_manager.execute_command('python3 -c "eval(\'print(1)\')"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "eval должен быть заблокирован"
    assert "eval" in result.error
    
    # Тест 6: Блокировка exec
    print("\n6. Тест блокировки exec:")
    result = await sandbox_manager.execute_command('python3 -c "exec(\'print(1)\')"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "exec должен быть заблокирован"
    assert "exec" in result.error
    
    # Тест 7: Блокировка __import__
    print("\n7. Тест блокировки __import__:")
    result = await sandbox_manager.execute_command('python3 -c "__import__(\'os\').system(\'ls\')"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "__import__ должен быть заблокирован"
    assert "__import__" in result.error
    
    # Тест 8: Блокировка open
    print("\n8. Тест блокировки open:")
    result = await sandbox_manager.execute_command('python3 -c "open(\'/etc/passwd\').read()"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "open должен быть заблокирован"
    assert "open" in result.error
    
    # Тест 9: Сложные математические операции разрешены
    print("\n9. Тест сложных математических операций:")
    result = await sandbox_manager.execute_command('python3 -c "import math; print(math.sqrt(16))"')
    print(f"   Результат: {result.output.strip() if result.success else result.error}")
    # math не заблокирован, поэтому должно работать
    
    # Тест 10: List comprehensions и lambda разрешены
    print("\n10. Тест list comprehensions и lambda:")
    result = await sandbox_manager.execute_command('python3 -c "print([(lambda x: x**2)(i) for i in range(5)])"')
    print(f"   Результат: {result.output.strip()}")
    print(f"   Успех: {result.success}")
    assert result.success, "List comprehensions и lambda должны работать"
    
    # Тест 11: Синтаксическая ошибка
    print("\n11. Тест синтаксической ошибки:")
    result = await sandbox_manager.execute_command('python3 -c "print(]"')
    print(f"   Ошибка: {result.error}")
    assert not result.success, "Синтаксическая ошибка должна быть поймана"
    assert "Синтаксическая ошибка" in result.error
    
    print("\n✅ Все AST тесты пройдены успешно!")


async def test_direct_ast_check():
    """Тест прямой проверки AST метода"""
    print("\n=== Тест прямой проверки _check_python_ast ===")
    
    sandbox_manager = SandboxManager()
    
    # Безопасный код
    assert sandbox_manager._check_python_ast("print('hello')") is None
    assert sandbox_manager._check_python_ast("x = 2 + 2") is None
    assert sandbox_manager._check_python_ast("[i**2 for i in range(10)]") is None
    
    # Опасный код
    assert "os" in sandbox_manager._check_python_ast("import os")
    assert "subprocess" in sandbox_manager._check_python_ast("from subprocess import call")
    assert "eval" in sandbox_manager._check_python_ast("eval('print(1)')")
    assert "exec" in sandbox_manager._check_python_ast("exec('x = 1')")
    assert "__import__" in sandbox_manager._check_python_ast("__import__('os')")
    assert "open" in sandbox_manager._check_python_ast("f = open('file.txt')")
    
    # Проверка синтаксических ошибок
    assert "Синтаксическая ошибка" in sandbox_manager._check_python_ast("print(")
    
    print("✅ Прямые AST проверки работают корректно!")


if __name__ == "__main__":
    print("🧪 Запуск тестов AST проверок в SandboxManager")
    asyncio.run(test_ast_checks())
    asyncio.run(test_direct_ast_check())
    print("\n🎉 Все тесты пройдены!")