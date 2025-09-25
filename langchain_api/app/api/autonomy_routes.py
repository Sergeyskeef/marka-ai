"""Autonomy API routes integrating the autonomous agent."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.autonomy.autonomous_agent import AutonomyLevel, AutonomousAgent
from app.agents.chat_handler import get_agent
from app.learning.reap_cycle import REAPLearningCycle
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Lazy singletons -----------------------------------------------------
_autonomous_agent: Optional[AutonomousAgent] = None
_memory_adapter: Optional[AdvancedMemoryAdapter] = None
_learning_cycle: Optional[REAPLearningCycle] = None
_agent_lock = asyncio.Lock()


async def _get_or_create_autonomous_agent() -> AutonomousAgent:
    """Create a shared :class:`AutonomousAgent` instance on demand."""

    global _autonomous_agent, _memory_adapter, _learning_cycle

    if _autonomous_agent is None:
        async with _agent_lock:
            if _autonomous_agent is None:
                logger.info("Initializing autonomous agent instance")
                base_agent = await get_agent()

                if _memory_adapter is None:
                    _memory_adapter = AdvancedMemoryAdapter()

                if _learning_cycle is None:
                    _learning_cycle = REAPLearningCycle(memory_adapter=_memory_adapter)

                _autonomous_agent = AutonomousAgent(
                    mark_agent=base_agent,
                    memory_adapter=_memory_adapter,
                    learning_cycle=_learning_cycle,
                )

    return _autonomous_agent


async def get_autonomous_agent_dep() -> AutonomousAgent:
    """FastAPI dependency that returns the shared autonomous agent."""

    return await _get_or_create_autonomous_agent()


# --- Pydantic models -----------------------------------------------------


class StartProjectRequest(BaseModel):
    """Request body for starting an autonomous project."""

    project_description: str = Field(..., min_length=1)


class TaskPayload(BaseModel):
    """Payload describing a task for the autonomous agent."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    type: str = Field(default="general")
    id: Optional[str] = None
    priority: Optional[str] = None
    estimated_hours: Optional[float] = None
    dependencies: Optional[List[str]] = None
    requirements: Optional[List[str]] = None
    output_file: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ExecuteTaskRequest(BaseModel):
    """Request body for executing a single task."""

    task: TaskPayload


class TaskExecutionResponse(BaseModel):
    """Response returned after executing a task."""

    status: str
    result: Dict[str, Any]


class StartProjectResponse(BaseModel):
    """Response returned when an autonomous project is started."""

    status: str
    plan: Optional[Dict[str, Any]] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)
    completed_tasks: int = 0
    total_tasks: int = 0
    progress: float = 0.0


class AutonomyStatusResponse(BaseModel):
    """Response describing the current state of the autonomous agent."""

    is_active: bool
    autonomy_level: str
    current_project: Optional[str] = None
    tasks_total: int = 0
    tasks_completed: int = 0
    current_task: Optional[Dict[str, Any]] = None
    progress: float = 0.0


class StopResponse(BaseModel):
    """Response returned after stopping the autonomous agent."""

    status: str


class SetAutonomyLevelResponse(BaseModel):
    """Response after changing the autonomy level."""

    status: str
    level: str


class CapabilitiesResponse(BaseModel):
    """Response listing available autonomous capabilities."""

    capabilities: List[str]


# --- Helpers -------------------------------------------------------------

_LEVEL_ALIASES = {
    "0": AutonomyLevel.MANUAL,
    "1": AutonomyLevel.ASSISTED,
    "2": AutonomyLevel.SUPERVISED,
    "3": AutonomyLevel.AUTONOMOUS,
}


