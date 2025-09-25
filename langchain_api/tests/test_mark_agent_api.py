import json
import os
import sys
import types
from typing import Any, Dict, Optional

import pytest


class _FakeTokenizer:
    def encode(self, text: str) -> list[str]:
        return list(text or "")


_fake_tiktoken = types.ModuleType("tiktoken")
_fake_tiktoken.encoding_for_model = lambda model: _FakeTokenizer()
_fake_tiktoken.get_encoding = lambda name: _FakeTokenizer()
sys.modules.setdefault("tiktoken", _fake_tiktoken)

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.agents.mark_agent import MarkAgent


@pytest.fixture(scope="session", autouse=True)
def wait_graphiti():  # noqa: D401 - переопределяем тяжёлую фикстуру из conftest
    """No-op fixture to bypass external Graphiti dependency in unit tests."""

class _DummyCompletions:
    async def create(self, **kwargs):  # pragma: no cover - не вызывается в тестах
        raise NotImplementedError


class _DummyChat:
    def __init__(self):
        self.completions = _DummyCompletions()


class _DummyClient:
    def __init__(self):
        self.chat = _DummyChat()


@pytest.mark.asyncio
async def test_generate_response_proxies_to_chat(monkeypatch):
    agent = MarkAgent(_DummyClient(), model="test-model", temperature=0.6)
    original_temperature = agent.temperature

    async def fake_chat(message: str, **kwargs: Any) -> Dict[str, Any]:
        fake_chat.called_with = (message, kwargs)
        return {"content": "ok", "metadata": {"model": "test-model"}}

    fake_chat.called_with = None
    monkeypatch.setattr(agent, "chat", fake_chat)

    response = await agent.generate_response(
        "Hello",
        user_id="user-1",
        chat_id=42,
        context=[{"role": "user", "content": "Prev"}],
        use_tools=False,
        temperature=0.2,
        max_tokens=128,
        llm_calls_limit=3,
        tool_calls_limit=5,
    )

    assert response == "ok"
    assert fake_chat.called_with is not None
    message, kwargs = fake_chat.called_with
    assert message == "Hello"
    assert kwargs["user_id"] == "user-1"
    assert kwargs["chat_id"] == 42
    assert kwargs["context"][0]["content"] == "Prev"
    assert kwargs["use_tools"] is False
    assert kwargs["override_max_tokens"] == 128
    assert kwargs["override_llm_calls_limit"] == 3
    assert kwargs["override_tool_calls_limit"] == 5
    assert agent.temperature == original_temperature


@pytest.mark.asyncio
async def test_call_tool_filters_arguments_and_returns_result():
    agent = MarkAgent(_DummyClient())
    agent._current_user_id = "user-42"

    async def sample_tool(text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sample_tool.called_with = {"text": text, "metadata": metadata}
        return {"text": text, "metadata": metadata}

    sample_tool.called_with = None
    agent.register_tool({"type": "function", "function": {"name": "sample_tool"}}, sample_tool)

    result = await agent.call_tool(
        "sample_tool",
        {"text": "hello", "ignored": "value", "metadata": {"foo": "bar"}},
    )

    assert result["text"] == "hello"
    assert sample_tool.called_with == {"text": "hello", "metadata": result["metadata"]}
    assert result["metadata"]["foo"] == "bar"
    assert result["metadata"]["owner_id"] == "user-42"
    assert result["metadata"]["user_id"] == "user-42"
    assert "timestamp" in result["metadata"]

    with pytest.raises(ValueError):
        await agent.call_tool("unknown_tool", {})

    json_result = await agent.call_tool("sample_tool", json.dumps({"text": "json"}))
    assert json_result["text"] == "json"
