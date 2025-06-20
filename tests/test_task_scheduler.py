import pytest
from langchain_api.services.task_executor import (
    TaskExecutor, TaskPriority, TaskStatus, TaskCategory, AccessLevel
)
from langchain_api.utils.task_manager import Task
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@pytest.fixture
def task_executor():
    executor = TaskExecutor()
    # Сбрасываем состояние ресурсов
    executor.scheduler.current_resources.clear()
    return executor

def test_create_task_with_dependencies(task_executor):
    # Создаем первую задачу
    task1 = task_executor.create_task(
        name="Task 1",
        description="First task",
        priority=TaskPriority.HIGH,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        required_resources={'cpu': 1.0, 'ram': 2.0, 'disk': 1.0}
    )
    
    # Создаем вторую задачу, зависящую от первой
    task2 = task_executor.create_task(
        name="Task 2",
        description="Second task",
        priority=TaskPriority.MEDIUM,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        depends_on={task1.id},
        required_resources={'cpu': 2.0, 'ram': 1.0, 'disk': 1.0}
    )
    
    # Проверяем порядок выполнения
    execution_order = task_executor.get_optimized_execution_order()
    assert len(execution_order) == 2
    assert execution_order[0].id == task1.id
    assert execution_order[1].id == task2.id

def test_resource_management(task_executor):
    """Тест управления ресурсами"""
    # Создаем задачи с разными требованиями к ресурсам через create_task
    task1 = task_executor.create_task(
        name="High Resource Task",
        description="Task requiring high resources",
        priority=TaskPriority.HIGH,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        depends_on=set(),
        required_resources={"cpu": 3.0, "ram": 6.0, "disk": 10.0}
    )
    task2 = task_executor.create_task(
        name="Low Resource Task",
        description="Task requiring low resources",
        priority=TaskPriority.LOW,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        depends_on=set(),
        required_resources={"cpu": 1.0, "ram": 2.0, "disk": 5.0}
    )
    # Проверяем, что задачи добавлены
    assert task1.id in task_executor.scheduler.dependency_graph
    assert task2.id in task_executor.scheduler.dependency_graph
    # Проверяем, что next_task возвращает задачу с меньшими требованиями к ресурсам
    next_task = task_executor.execute_next_task()
    assert next_task is not None
    assert next_task.id == task2.id  # Должна быть выбрана задача с меньшими требованиями
    # Освобождаем ресурсы
    task_executor.scheduler.release_resources(next_task.id)
    # Проверяем, что следующая задача может быть выполнена
    next_task = task_executor.execute_next_task()
    assert next_task is not None
    assert next_task.id == task1.id  # Теперь должна быть выбрана задача с большими требованиями

def test_task_completion_and_resource_release(task_executor):
    # Создаем задачу
    task = task_executor.create_task(
        name="Test Task",
        description="Task for testing completion",
        priority=TaskPriority.MEDIUM,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        required_resources={'cpu': 2.0, 'ram': 2.0, 'disk': 2.0}
    )
    
    # Запускаем задачу
    started_task = task_executor.execute_next_task()
    assert started_task is not None
    assert started_task.status == TaskStatus.RUNNING
    
    # Завершаем задачу
    completed_task = task_executor.complete_task(task.id, result="Success")
    assert completed_task is not None
    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.result == "Success"

def test_task_failure_and_resource_release(task_executor):
    # Создаем задачу
    task = task_executor.create_task(
        name="Test Task",
        description="Task for testing failure",
        priority=TaskPriority.MEDIUM,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        required_resources={'cpu': 2.0, 'ram': 2.0, 'disk': 2.0}
    )
    
    # Запускаем задачу
    started_task = task_executor.execute_next_task()
    assert started_task is not None
    assert started_task.status == TaskStatus.RUNNING
    
    # Отмечаем задачу как неудачную
    failed_task = task_executor.fail_task(task.id, error="Test error")
    assert failed_task is not None
    assert failed_task.status == TaskStatus.FAILED
    assert failed_task.error == "Test error"

def test_cyclic_dependencies(task_executor):
    # Создаем первую задачу
    task1 = task_executor.create_task(
        name="Task 1",
        description="First task",
        priority=TaskPriority.HIGH,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN
    )
    
    # Создаем вторую задачу, зависящую от первой
    task2 = task_executor.create_task(
        name="Task 2",
        description="Second task",
        priority=TaskPriority.MEDIUM,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        depends_on={task1.id}
    )
    
    # Создаем третью задачу, зависящую от второй
    task3 = task_executor.create_task(
        name="Task 3",
        description="Third task",
        priority=TaskPriority.LOW,
        parameters={},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.ADMIN,
        depends_on={task2.id}
    )
    
    # Пытаемся создать циклическую зависимость, добавляя зависимость task1 от task3
    with pytest.raises(ValueError):
        # Обновляем task1, добавляя зависимость от task3
        task_executor.scheduler.add_task_dependency(
            task_id=task1.id,
            depends_on={task3.id},  # Создаем цикл task1 -> task2 -> task3 -> task1
            required_resources={'cpu': 1.0, 'ram': 1.0, 'disk': 1.0}
        ) 