"""
E2E тесты для Sandbox Runner
"""
import asyncio
import sys
sys.path.insert(0, '/workspace')
from sandbox.sandbox_manager import SandboxManager


async def test_sandbox_arithmetic():
    """Тест выполнения арифметических операций в песочнице"""
    sandbox = SandboxManager()
    
    # Тест из задачи F-1: 342*100 должно вернуть 34200
    result = await sandbox.execute_command("python3 -c \"print(342*100)\"")
    
    assert result.success is True
    assert "34200" in result.output.strip()
    assert result.error is None or result.error == ""


async def test_sandbox_blocks_dangerous_commands():
    """Тест блокировки опасных команд"""
    sandbox = SandboxManager()
    
    # Тест блокировки os.system
    dangerous_code = """
import os
os.system('echo HACKED')
"""
    
    result = await sandbox.execute_command(f"python3 -c \"{dangerous_code}\"")
    
    # Команда должна либо не выполниться, либо быть заблокирована
    # В текущей реализации нужно добавить блокировку
    assert result.success is False or "HACKED" not in result.output


async def test_sandbox_timeout():
    """Тест таймаута выполнения команд"""
    sandbox = SandboxManager()
    
    # Команда, которая работает долго
    result = await sandbox.execute_command(
        "python3 -c \"import time; time.sleep(60)\"", 
        timeout=2
    )
    
    assert result.success is False
    assert "превысила лимит времени" in result.error


async def test_sandbox_output_limit():
    """Тест ограничения размера вывода"""
    sandbox = SandboxManager()
    
    # Создаем большой вывод
    result = await sandbox.execute_command(
        "python3 -c \"print('x' * 2000000)\""
    )
    
    # Проверяем, что вывод обрезан
    assert len(result.output) <= sandbox.default_max_output + 100  # +100 для сообщения об обрезке
    assert "обрезан" in result.output or len(result.output) < 2000000


if __name__ == "__main__":
    asyncio.run(test_sandbox_arithmetic())
    asyncio.run(test_sandbox_blocks_dangerous_commands())
    asyncio.run(test_sandbox_timeout())
    asyncio.run(test_sandbox_output_limit())
    print("✅ Все тесты пройдены!")