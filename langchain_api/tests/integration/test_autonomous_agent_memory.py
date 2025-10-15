"""Integration test for autonomous agent plan persistence helpers."""

import json
import os
import sys
import types
from typing import Any, Dict, List, Optional

import pytest

# Provide lightweight OpenAI stubs to satisfy imports during testing
if "openai" not in sys.modules:  # pragma: no cover - import guard for tests
    openai_stub = types.ModuleType("openai")

    class _DummyAsyncOpenAI:  # pragma: no cover - placeholder
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

    openai_stub.AsyncOpenAI = _DummyAsyncOpenAI

    types_module = types.ModuleType("openai.types")
    chat_module = types.ModuleType("openai.types.chat")
    chat_completion_module = types.ModuleType("openai.types.chat.chat_completion")

    class _ChatCompletionMessage:  # pragma: no cover - placeholder class
        pass

    class _ChatCompletionMessageToolCallUnion:  # pragma: no cover - placeholder class
        pass

    class _ChatCompletion:  # pragma: no cover - placeholder class
        pass

    chat_module.ChatCompletionMessage = _ChatCompletionMessage
    chat_module.ChatCompletionMessageToolCallUnion = _ChatCompletionMessageToolCallUnion
    chat_module.chat_completion = chat_completion_module
    chat_completion_module.ChatCompletion = _ChatCompletion

    openai_stub.types = types_module
    sys.modules["openai"] = openai_stub
    sys.modules["openai.types"] = types_module
    sys.modules["openai.types.chat"] = chat_module
    sys.modules["openai.types.chat.chat_completion"] = chat_completion_module
    types_module.chat = chat_module

if "tiktoken" not in sys.modules:  # pragma: no cover - test double for tokenizer
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

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SKIP_GRAPHITI_WAIT", "1")

from app.autonomy.autonomous_agent import AutonomyLevel, AutonomousAgent
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter


class RecordingMemoryAdapter(AdvancedMemoryAdapter):
    """Lightweight adapter that records skill saves for assertions."""

    def __init__(self) -> None:
        # Skip parent initialisation to avoid external dependencies
        self.saved_skills: List[Dict[str, Any]] = []

    async def save_skill(
        self,
        name: str,
        trigger_patterns: Optional[List[str]] = None,
        procedure: str = "",
        system_prompt: str = "",
        performance_score: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        provided = {
            "name": name,
            "trigger_patterns": trigger_patterns,
            "procedure": procedure,
            "system_prompt": system_prompt,
        }
        missing = [key for key, value in provided.items() if value is None]
        if missing:
            raise TypeError(f"Missing required arguments: {missing}")

        if trigger_patterns is not None and not isinstance(trigger_patterns, list):
            raise TypeError("trigger_patterns must be a list when provided")

        record = {
            "name": name,
            "trigger_patterns": trigger_patterns or [],
            "procedure": procedure,
            "system_prompt": system_prompt,
            "metadata": metadata or {},
        }
        self.saved_skills.append(record)
        return {"success": True, "id": f"skill-{len(self.saved_skills)}", "metadata": metadata or {}}

    async def search_memories(self, *_, **__):  # pragma: no cover - behaviour is mocked
        return []


class DummyMarkAgent:
    async def generate_response(self, *_: Any, **__: Any) -> str:
        plan = {
            "project_name": "Memory Safe Project",
            "description": "A minimal plan for testing",
            "estimated_hours": 0,
            "tasks": [],
        }
        return json.dumps(plan)


class DummyLearningCycle:
    async def reflect_on_episode(self, episode_id: str) -> None:  # pragma: no cover - no-op
        self.last_episode = episode_id


@pytest.mark.asyncio
async def test_start_autonomous_mode_saves_plan_without_type_error() -> None:
    """Ensure plan persistence uses supported AdvancedMemoryAdapter helpers."""

    memory_adapter = RecordingMemoryAdapter()
    agent = AutonomousAgent(
        mark_agent=DummyMarkAgent(),
        memory_adapter=memory_adapter,
        learning_cycle=DummyLearningCycle(),
        autonomy_level=AutonomyLevel.AUTONOMOUS,
    )

    result = await agent.start_autonomous_mode("Create integration test for memory")

    assert result["status"] == "completed"
    assert len(memory_adapter.saved_skills) == 2  # planner + autonomous agent saves
    for saved in memory_adapter.saved_skills:
        assert isinstance(saved["trigger_patterns"], list)
        assert saved["metadata"].get("skill_category") == "project_plan"
