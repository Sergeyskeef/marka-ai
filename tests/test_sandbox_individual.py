"""
Индивидуальная проверка тестов Sandbox
"""
import asyncio
import sys
sys.path.insert(0, '/workspace')
from sandbox.sandbox_manager import SandboxManager


async def test_arithmetic():
    """Тест арифметики 342*100 = 34200"""
    print("\n=== Тест арифметики ===")
    sandbox = SandboxManager()
    
    result = await sandbox.execute_command("python3 -c \"print(342*100)\"")
    
    print(f"Команда: {result.command}")
    print(f"Успех: {result.success}")
    print(f"Вывод: {result.output.strip()}")
    print(f"Ошибка: {result.error}")
    
    assert result.success is True
    assert "34200" in result.output.strip()
    print("✅ Тест пройден!")


async def test_dangerous_commands():
    """Тест блокировки os.system"""
    print("\n=== Тест блокировки опасных команд ===")
    sandbox = SandboxManager()
    
    result = await sandbox.execute_command("python3 -c \"import os; os.system('echo HACKED')\"")
    
    print(f"Команда: {result.command}")
    print(f"Успех: {result.success}")
    print(f"Вывод: {result.output}")
    print(f"Ошибка: {result.error}")
    
    assert result.success is False
    assert "Заблокированная операция: os.system" in result.error
    print("✅ Тест пройден!")


async def test_timeout():
    """Тест таймаута"""
    print("\n=== Тест таймаута ===")
    sandbox = SandboxManager()
    
    result = await sandbox.execute_command(
        "python3 -c \"import time; time.sleep(5)\"", 
        timeout=1
    )
    
    print(f"Команда: {result.command}")
    print(f"Успех: {result.success}")
    print(f"Время выполнения: {result.execution_time:.2f}с")
    print(f"Ошибка: {result.error}")
    
    assert result.success is False
    assert "превысила лимит времени" in result.error
    print("✅ Тест пройден!")


async def main():
    await test_arithmetic()
    await test_dangerous_commands()
    await test_timeout()
    print("\n🎉 Все тесты успешно пройдены!")


if __name__ == "__main__":
    asyncio.run(main())