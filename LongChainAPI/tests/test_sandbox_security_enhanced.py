"""
Расширенные тесты безопасности песочницы
"""

import pytest
import asyncio
from sandbox.sandbox_manager import SandboxManager


@pytest.fixture
def sandbox_manager():
    """Создает экземпляр SandboxManager для тестов"""
    return SandboxManager()


class TestShellCommandSecurity:
    """Тесты безопасности shell команд"""
    
    @pytest.mark.asyncio
    async def test_allowed_commands(self, sandbox_manager):
        """Проверка разрешенных команд"""
        allowed_commands = [
            "echo 'Hello, World!'",
            "ls -la",
            "pwd",
            "date",
            "python3 --version",
            "pip list",
        ]
        
        for cmd in allowed_commands:
            result = await sandbox_manager.execute_command(cmd)
            assert result.error != "Команда не в белом списке", f"Команда {cmd} должна быть разрешена"
    
    @pytest.mark.asyncio
    async def test_blocked_commands(self, sandbox_manager):
        """Проверка блокировки опасных команд"""
        blocked_commands = [
            "nc -l 8080",  # сетевые утилиты
            "nmap localhost",
            "telnet example.com",
            "ssh user@host",
            "systemctl restart nginx",
            "service apache2 stop",
            "sudo apt-get update",
            "su root",
            "chmod 777 /etc/passwd",
            "docker exec -it container bash",
        ]
        
        for cmd in blocked_commands:
            result = await sandbox_manager.execute_command(cmd)
            assert not result.success, f"Команда {cmd} должна быть заблокирована"
            assert result.error is not None
    
    @pytest.mark.asyncio
    async def test_dangerous_patterns(self, sandbox_manager):
        """Проверка опасных паттернов"""
        dangerous_commands = [
            "rm -rf /",
            "rm -rf /*",
            "cat /etc/passwd",
            "cat /etc/shadow",
            "echo 'test' > /dev/null",
            "kill -9 1",
            "pkill python",
        ]
        
        for cmd in dangerous_commands:
            result = await sandbox_manager.execute_command(cmd)
            assert not result.success, f"Опасная команда {cmd} должна быть заблокирована"
            assert "опасный паттерн" in result.error.lower()


class TestPythonCodeSecurity:
    """Тесты безопасности Python кода"""
    
    @pytest.mark.asyncio
    async def test_blocked_imports(self, sandbox_manager):
        """Проверка блокировки опасных импортов"""
        blocked_codes = [
            "python3 -c \"import os; os.system('ls')\"",
            "python3 -c \"import subprocess; subprocess.call(['ls'])\"",
            "python3 -c \"import sys; sys.exit()\"",
            "python3 -c \"import socket; socket.socket()\"",
            "python3 -c \"import urllib.request; urllib.request.urlopen('http://example.com')\"",
            "python3 -c \"import requests; requests.get('http://example.com')\"",
            "python3 -c \"import httpx; httpx.get('http://example.com')\"",
        ]
        
        for cmd in blocked_codes:
            result = await sandbox_manager.execute_command(cmd)
            assert not result.success, f"Код с опасным импортом должен быть заблокирован: {cmd}"
            assert "заблокирован" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_blocked_builtins(self, sandbox_manager):
        """Проверка блокировки опасных встроенных функций"""
        blocked_codes = [
            "python3 -c \"eval('print(1)')\"",
            "python3 -c \"exec('print(1)')\"",
            "python3 -c \"compile('print(1)', 'test', 'exec')\"",
            "python3 -c \"__import__('os')\"",
            "python3 -c \"getattr(__builtins__, 'eval')\"",
            "python3 -c \"setattr(object, 'test', 1)\"",
            "python3 -c \"globals()['__builtins__']\"",
            "python3 -c \"locals()['__name__']\"",
        ]
        
        for cmd in blocked_codes:
            result = await sandbox_manager.execute_command(cmd)
            assert not result.success, f"Код с опасной функцией должен быть заблокирован: {cmd}"
    
    @pytest.mark.asyncio
    async def test_blocked_file_operations(self, sandbox_manager):
        """Проверка блокировки операций с файлами"""
        blocked_codes = [
            "python3 -c \"open('/etc/passwd', 'r')\"",
            "python3 -c \"with open('/tmp/test.txt', 'w') as f: f.write('test')\"",
        ]
        
        for cmd in blocked_codes:
            result = await sandbox_manager.execute_command(cmd)
            assert not result.success, f"Операция с файлами должна быть заблокирована: {cmd}"
    
    @pytest.mark.asyncio
    async def test_allowed_python_code(self, sandbox_manager):
        """Проверка разрешенного Python кода"""
        allowed_codes = [
            "python3 -c \"print('Hello, World!')\"",
            "python3 -c \"print(2 + 2)\"",
            "python3 -c \"import math; print(math.pi)\"",
            "python3 -c \"import json; print(json.dumps({'test': 1}))\"",
            "python3 -c \"from collections import defaultdict; d = defaultdict(int)\"",
        ]
        
        for cmd in allowed_codes:
            result = await sandbox_manager.execute_command(cmd)
            # Проверяем что нет ошибок безопасности (может быть другая ошибка если нет python3)
            if result.error:
                assert "заблокирован" not in result.error.lower(), f"Безопасный код не должен блокироваться: {cmd}"


class TestEdgeCases:
    """Тесты граничных случаев"""
    
    @pytest.mark.asyncio
    async def test_command_injection_attempts(self, sandbox_manager):
        """Проверка попыток инъекции команд"""
        injection_attempts = [
            "echo 'test' && rm -rf /",
            "echo 'test'; cat /etc/passwd",
            "echo 'test' | nc -l 8080",
            "echo `cat /etc/passwd`",
            "echo $(sudo su)",
        ]
        
        for cmd in injection_attempts:
            result = await sandbox_manager.execute_command(cmd)
            # Должны быть заблокированы либо по паттерну, либо по команде
            assert not result.success or "cat" not in result.output
    
    @pytest.mark.asyncio
    async def test_bypass_attempts(self, sandbox_manager):
        """Проверка попыток обхода защиты"""
        bypass_attempts = [
            "python3 -c \"__builtins__.__import__('os').system('ls')\"",
            "python3 -c \"type(eval)('print(1)')\"",
            "python3 -c \"().__class__.__bases__[0].__subclasses__()\"",
        ]
        
        for cmd in bypass_attempts:
            result = await sandbox_manager.execute_command(cmd)
            assert not result.success, f"Попытка обхода должна быть заблокирована: {cmd}"


class TestResourceLimits:
    """Тесты лимитов ресурсов"""
    
    @pytest.mark.asyncio
    async def test_timeout(self, sandbox_manager):
        """Проверка таймаута выполнения"""
        # Команда которая выполняется долго
        result = await sandbox_manager.execute_command(
            "python3 -c \"import time; time.sleep(10)\"",
            timeout=2
        )
        
        # Должна быть прервана по таймауту
        assert not result.success or result.execution_time < 5
    
    @pytest.mark.asyncio
    async def test_output_limit(self, sandbox_manager):
        """Проверка лимита на размер вывода"""
        # Генерируем большой вывод
        result = await sandbox_manager.execute_command(
            "python3 -c \"print('A' * 2000000)\""
        )
        
        # Проверяем что вывод обрезан
        if result.success:
            assert len(result.output) <= sandbox_manager.default_max_output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])