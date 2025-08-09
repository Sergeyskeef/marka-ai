"""
Тесты для OpenAI Agents SDK интеграции
"""

import asyncio
import pytest
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.mark_agent import MarkAgent
from app.agents.tools import create_openai_tool, tool_registry
from app.agents.chat_handler import enhanced_chat, simple_chat
from openai import AsyncOpenAI


@pytest.mark.asyncio
async def test_mark_agent_basic():
    """Тест базовой функциональности агента"""
    client = AsyncOpenAI()
    agent = MarkAgent(client, model="gpt-5-mini")
    
    result = await agent.chat("Привет! Как дела?")
    
    assert "content" in result
    assert result["content"] is not None
    assert len(result["content"]) > 0
    assert "metadata" in result
    assert result["metadata"]["model"] == "gpt-5-mini"


@pytest.mark.asyncio
async def test_tool_creation():
    """Тест создания инструментов"""
    
    @create_openai_tool
    def test_function(param1: str, param2: int = 5) -> str:
        """Тестовая функция для проверки
        
        Args:
            param1: Первый параметр
            param2: Второй параметр с значением по умолчанию
        """
        return f"Result: {param1}, {param2}"
    
    definition = test_function._openai_tool_definition
    
    assert definition["type"] == "function"
    assert definition["function"]["name"] == "test_function"
    assert "Тестовая функция для проверки" in definition["function"]["description"]
    assert "param1" in definition["function"]["parameters"]["properties"]
    assert "param2" in definition["function"]["parameters"]["properties"]
    assert definition["function"]["parameters"]["required"] == ["param1"]


@pytest.mark.asyncio
async def test_enhanced_chat():
    """Тест улучшенного чата"""
    result = await enhanced_chat(
        "Расскажи про Python",
        chat_id=123,
        mode="chat",
        user_id="test_user"
    )
    
    assert "content" in result
    assert result["content"] is not None
    assert "metadata" in result
    assert result["metadata"]["mode"] == "chat"
    assert result["metadata"]["user_id"] == "test_user"


@pytest.mark.asyncio 
async def test_simple_chat_compatibility():
    """Тест обратной совместимости simple_chat"""
    result = await simple_chat("Что такое AI?")
    
    assert "answer" in result  # Ключ для совместимости
    assert result["answer"] is not None
    assert "metadata" in result


@pytest.mark.asyncio
async def test_memory_tools():
    """Тест инструментов памяти"""
    from app.agents.memory_tools import search_memory, save_to_memory
    
    # Тест сохранения
    save_result = await save_to_memory("Тестовая информация для памяти")
    assert save_result is not None
    
    # Тест поиска
    search_result = await search_memory("тест", limit=3)
    assert search_result is not None


if __name__ == "__main__":
    # Запуск тестов
    asyncio.run(test_mark_agent_basic())
    asyncio.run(test_tool_creation())
    print("✅ Все базовые тесты пройдены!")