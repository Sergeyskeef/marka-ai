"""
Тесты для модуля task_manager.py.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from utils.task_manager import TaskManager, TaskStatus, TaskPriority, Task

@pytest.fixture
def task_manager():
    """Фикстура для создания экземпляра TaskManager."""
    return TaskManager()

def test_create_task(task_manager):
    """Тест создания задачи."""
    task = task_manager.create_task(
        task_type="development",
        description="Test task",
        priority=TaskPriority.HIGH
    )
    
    assert task.id in task_manager.tasks
    assert task.type == "development"
    assert task.description == "Test task"
    assert task.priority == TaskPriority.HIGH
    assert task.status == TaskStatus.PENDING
    assert task.created_at is not None
    assert task.started_at is None
    assert task.completed_at is None
    assert task.error_message is None
    assert task.metrics is None

def test_get_task(task_manager):
    """Тест получения задачи."""
    task = task_manager.create_task("development", "Test task")
    retrieved_task = task_manager.get_task(task.id)
    
    assert retrieved_task == task
    assert task_manager.get_task("nonexistent") is None

def test_list_tasks(task_manager):
    """Тест получения списка задач."""
    # Создаем задачи с разными статусами
    task1 = task_manager.create_task("development", "Task 1")
    task2 = task_manager.create_task("system", "Task 2")
    
    # Запускаем одну задачу
    task_manager.start_task(task1.id)
    
    # Проверяем все задачи
    all_tasks = task_manager.list_tasks()
    assert len(all_tasks) == 2
    
    # Проверяем задачи по статусу
    pending_tasks = task_manager.list_tasks(TaskStatus.PENDING)
    assert len(pending_tasks) == 1
    assert pending_tasks[0].id == task2.id
    
    running_tasks = task_manager.list_tasks(TaskStatus.RUNNING)
    assert len(running_tasks) == 1
    assert running_tasks[0].id == task1.id

def test_start_task(task_manager):
    """Тест запуска задачи."""
    task = task_manager.create_task("development", "Test task")
    
    # Успешный запуск
    assert task_manager.start_task(task.id)
    assert task.status == TaskStatus.RUNNING
    assert task.started_at is not None
    
    # Попытка запустить уже запущенную задачу
    assert not task_manager.start_task(task.id)
    
    # Попытка запустить несуществующую задачу
    assert not task_manager.start_task("nonexistent")

def test_complete_task(task_manager):
    """Тест завершения задачи."""
    task = task_manager.create_task("development", "Test task")
    task_manager.start_task(task.id)
    
    # Успешное завершение
    assert task_manager.complete_task(task.id, success=True)
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None
    assert task.metrics is not None
    
    # Завершение с ошибкой
    task2 = task_manager.create_task("system", "Task 2")
    task_manager.start_task(task2.id)
    assert task_manager.complete_task(task2.id, success=False, error_message="Test error")
    assert task2.status == TaskStatus.FAILED
    assert task2.error_message == "Test error"
    
    # Попытка завершить несуществующую задачу
    assert not task_manager.complete_task("nonexistent")

def test_cancel_task(task_manager):
    """Тест отмены задачи."""
    task = task_manager.create_task("development", "Test task")
    
    # Отмена ожидающей задачи
    assert task_manager.cancel_task(task.id)
    assert task.status == TaskStatus.CANCELLED
    assert task.completed_at is not None
    
    # Попытка отменить уже отмененную задачу
    assert not task_manager.cancel_task(task.id)
    
    # Попытка отменить несуществующую задачу
    assert not task_manager.cancel_task("nonexistent")

def test_get_task_status(task_manager):
    """Тест получения статуса задачи."""
    task = task_manager.create_task("development", "Test task")
    task_manager.start_task(task.id)
    task_manager.complete_task(task.id, success=True)
    
    status = task_manager.get_task_status(task.id)
    assert status is not None
    assert status["id"] == task.id
    assert status["type"] == "development"
    assert status["description"] == "Test task"
    assert status["status"] == TaskStatus.COMPLETED.value
    assert status["created_at"] is not None
    assert status["started_at"] is not None
    assert status["completed_at"] is not None
    assert status["error_message"] is None
    assert "metrics" in status
    
    # Проверка несуществующей задачи
    assert task_manager.get_task_status("nonexistent") is None

def test_analyze_task(task_manager):
    """Тест анализа задачи."""
    task = task_manager.create_task("development", "Test task")
    task_manager.start_task(task.id)
    task_manager.complete_task(task.id, success=True)
    
    analysis = task_manager.analyze_task(task.id)
    assert analysis is not None
    assert analysis["task_id"] == task.id
    assert analysis["task_type"] == "development"
    assert 0 <= analysis["performance_score"] <= 1
    assert 0 <= analysis["resource_efficiency"] <= 1
    assert isinstance(analysis["recommendations"], list)
    assert isinstance(analysis["patterns"], list)
    
    # Проверка несуществующей задачи
    assert task_manager.analyze_task("nonexistent") is None

@patch('psutil.cpu_percent')
@patch('psutil.Process')
def test_get_statistics(mock_process, mock_cpu_percent, task_manager):
    """Тест получения статистики."""
    # Настраиваем моки
    mock_process.return_value.memory_percent.return_value = 30.0
    mock_cpu_percent.return_value = 50.0
    
    # Создаем и завершаем несколько задач
    for i in range(3):
        task = task_manager.create_task("development", f"Task {i}")
        task_manager.start_task(task.id)
        task_manager.complete_task(task.id, success=True)

    stats = task_manager.get_statistics()
    assert stats["total_tasks"] == 3
    assert stats["successful_tasks"] == 3
    assert stats["success_rate"] == 1.0
    assert stats["average_execution_time"] > 0
    assert stats["average_cpu_usage"] > 0
    assert stats["average_memory_usage"] > 0 