def _resolve_autonomy_level(raw_level: str) -> AutonomyLevel:
    """Normalize a user-supplied autonomy level to the enum value."""

    normalized = raw_level.strip().lower()
    if normalized in _LEVEL_ALIASES:
        return _LEVEL_ALIASES[normalized]

    try:
        return AutonomyLevel(normalized)
    except ValueError:  # Try enum member access (MANUAL, etc.)
        try:
            return AutonomyLevel[normalized.upper()]
        except KeyError as exc:  # noqa: PERF203 - explicit error message
            raise ValueError(f"Unknown autonomy level: '{raw_level}'") from exc


def _calculate_progress(completed: int, total: int) -> float:
    """Calculate completion ratio with bounds checking."""

    if total <= 0:
        return 0.0
    ratio = completed / total
    return max(0.0, min(1.0, ratio))


# --- Routes --------------------------------------------------------------


@router.post("/autonomy/start_project", response_model=StartProjectResponse)
async def start_project(
    request: StartProjectRequest,
    agent: AutonomousAgent = Depends(get_autonomous_agent_dep),
) -> StartProjectResponse:
    """Trigger autonomous project execution."""

    try:
        result = await agent.start_autonomous_mode(request.project_description)
    except Exception as exc:  # noqa: BLE001 - surface detailed message via HTTP
        logger.exception("Failed to start autonomous mode: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error") or "Failed to start autonomous mode",
        )

    completed = int(result.get("completed_tasks") or 0)
    total = int(result.get("total_tasks") or 0)

    return StartProjectResponse(
        status=result.get("status", "unknown"),
        plan=result.get("plan"),
        results=list(result.get("results") or []),
        completed_tasks=completed,
        total_tasks=total,
        progress=_calculate_progress(completed, total),
    )


@router.post("/autonomy/execute_task", response_model=TaskExecutionResponse)
async def execute_task(
    request: ExecuteTaskRequest,
    agent: AutonomousAgent = Depends(get_autonomous_agent_dep),
) -> TaskExecutionResponse:
    """Execute a single task through the autonomous agent."""

    task_payload = request.task.model_dump(exclude_none=True)

    try:
        result = await agent.execute_task(task_payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to execute task: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error") or "Task execution failed",
        )

    return TaskExecutionResponse(status=result.get("status", "unknown"), result=result)


@router.get("/autonomy/status", response_model=AutonomyStatusResponse)
async def autonomy_status(
    agent: AutonomousAgent = Depends(get_autonomous_agent_dep),
) -> AutonomyStatusResponse:
    """Return the current status of the autonomous agent."""

    try:
        status_payload = await agent.get_status()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read autonomous status: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    total = int(status_payload.get("tasks_total") or 0)
    completed = int(status_payload.get("tasks_completed") or 0)

    return AutonomyStatusResponse(
        is_active=bool(status_payload.get("is_active")),
        autonomy_level=status_payload.get("autonomy_level") or AutonomyLevel.SUPERVISED.value,
        current_project=status_payload.get("current_project"),
        tasks_total=total,
        tasks_completed=completed,
        current_task=status_payload.get("current_task"),
        progress=_calculate_progress(completed, total),
    )


@router.post("/autonomy/stop", response_model=StopResponse)
async def stop_autonomy(
    agent: AutonomousAgent = Depends(get_autonomous_agent_dep),
) -> StopResponse:
    """Stop the autonomous agent."""

    try:
        agent.stop()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to stop autonomous agent: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return StopResponse(status="stopped")


@router.post("/autonomy/set_autonomy_level/{level}", response_model=SetAutonomyLevelResponse)
async def set_autonomy_level(
    level: str,
    agent: AutonomousAgent = Depends(get_autonomous_agent_dep),
) -> SetAutonomyLevelResponse:
    """Set the autonomy level for the agent."""

    try:
        autonomy_level = _resolve_autonomy_level(level)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        agent.set_autonomy_level(autonomy_level)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to change autonomy level: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return SetAutonomyLevelResponse(status="ok", level=autonomy_level.value)


@router.get("/autonomy/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    """Return a static list of supported autonomous capabilities."""

    return CapabilitiesResponse(capabilities=["plan", "code", "test", "document"])

