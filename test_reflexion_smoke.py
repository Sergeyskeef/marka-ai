#!/usr/bin/env python3
"""
Тест Reflexion Loop α для smoke test
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.append('/app')

async def test_reflexion():
    """Тестирует Reflexion Loop α"""
    try:
        from langchain_api.core.agent.runner import AgentRunner
        
        runner = AgentRunner()
        
        # Тестируем сценарий где первая попытка неуспешна
        result = await runner.try_answer(
            question='Как решить проблему недостатка информации?',
            user_id='smoke_reflexion_user'
        )
        
        print(f'Success: {result["success"]}')
        print(f'Attempts: {result["final_attempt"]}')
        
        # Результат считается успешным если первая попытка была успешной
        return result["success"]
    except Exception as e:
        print(f'Exception: {e}')
        return False

def main():
    """Основная функция"""
    try:
        # Запуск теста
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        test_result = loop.run_until_complete(test_reflexion())
        loop.close()
        
        # Выход с соответствующим кодом
        sys.exit(0 if test_result else 1)
    except Exception as e:
        print(f'Error in main: {e}')
        sys.exit(1)

if __name__ == "__main__":
    main() 