"""Async tests for the autonomy FastAPI routes."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Ensure project package is importable in tests
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Provide a lightweight tiktoken stub to avoid network calls during imports
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

# Ensure config has a placeholder API key before importing the app modules
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.api import autonomy_routes

test_app = FastAPI()
test_app.include_router(autonomy_routes.router, prefix="/api")


AutonomyLevel = autonomy_routes.AutonomyLevel


@pytest.fixture(scope="session", autouse=True)
def wait_graphiti():
    """Override the global Graphiti wait fixture for isolated tests."""

    yield


class StubAutonomousAgent:
    """Simple stand-in for :class:`AutonomousAgent` used in tests."""

    def __init__(self) -> None:
        self.start_result: Any = {
            "status": "completed",
            "plan": {"project_name": "Stub"},
            "results": [],
            "completed_tasks": 0,
            "total_tasks": 0,
        }
        self.execute_result: Any = {"status": "completed", "task": {"name": "default"}}
        self.status_payload: Any = {
            "is_active": False,
            "autonomy_level": AutonomyLevel.SUPERVISED.value,
            "current_project": None,
            "tasks_total": 0,
            "tasks_completed": 0,
            "current_task": None,
        }
        self.stop_result: Optional[Exception] = None
        self.set_level_result: Optional[Exception] = None
        self.last_project_description: Optional[str] = None
        self.last_task_payload: Optional[Dict[str, Any]] = None
        self.stop_called = False
        self.received_level: Optional[AutonomyLevel] = None
        self.level_history: List[AutonomyLevel] = []

    async def start_autonomous_mode(self, description: str) -> Any:
        self.last_project_description = description
        if isinstance(self.start_result, Exception):
            raise self.start_result
        return self.start_result

    async def execute_task(self, task: Dict[str, Any]) -> Any:
        self.last_task_payload = task
        if isinstance(self.execute_result, Exception):
            raise self.execute_result
        return self.execute_result

    async def get_status(self) -> Dict[str, Any]:
        if isinstance(self.status_payload, Exception):
            raise self.status_payload
        return self.status_payload

    def stop(self) -> None:
        if isinstance(self.stop_result, Exception):
            raise self.stop_result
        self.stop_called = True

    def set_autonomy_level(self, level: AutonomyLevel) -> None:
        if isinstance(self.set_level_result, Exception):
            raise self.set_level_result
        self.received_level = level
        self.level_history.append(level)


@asynccontextmanager
async def override_agent(agent: StubAutonomousAgent):
    """Provide a temporary dependency override for the autonomous agent."""

    async def _dependency() -> StubAutonomousAgent:
        return agent

    test_app.dependency_overrides[autonomy_routes.get_autonomous_agent_dep] = _dependency
    transport = ASGITransport(app=test_app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        test_app.dependency_overrides.pop(autonomy_routes.get_autonomous_agent_dep, None)


@pytest.mark.asyncio
async def test_start_project_success() -> None:
    stub = StubAutonomousAgent()
    stub.start_result = {
        "status": "completed",
        "plan": {"project_name": "Test Project"},
        "results": [{"status": "completed", "task": {"id": "task-1"}}],
        "completed_tasks": 1,
        "total_tasks": 2,
    }

    async with override_agent(stub) as client:
        response = await client.post(
            "/api/autonomy/start_project",
            json={"project_description": "Build an autonomous feature"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["plan"]["project_name"] == "Test Project"
    assert data["results"][0]["task"]["id"] == "task-1"
    assert data["progress"] == pytest.approx(0.5)
    assert stub.last_project_description == "Build an autonomous feature"


@pytest.mark.asyncio
async def test_start_project_failure_payload_error() -> None:
    stub = StubAutonomousAgent()
    stub.start_result = {"status": "error", "error": "LLM failure"}

    async with override_agent(stub) as client:
        response = await client.post(
            "/api/autonomy/start_project",
            json={"project_description": "Broken run"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "LLM failure"


@pytest.mark.asyncio
async def test_execute_task_success() -> None:
    stub = StubAutonomousAgent()
    stub.execute_result = {
        "status": "completed",
        "task": {"name": "Implement feature"},
        "message": "done",
    }

    async with override_agent(stub) as client:
        response = await client.post(
            "/api/autonomy/execute_task",
            json={
                "task": {
                    "name": "Implement feature",
                    "description": "Write the code",
                    "type": "general",
                }
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["result"]["task"]["name"] == "Implement feature"
    assert stub.last_task_payload == {
        "name": "Implement feature",
        "description": "Write the code",
        "type": "general",
    }


@pytest.mark.asyncio
async def test_execute_task_failure_exception() -> None:
    stub = StubAutonomousAgent()
    stub.execute_result = RuntimeError("Tool failure")

    async with override_agent(stub) as client:
        response = await client.post(
            "/api/autonomy/execute_task",
            json={
                "task": {
                    "name": "Implement feature",
                    "description": "Write the code",
                }
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Tool failure"


@pytest.mark.asyncio
async def test_status_stop_and_set_level() -> None:
    stub = StubAutonomousAgent()
    stub.status_payload = {
        "is_active": True,
        "autonomy_level": AutonomyLevel.ASSISTED.value,
        "current_project": "Project X",
        "tasks_total": 4,
        "tasks_completed": 2,
        "current_task": {"id": "task-3"},
    }

    async with override_agent(stub) as client:
        status_response = await client.get("/api/autonomy/status")
        stop_response = await client.post("/api/autonomy/stop")
        set_response = await client.post("/api/autonomy/set_autonomy_level/autonomous")
        alias_response = await client.post("/api/autonomy/set_autonomy_level/2")

    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["autonomy_level"] == AutonomyLevel.ASSISTED.value
    assert status_data["progress"] == pytest.approx(0.5)
    assert status_data["current_task"]["id"] == "task-3"

    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
    assert stub.stop_called is True

    assert set_response.status_code == 200
    assert set_response.json()["level"] == AutonomyLevel.AUTONOMOUS.value
    assert stub.level_history[0] == AutonomyLevel.AUTONOMOUS

    assert alias_response.status_code == 200
    assert alias_response.json()["level"] == AutonomyLevel.SUPERVISED.value
    assert stub.level_history[-1] == AutonomyLevel.SUPERVISED


@pytest.mark.asyncio
async def test_set_level_invalid_value() -> None:
    stub = StubAutonomousAgent()

    async with override_agent(stub) as client:
        response = await client.post("/api/autonomy/set_autonomy_level/invalid")

    assert response.status_code == 400
    assert "Unknown autonomy level" in response.json()["detail"]
