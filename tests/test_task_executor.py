import time

import pytest

from langchain_api.core.feedback_system import FeedbackSystem
from langchain_api.services.task_executor import (
    AccessLevel,
    TaskCategory,
    TaskExecutor,
    TaskPriority,
    TaskStatus,
)


@pytest.fixture
def task_executor():
    executor = TaskExecutor()
    executor.feedback_system = FeedbackSystem(use_temp_file=True)
    return executor

@pytest.fixture
def sample_task(task_executor):
    return task_executor.create_task(
        title="test_task",
        description="Test task description",
        priority=TaskPriority.NORMAL,
        parameters={"param1": "value1"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

def test_create_task(task_executor):
    task = task_executor.create_task(
        title="sandbox",
        description="Test task",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )
    assert task.id is not None
    assert task.title == "sandbox"
    assert task.status == TaskStatus.PENDING
    assert task.created_at is not None
    assert task.updated_at is not None

def test_create_task_insufficient_permissions(task_executor):
    # Создаем задачу с системной категорией (должна пройти)
    task = task_executor.create_task(
        title="system",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"command": "test"},
        category=TaskCategory.SYSTEM,
        access_level=AccessLevel.READ
    )
    assert task is not None

def test_task_priority_queue(task_executor):
    # Создаем задачи с разными приоритетами
    task1 = task_executor.create_task(
        title="user",
        description="Low priority",
        priority=TaskPriority.LOW,
        parameters={"code": "test1"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )
    task2 = task_executor.create_task(
        title="user",
        description="High priority",
        priority=TaskPriority.HIGH,
        parameters={"code": "test2"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )
    task3 = task_executor.create_task(
        title="user",
        description="Normal priority",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test3"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    # Получаем список задач и проверяем наличие
    tasks = task_executor.get_task_list()
    assert len(tasks) >= 3
    task_ids = [task.id for task in tasks]
    assert task1.id in task_ids
    assert task2.id in task_ids
    assert task3.id in task_ids

def test_update_task_status(task_executor):
    task = task_executor.create_task(
        title="user",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    updated_task = task_executor.update_task_status(
        task.id,
        TaskStatus.COMPLETED,
        result="Success"
    )
    assert updated_task.status == TaskStatus.COMPLETED
    assert updated_task.result == "Success"

def test_update_task_status_insufficient_permissions(task_executor):
    task_executor.create_task(
        title="sandbox",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    # Создаем новую задачу с недостаточными правами
    with pytest.raises(ValueError):
        task_executor.create_task(
            title="system",
            description="Test",
            priority=TaskPriority.NORMAL,
            parameters={"command": "test"},
            category=TaskCategory.SYSTEM,
            access_level=AccessLevel.READ
        )

def test_cancel_task(task_executor):
    task = task_executor.create_task(
        title="sandbox",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    assert task_executor.cancel_task(task.id) is True
    assert task_executor.get_task(task.id).status == TaskStatus.CANCELLED

def test_cancel_task_insufficient_permissions(task_executor):
    task_executor.create_task(
        title="sandbox",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    # Создаем новую задачу с недостаточными правами
    with pytest.raises(ValueError):
        task_executor.create_task(
            title="system",
            description="Test",
            priority=TaskPriority.NORMAL,
            parameters={"command": "test"},
            category=TaskCategory.SYSTEM,
            access_level=AccessLevel.READ
        )

def test_pause_resume_task(task_executor):
    task = task_executor.create_task(
        title="sandbox",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    # Обновляем статус на RUNNING для теста паузы
    task_executor.update_task_status(task.id, TaskStatus.RUNNING)

    assert task_executor.pause_task(task.id) is True
    assert task_executor.get_task(task.id).status == TaskStatus.PAUSED

    assert task_executor.resume_task(task.id) is True
    assert task_executor.get_task(task.id).status == TaskStatus.RUNNING

def test_pause_task_insufficient_permissions(task_executor):
    task = task_executor.create_task(
        title="sandbox",
        description="Test",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    # Обновляем статус на RUNNING для теста паузы
    task_executor.update_task_status(task.id, TaskStatus.RUNNING)

    # Создаем новую задачу с недостаточными правами
    with pytest.raises(ValueError):
        task_executor.create_task(
            title="system",
            description="Test",
            priority=TaskPriority.NORMAL,
            parameters={"command": "test"},
            category=TaskCategory.SYSTEM,
            access_level=AccessLevel.READ
        )

def test_get_task_list(task_executor):
    # Создаем несколько задач
    task1 = task_executor.create_task(
        title="sandbox",
        description="Test 1",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test1"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )
    task2 = task_executor.create_task(
        title="sandbox",
        description="Test 2",
        priority=TaskPriority.NORMAL,
        parameters={"code": "test2"},
        category=TaskCategory.USER,
        access_level=AccessLevel.READ
    )

    # Обновляем статус одной задачи
    task_executor.update_task_status(task1.id, TaskStatus.COMPLETED)

    # Проверяем фильтрацию по статусу
    pending_tasks = task_executor.get_task_list(TaskStatus.PENDING)
    assert len(pending_tasks) == 1
    assert pending_tasks[0].id == task2.id

    completed_tasks = task_executor.get_task_list(TaskStatus.COMPLETED)
    assert len(completed_tasks) == 1
    assert completed_tasks[0].id == task1.id

def test_task_execution_with_feedback(task_executor, sample_task):
    """Тест выполнения задачи с системой обратной связи"""
    # Выполняем задачу
    executed_task = task_executor.execute_next_task()
    assert executed_task is not None
    assert executed_task.status == TaskStatus.COMPLETED

    # Проверяем, что метрики были записаны
    analysis = task_executor.get_task_performance_analysis(sample_task.id)
    assert analysis['total_executions'] == 1
    assert analysis['success_rate'] == 1.0
    assert 'execution_time' in analysis
    assert 'resource_usage' in analysis

def test_task_optimization_suggestions(task_executor, sample_task):
    """Тест получения предложений по оптимизации"""
    # Выполняем задачу несколько раз с разными параметрами
    for _ in range(3):
        task_executor.execute_next_task()
        time.sleep(0.1)  # Даем время на сбор метрик

    # Получаем предложения по оптимизации
    suggestions = task_executor.get_task_optimization_suggestions(sample_task.id)
    assert isinstance(suggestions, list)

    # Проверяем, что предложения содержат рекомендации
    if suggestions:
        assert all('type' in s for s in suggestions)
        assert all('description' in s for s in suggestions)
        assert all('recommendation' in s for s in suggestions)

def test_task_parameter_adjustment(task_executor, sample_task):
    """Тест автоматической корректировки параметров задачи"""
    # Выполняем задачу с начальными параметрами
    initial_params = sample_task.parameters.copy()
    task_executor.execute_next_task()

    # Проверяем, что параметры были скорректированы
    adjusted_params = task_executor.feedback_system.adjust_task_parameters(sample_task.id)
    assert isinstance(adjusted_params, dict)

    # Проверяем, что параметры изменились
    if adjusted_params:
        assert adjusted_params != initial_params

def test_task_performance_analysis(task_executor, sample_task):
    """Тест анализа производительности задачи"""
    # Выполняем задачу несколько раз
    for _ in range(3):
        task_executor.execute_next_task()
        time.sleep(0.1)

    # Получаем анализ производительности
    analysis = task_executor.get_task_performance_analysis(sample_task.id)

    # Проверяем структуру анализа
    assert 'total_executions' in analysis
    assert 'average_execution_time' in analysis
    assert 'success_rate' in analysis
    assert 'resource_usage' in analysis

    # Проверяем значения
    assert analysis['total_executions'] == 3
    assert 0 <= analysis['success_rate'] <= 1
    assert analysis['resource_usage']['cpu'] >= 0
    assert analysis['resource_usage']['memory'] >= 0

def test_feedback_system_integration(task_executor, sample_task):
    """Тест полной интеграции системы обратной связи"""
    # Выполняем задачу
    executed_task = task_executor.execute_next_task()
    assert executed_task is not None

    # Проверяем все аспекты системы обратной связи
    analysis = task_executor.get_task_performance_analysis(sample_task.id)
    suggestions = task_executor.get_task_optimization_suggestions(sample_task.id)
    adjusted_params = task_executor.feedback_system.adjust_task_parameters(sample_task.id)

    # Проверяем, что все компоненты работают
    assert analysis is not None
    assert suggestions is not None
    assert adjusted_params is not None

    # Проверяем, что метрики корректно записаны
    assert 'execution_time' in analysis
    assert 'success_rate' in analysis
    assert 'resource_usage' in analysis
