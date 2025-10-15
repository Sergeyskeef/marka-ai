"""Tests for autonomous agent memory integration."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "tiktoken" not in sys.modules:
    class _DummyTokenizer:
        def encode(self, text: str) -> bytes:
            return text.encode("utf-8")

    def _fake_encoding_for_model(_: str) -> _DummyTokenizer:
        return _DummyTokenizer()

    def _fake_get_encoding(_: str) -> _DummyTokenizer:
        return _DummyTokenizer()

    import types

    sys.modules["tiktoken"] = types.SimpleNamespace(
        encoding_for_model=_fake_encoding_for_model,
        get_encoding=_fake_get_encoding,
    )

import types

# Provide lightweight stubs for optional dependencies pulled in by MarkAgent
openai_stub = types.SimpleNamespace()
openai_stub.AsyncOpenAI = object
chat_module = types.SimpleNamespace(
    ChatCompletionMessage=object,
    ChatCompletionMessageToolCallUnion=object,
    chat_completion=types.SimpleNamespace(ChatCompletion=object),
)
openai_types = types.SimpleNamespace(chat=chat_module)
sys.modules.setdefault("openai", openai_stub)
sys.modules.setdefault("openai.types", openai_types)
sys.modules.setdefault("openai.types.chat", chat_module)
sys.modules.setdefault(
    "openai.types.chat.chat_completion",
    chat_module.chat_completion,
)

redis_asyncio_stub = types.SimpleNamespace(Redis=object)
redis_module = types.SimpleNamespace(asyncio=redis_asyncio_stub)
sys.modules.setdefault("redis", redis_module)
sys.modules.setdefault("redis.asyncio", redis_asyncio_stub)

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SKIP_GRAPHITI_WAIT", "1")

from app.autonomy import autonomous_agent  # noqa: E402


@pytest.mark.asyncio
async def test_autonomous_mode_saves_episode_and_triggers_reflection(monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent should persist episodes and trigger reflection after tasks complete."""

    mark_agent = SimpleNamespace(
        generate_response=AsyncMock(return_value="Задача выполнена"),
    )

    memory_adapter = SimpleNamespace(
        save_skill=AsyncMock(return_value={"success": True, "id": "skill-1"}),
        save_episode=AsyncMock(
            side_effect=[
                {"success": True, "id": "episode-task"},
                {"success": True, "id": "episode-learn"},
            ]
        ),
    )

    learning_cycle = SimpleNamespace(
        reflect_on_episode=AsyncMock(),
    )

    class _StubPlanner:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        async def create_project_plan(self, project_description: str) -> dict[str, object]:
            return {
                "tasks": [
                    {
                        "name": "Test task",
                        "description": "Выполнить простое действие",
                        "type": "general",
                    }
                ]
            }

    class _StubCodeGenerator:
        def __init__(self, *_: object, **__: object) -> None:
            pass

    class _StubTestRunner:
        def __init__(self, *_: object, **__: object) -> None:
            pass

    monkeypatch.setattr(autonomous_agent, "TaskPlanner", _StubPlanner)
    monkeypatch.setattr(autonomous_agent, "CodeGenerator", _StubCodeGenerator)
    monkeypatch.setattr(autonomous_agent, "TestRunner", _StubTestRunner)

    agent = autonomous_agent.AutonomousAgent(
        mark_agent=mark_agent,
        memory_adapter=memory_adapter,
        learning_cycle=learning_cycle,
    )

    result = await agent.start_autonomous_mode("Тестовый проект")

    assert result["status"] == "completed"
    assert memory_adapter.save_episode.await_count == 2

    saved_calls = memory_adapter.save_episode.await_args_list
    assert saved_calls[0].kwargs["situation"].startswith("Выполнение задачи")
    assert saved_calls[1].kwargs["situation"].startswith("Completed task")

    learning_cycle.reflect_on_episode.assert_awaited_once_with("episode-learn")
