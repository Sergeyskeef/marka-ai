import asyncio
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

_fake_openai = types.ModuleType("openai")
_fake_openai.AsyncOpenAI = type("AsyncOpenAI", (), {})
_fake_openai_types = types.ModuleType("openai.types")
_fake_openai_chat = types.ModuleType("openai.types.chat")
_fake_openai_chat.ChatCompletionMessage = type("ChatCompletionMessage", (), {})
_fake_openai_chat.ChatCompletionMessageToolCallUnion = type("ChatCompletionMessageToolCallUnion", (), {})
_fake_openai_chat_completion = types.ModuleType("openai.types.chat.chat_completion")
_fake_openai_chat_completion.ChatCompletion = type("ChatCompletion", (), {})
_fake_openai_types.chat = _fake_openai_chat
sys.modules.setdefault("openai", _fake_openai)
sys.modules.setdefault("openai.types", _fake_openai_types)
sys.modules.setdefault("openai.types.chat", _fake_openai_chat)
sys.modules.setdefault("openai.types.chat.chat_completion", _fake_openai_chat_completion)

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.agents.mark_agent import MarkAgent, RequestState
from core.memory.memory_manager import memory_manager


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
    state = RequestState(user_id="user-42")

    async def sample_tool(text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sample_tool.called_with = {"text": text, "metadata": metadata}
        return {"text": text, "metadata": metadata}

    sample_tool.called_with = None
    agent.register_tool({"type": "function", "function": {"name": "sample_tool"}}, sample_tool)

    result = await agent.call_tool(
        "sample_tool",
        {"text": "hello", "ignored": "value", "metadata": {"foo": "bar"}},
        state=state,
    )

    assert result["text"] == "hello"
    assert sample_tool.called_with == {"text": "hello", "metadata": result["metadata"]}
    assert result["metadata"]["foo"] == "bar"
    assert result["metadata"]["owner_id"] == "user-42"
    assert result["metadata"]["user_id"] == "user-42"
    assert "timestamp" in result["metadata"]

    with pytest.raises(ValueError):
        await agent.call_tool("unknown_tool", {})

    json_result = await agent.call_tool("sample_tool", json.dumps({"text": "json"}), state=state)
    assert json_result["text"] == "json"


@pytest.mark.asyncio
async def test_chat_state_is_isolated_between_users(monkeypatch):
    class _StubCompletions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            messages = kwargs.get("messages", []) or []
            has_tool_feedback = any(isinstance(msg, dict) and msg.get("role") == "tool" for msg in messages)
            if kwargs.get("tool_choice") == "none" or has_tool_feedback:
                message = types.SimpleNamespace(
                    role="assistant",
                    content="done",
                    tool_calls=[],
                )
                message.model_dump = lambda msg=message: {
                    "role": msg.role,
                    "content": msg.content,
                    "tool_calls": [],
                }
                choice = types.SimpleNamespace(message=message, finish_reason="stop")
            else:
                tool_call = types.SimpleNamespace(
                    id=f"call-{len(self.calls)}",
                    function=types.SimpleNamespace(
                        name="demo_tool",
                        arguments=json.dumps({}),
                    ),
                )
                message = types.SimpleNamespace(
                    role="assistant",
                    content="",
                    tool_calls=[tool_call],
                )
                message.model_dump = lambda msg=message, tc=tool_call: {
                    "role": msg.role,
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    ],
                }
                choice = types.SimpleNamespace(message=message, finish_reason="tool_calls")
            usage = types.SimpleNamespace(total_tokens=1, model_dump=lambda: {"total_tokens": 1})
            return types.SimpleNamespace(choices=[choice], usage=usage)

    completions = _StubCompletions()
    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))
    agent = MarkAgent(client, use_dynamic_prompts=False)

    tool_invocations: list[str | None] = []

    async def demo_tool(metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tool_invocations.append((metadata or {}).get("user_id"))
        return {"ok": True, "user_id": (metadata or {}).get("user_id")}

    agent.register_tool({"type": "function", "function": {"name": "demo_tool"}}, demo_tool)

    tool_log_users: list[str | None] = []

    async def fake_save(text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if metadata and metadata.get("type") == "tool_call":
            tool_log_users.append(metadata.get("user_id"))
        return {"success": True}

    async def fake_retrieve_context(*args, **kwargs):  # pragma: no cover - стаб
        return []

    async def fake_detect_incident(*args, **kwargs):  # pragma: no cover - стаб
        return {}

    async def fake_mine_skill(*args, **kwargs):  # pragma: no cover - стаб
        return {}

    async def fake_get_redis():  # pragma: no cover - стаб
        return None

    monkeypatch.setattr(memory_manager, "save", fake_save)
    monkeypatch.setattr("app.agents.mark_agent.fractal_graph.retrieve_context", fake_retrieve_context)
    monkeypatch.setattr("app.agents.mark_agent.detect_incident", fake_detect_incident)
    monkeypatch.setattr("app.agents.mark_agent.mine_skill", fake_mine_skill)
    monkeypatch.setattr(agent, "_get_redis", fake_get_redis)

    async def run_chat(uid: str):
        return await agent.chat(
            f"hello {uid}",
            user_id=uid,
            override_llm_calls_limit=3,
            override_tool_calls_limit=2,
        )

    responses = await asyncio.gather(
        run_chat("user-a"),
        run_chat("user-b"),
    )

    assert len(completions.calls) == 6
    assert sorted(tool_invocations) == ["user-a", "user-b"]
    assert sorted(u for u in tool_log_users if u) == ["user-a", "user-b"]

    metadata_by_user = {resp.get("metadata", {}).get("user_id"): resp.get("metadata", {}) for resp in responses}
    assert set(metadata_by_user) == {"user-a", "user-b"}
    for meta in metadata_by_user.values():
        assert meta["tool_calls_count"] == 1
        assert meta["llm_calls"] == 3

