import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import types

# Ensure required environment variables for imports
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SKIP_GRAPHITI_WAIT", "1")

# Provide a lightweight OpenAI stub to satisfy imports during testing
if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _DummyAsyncOpenAI:  # noqa: D401 - simple stub
        """Stub for AsyncOpenAI that provides no functionality."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            """Do nothing."""

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

# Make project importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.chat import router as chat_router  # noqa: E402
from app.agents import chat_handler  # noqa: E402


test_app = FastAPI()
test_app.include_router(chat_router, prefix="/api")


class StubAgent:
    def __init__(self) -> None:
        self.model = "stub-model"
        self.tools: List[Any] = []
        self.temperature = None
        self.max_tokens = None
        self.chat_calls: List[Dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> Dict[str, Any]:
        self.chat_calls.append(kwargs)
        return {
            "content": f"stub-answer:{kwargs['message']}",
            "metadata": {"agent": "stub"},
            "tool_calls": [],
        }


@pytest.mark.asyncio
async def test_chat_reuses_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "test-session-123"
    stub_agent = StubAgent()

    monkeypatch.setattr(chat_handler, "get_agent", AsyncMock(return_value=stub_agent))

    monkeypatch.setattr(
        chat_handler.memory_manager,
        "search_episodes",
        AsyncMock(return_value={"items": []}),
    )
    monkeypatch.setattr(
        chat_handler.memory_manager,
        "hybrid_search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        chat_handler.memory_manager,
        "save",
        AsyncMock(return_value={"success": True, "id": "mem-1"}),
    )

    create_session_calls: List[Dict[str, Any]] = []
    create_session_mock = AsyncMock()

    async def _capture_session(*, session_id: str, user_id: Optional[str]) -> Dict[str, Any]:
        create_session_calls.append({"session_id": session_id, "user_id": user_id})
        return {"success": True}

    create_session_mock.side_effect = _capture_session
    monkeypatch.setattr(chat_handler.graphiti_adapter, "create_session", create_session_mock)

    create_message_calls: List[Dict[str, Any]] = []
    create_message_mock = AsyncMock()

    async def _capture_message(
        *,
        session_id: str,
        role: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        create_message_calls.append(
            {
                "session_id": session_id,
                "role": role,
                "text": text,
                "metadata": metadata,
            }
        )
        return {"success": True}

    create_message_mock.side_effect = _capture_message
    monkeypatch.setattr(chat_handler.graphiti_adapter, "create_message", create_message_mock)
    monkeypatch.setattr(
        chat_handler.graphiti_adapter,
        "list_edges",
        AsyncMock(return_value={"edges": []}),
    )
    monkeypatch.setattr(
        chat_handler.graphiti_adapter,
        "list_episodes",
        AsyncMock(return_value={"nodes": []}),
    )

    monkeypatch.setattr("app.api.chat.get_last_xtrace", lambda: None)

    payload = {
        "message": "Hello",
        "user_id": "user-1",
        "session_id": session_id,
        "context": {"mode": "chat"},
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/chat", json=payload)
        second = await client.post("/api/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200

    first_body = first.json()
    second_body = second.json()

    assert first_body["session_id"] == session_id
    assert second_body["session_id"] == session_id
    assert first_body["metadata"]["session_id"] == session_id
    assert second_body["metadata"]["session_id"] == session_id

    assert len(stub_agent.chat_calls) == 2
    assert all(call["chat_id"] == session_id for call in stub_agent.chat_calls)

    assert len(create_session_calls) == 2
    assert all(call["session_id"] == session_id for call in create_session_calls)

    assert len(create_message_calls) == 4
    assert all(msg["session_id"] == session_id for msg in create_message_calls)
    assert all(msg["metadata"].get("session_id") == session_id for msg in create_message_calls)

    save_calls = chat_handler.memory_manager.save.await_args_list
    assert len(save_calls) == 2
    for call in save_calls:
        assert call.args[1]["session_id"] == session_id
