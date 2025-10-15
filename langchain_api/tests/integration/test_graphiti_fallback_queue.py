import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock
import types

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SKIP_GRAPHITI_WAIT", "1")

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _DummyAsyncOpenAI:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    openai_stub.AsyncOpenAI = _DummyAsyncOpenAI

    chat_module = types.ModuleType("openai.types.chat")
    chat_module.ChatCompletionMessage = object
    chat_module.ChatCompletionMessageToolCallUnion = object

    chat_completion_module = types.ModuleType("openai.types.chat.chat_completion")
    chat_completion_module.ChatCompletion = object

    types_module = types.ModuleType("openai.types")
    chat_module.chat_completion = chat_completion_module
    types_module.chat = chat_module

    sys.modules["openai"] = openai_stub
    sys.modules["openai.types"] = types_module
    sys.modules["openai.types.chat"] = chat_module
    sys.modules["openai.types.chat.chat_completion"] = chat_completion_module
    openai_stub.types = types_module

if "tiktoken" not in sys.modules:
    class _DummyTokenizer:
        def encode(self, text: str) -> bytes:
            return text.encode("utf-8")

    def _fake_encoding_for_model(_: str) -> _DummyTokenizer:
        return _DummyTokenizer()

    def _fake_get_encoding(_: str) -> _DummyTokenizer:
        return _DummyTokenizer()

    sys.modules["tiktoken"] = types.SimpleNamespace(
        encoding_for_model=_fake_encoding_for_model,
        get_encoding=_fake_get_encoding,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents import chat_handler  # noqa: E402
from app.utils import fallback_queue  # noqa: E402


class DummyRedis:
    def __init__(self) -> None:
        self.queue: List[str] = []

    async def ping(self) -> bool:
        return True

    async def rpush(self, key: str, value: str) -> int:
        self.queue.append(value)
        return len(self.queue)

    async def lpop(self, key: str) -> Any:
        if not self.queue:
            return None
        return self.queue.pop(0)


class StubAgent:
    def __init__(self) -> None:
        self.tools: List[Any] = []
        self.chat_calls: List[Dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> Dict[str, Any]:
        self.chat_calls.append(kwargs)
        return {
            "content": f"stub-answer:{kwargs['message']}",
            "metadata": {"agent": "stub"},
            "tool_calls": [],
        }


@pytest.mark.asyncio
async def test_graphiti_failure_goes_to_fallback_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_agent = StubAgent()
    monkeypatch.setattr(chat_handler, "get_agent", AsyncMock(return_value=stub_agent))

    monkeypatch.setattr(chat_handler.memory_manager, "hybrid_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_handler.memory_manager, "search_episodes", AsyncMock(return_value={"items": []}))
    monkeypatch.setattr(chat_handler.memory_manager, "save", AsyncMock(return_value={"success": True, "id": "mem-1"}))

    dummy_redis = DummyRedis()
    fallback_queue.reset_redis_client()
    monkeypatch.setattr(fallback_queue, "_redis", dummy_redis, raising=False)

    fail_first_call = {"flag": True}

    async def create_session_side_effect(*, session_id: str, user_id: str | None) -> Dict[str, Any]:
        if fail_first_call["flag"]:
            fail_first_call["flag"] = False
            raise RuntimeError("graphiti-down")
        return {"success": True, "session_id": session_id, "user_id": user_id}

    create_session_mock = AsyncMock(side_effect=create_session_side_effect)
    monkeypatch.setattr(chat_handler.graphiti_adapter, "create_session", create_session_mock)
    monkeypatch.setattr(fallback_queue.graphiti_adapter, "create_session", create_session_mock)

    create_message_calls: List[Dict[str, Any]] = []

    async def create_message_side_effect(*, session_id: str, role: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        create_message_calls.append({
            "session_id": session_id,
            "role": role,
            "text": text,
            "metadata": metadata,
        })
        return {"success": True}

    create_message_mock = AsyncMock(side_effect=create_message_side_effect)
    monkeypatch.setattr(chat_handler.graphiti_adapter, "create_message", create_message_mock)
    monkeypatch.setattr(fallback_queue.graphiti_adapter, "create_message", create_message_mock)

    monkeypatch.setattr(chat_handler.graphiti_adapter, "list_edges", AsyncMock(return_value={"edges": []}))
    monkeypatch.setattr(chat_handler.graphiti_adapter, "list_episodes", AsyncMock(return_value={"nodes": []}))

    response = await chat_handler.enhanced_chat(
        question="Hello fallback",
        chat_id=123,
        user_id="user-1",
        mode="chat",
        session_id="session-xyz",
    )

    assert response["metadata"].get("graphiti_fallback") is True
    assert "graphiti-down" in response["metadata"].get("graphiti_fallback_reason", "")

    assert len(dummy_redis.queue) == 1
    payload = dummy_redis.queue[0]
    assert isinstance(payload, str)

    data = json.loads(payload)
    assert data["session_id"] == "session-xyz"
    assert data["user_id"] == "user-1"
    assert data.get("attempts") == 0
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"

    processed = await fallback_queue.process_queue_once(retry_delay=0.0)
    assert processed is True
    assert dummy_redis.queue == []

    assert create_session_mock.await_count == 2
    assert len(create_message_calls) == 2
