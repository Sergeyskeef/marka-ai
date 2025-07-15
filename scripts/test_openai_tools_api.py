#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой тест для проверки нового подхода с OpenAI Tools API.
Тестирует базовую функциональность tool_calls для выполнения команд.
"""

import sys
import os
import json
import asyncio
import httpx
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_api.utils.openai_proxy_client import create_openai_client

# Создаем клиент OpenAI
openai_client = create_openai_client(timeout=30.0)

# Определяем tools schema
tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_sandbox_command",
            "description": "Run a shell command inside the project's Docker sandbox and return stdout & stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute."
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# Few-shot примеры
few_shot_examples = [
    {
        "role": "user",
        "content": "Проверь файлы в директории"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "execute_sandbox_command",
                "arguments": json.dumps({"command": "ls -la"})
            }
        }]
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "execute_sandbox_command",
        "content": "total 108\ndrwx------  9 1000 1003  4096 Jun 14 10:12 .\ndrwxr-xr-x  1 root root  4096 Jun 20 14:28 ..\n-rw-rw-r--  1 1000 1003  1297 May 31 20:47 README.md\n-rw-rw-r--  1 1000 1003 10995 May 31 09:41 all_tasks.md\n..."
    },
    {
        "role": "assistant",
        "content": "Вот что нашлось в директории:\n\n```\ntotal 108\ndrwx------  9 1000 1003  4096 Jun 14 10:12 .\ndrwxr-xr-x  1 root root  4096 Jun 20 14:28 ..\n-rw-rw-r--  1 1000 1003  1297 May 31 20:47 README.md\n-rw-rw-r--  1 1000 1003 10995 May 31 09:41 all_tasks.md\n```\n\nЭто основные файлы проекта."
    }
]

async def execute_sandbox_command(command: str) -> str:
    """Выполняет команду в песочнице через API."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "http://app:8000/sandbox/exec",
                json={"command": command}
            )
            if response.status_code == 200:
                result = response.json()
                return f"Command: {result['cmd']}\nExit code: {result['returncode']}\n\nSTDOUT:\n{result['stdout'] or '(empty)'}\n\nSTDERR:\n{result['stderr'] or '(empty)'}"
            else:
                return f"API Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Execution Error: {str(e)}"

async def test_tools_api():
    """Тестирует OpenAI Tools API с выполнением команд."""
    print("🧪 Тестирование OpenAI Tools API")
    print("=" * 50)
    
    # Тестовые вопросы
    test_questions = [
        "Проверь файлы в директории",
        "Какая текущая директория?",
        "Кто я в системе?"
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n{i}. Вопрос: {question}")
        print("-" * 30)
        
        try:
            # Первый запрос - получаем tool_calls
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0,
                tools=tools,
                tool_choice="auto",
                messages=[
                    {"role": "system", "content": "Ты - Марк, помощник который может выполнять команды в песочнице. ВСЕГДА используй execute_sandbox_command для получения реальных данных."},
                    *few_shot_examples,
                    {"role": "user", "content": question}
                ]
            )
            
            msg = response.choices[0].message
            print(f"Ответ LLM: {msg.content or 'Нет текста'}")
            
            if msg.tool_calls:
                print(f"✅ Обнаружены tool_calls: {len(msg.tool_calls)}")
                
                # Выполняем команды
                for call in msg.tool_calls:
                    print(f"Выполняем: {call.function.name}({call.function.arguments})")
                    
                    if call.function.name == "execute_sandbox_command":
                        args = json.loads(call.function.arguments)
                        command = args["command"]
                        
                        # Выполняем команду
                        result = await execute_sandbox_command(command)
                        print(f"Результат: {result[:200]}...")
                        
                        # Добавляем результат в историю
                        messages = [
                            {"role": "system", "content": "Ты - Марк, помощник который может выполнять команды в песочнице."},
                            *few_shot_examples,
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": None, "tool_calls": [call]},
                            {"role": "tool", "tool_call_id": call.id, "name": call.function.name, "content": result}
                        ]
                        
                        # Второй запрос - получаем финальный ответ
                        final_response = openai_client.chat.completions.create(
                            model="gpt-4.1-mini",
                            temperature=0,
                            messages=messages
                        )
                        
                        final_msg = final_response.choices[0].message
                        print(f"Финальный ответ: {final_msg.content}")
                        
            else:
                print("❌ Tool_calls НЕ обнаружены")
                print(f"Полный ответ: {msg}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        print("=" * 50)

async def test_forced_tool_call():
    """Тестирует принудительный вызов инструмента."""
    print("\n🧪 Тестирование принудительного tool_call")
    print("=" * 50)
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            tools=tools,
            tool_choice={"name": "execute_sandbox_command"},  # Принудительный вызов
            messages=[
                {"role": "system", "content": "Ты - Марк, помощник который может выполнять команды в песочнице."},
                {"role": "user", "content": "Привет"}
            ]
        )
        
        msg = response.choices[0].message
        print(f"Принудительный tool_call: {msg.tool_calls}")
        
        if msg.tool_calls:
            print("✅ Принудительный tool_call работает!")
        else:
            print("❌ Принудительный tool_call не сработал")
            
    except Exception as e:
        print(f"❌ Ошибка принудительного tool_call: {e}")

def main():
    """Основная функция тестирования."""
    print("🚀 Простой тест OpenAI Tools API")
    print("=" * 50)
    
    # Запускаем тесты
    asyncio.run(test_tools_api())
    asyncio.run(test_forced_tool_call())
    
    print("\n✅ Тестирование завершено!")
    print("\n📝 Результаты:")
    print("1. Проверен базовый tool_call")
    print("2. Проверен принудительный tool_call")
    print("3. Проверена интеграция с API песочницы")

if __name__ == "__main__":
    main() 