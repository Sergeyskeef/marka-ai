from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from langchain_api.services.task_executor import TaskPriority, TaskStatus, task_executor

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Используем глобальный экземпляр TaskExecutor (импортированный выше)

class TaskCreate(BaseModel):
    name: str
    description: str
    priority: TaskPriority
    parameters: dict[str, Any]

class TaskResponse(BaseModel):
    id: str
    name: str
    description: str
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    parameters: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None

    class Config:
        from_attributes = True

@router.post("/", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """Создание новой задачи"""
    return task_executor.create_task(
        name=task.name,
        description=task.description,
        priority=task.priority,
        parameters=task.parameters
    )

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Получение задачи по ID"""
    task = task_executor.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/", response_model=list[TaskResponse])
async def list_tasks(status: TaskStatus | None = None):
    """Получение списка задач с возможностью фильтрации по статусу"""
    return task_executor.get_task_list(status)

@router.get("/queue/status", response_model=list[TaskResponse])
async def get_queue_status():
    """Получение текущего состояния очереди задач"""
    return task_executor.get_queue_status()

@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Отмена задачи"""
    if not task_executor.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    return {"message": "Task cancelled successfully"}

@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    """Приостановка задачи"""
    if not task_executor.pause_task(task_id):
        raise HTTPException(status_code=400, detail="Cannot pause task")
    return {"message": "Task paused successfully"}

@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    """Возобновление задачи"""
    if not task_executor.resume_task(task_id):
        raise HTTPException(status_code=400, detail="Cannot resume task")
    return {"message": "Task resumed successfully"}

@router.put("/{task_id}/status")
async def update_task_status(
    task_id: str,
    status: TaskStatus,
    result: dict[str, Any] | None = None,
    error: str | None = None
):
    """Обновление статуса задачи"""
    task = task_executor.update_task_status(task_id, status, result, error)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
