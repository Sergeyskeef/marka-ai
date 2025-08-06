#!/usr/bin/env python3
"""
Ручное тестирование безопасности песочницы
"""

import asyncio
from sandbox.sandbox_manager import SandboxManager


async def test_security():
    sm = SandboxManager()
    
    print("=== Тестирование безопасности песочницы ===\n")
    
    # Тест 1: Разрешенные команды
    print("1. Тест разрешенных команд:")
    allowed_commands = [
        "echo 'Hello, World!'",
        "ls -la",
        "pwd",
        "python3 -c \"print('Test')\"",
    ]
    
    for cmd in allowed_commands:
        result = await sm.execute_command(cmd)
        status = "✅" if result.success else "❌"
        print(f"  {status} {cmd[:50]}... - {result.error if result.error else 'OK'}")
    
    print("\n2. Тест блокировки shell команд:")
    blocked_commands = [
        "nc -l 8080",
        "sudo ls",
        "rm -rf /",
        "cat /etc/passwd",
        "docker ps",
        "systemctl status",
    ]
    
    for cmd in blocked_commands:
        result = await sm.execute_command(cmd)
        status = "✅" if not result.success else "❌"
        print(f"  {status} {cmd[:50]}... - {result.error if result.error else 'ДОЛЖНА БЫТЬ ЗАБЛОКИРОВАНА!'}")
    
    print("\n3. Тест блокировки Python импортов:")
    blocked_python = [
        "python3 -c \"import os; os.system('ls')\"",
        "python3 -c \"import subprocess\"",
        "python3 -c \"import socket\"",
        "python3 -c \"import requests\"",
        "python3 -c \"eval('print(1)')\"",
        "python3 -c \"exec('print(1)')\"",
        "python3 -c \"__import__('os')\"",
    ]
    
    for cmd in blocked_python:
        result = await sm.execute_command(cmd)
        status = "✅" if not result.success else "❌"
        print(f"  {status} {cmd[:50]}... - {result.error if result.error else 'ДОЛЖНА БЫТЬ ЗАБЛОКИРОВАНА!'}")
    
    print("\n4. Тест разрешенного Python кода:")
    allowed_python = [
        "python3 -c \"print(2 + 2)\"",
        "python3 -c \"import math; print(math.pi)\"",
        "python3 -c \"import json; print(json.dumps({'test': 1}))\"",
    ]
    
    for cmd in allowed_python:
        result = await sm.execute_command(cmd)
        status = "✅" if result.success else "⚠️"
        if result.success:
            print(f"  {status} {cmd[:50]}... - Output: {result.output.strip()}")
        else:
            print(f"  {status} {cmd[:50]}... - {result.error}")


if __name__ == "__main__":
    asyncio.run(test_security())