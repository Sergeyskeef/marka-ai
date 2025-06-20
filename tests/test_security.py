import pytest
from langchain_api.services.security import (
    SecurityManager,
    AccessLevel,
    TaskCategory,
    SecurityPolicy,
    ResourceUsage
)
from datetime import datetime, timedelta
import time
import json
from pathlib import Path

@pytest.fixture
def security_manager():
    """Фикстура для SecurityManager"""
    return SecurityManager()

def test_validate_access_level(security_manager):
    """Тест проверки уровней доступа"""
    assert security_manager._validate_access_level(AccessLevel.ADMIN, AccessLevel.READ)
    assert security_manager._validate_access_level(AccessLevel.MANAGE, AccessLevel.EXECUTE)
    assert not security_manager._validate_access_level(AccessLevel.READ, AccessLevel.ADMIN)
    assert not security_manager._validate_access_level(AccessLevel.EXECUTE, AccessLevel.MANAGE)

def test_validate_category(security_manager):
    """Тест проверки категорий задач"""
    assert security_manager._validate_category(
        TaskCategory.SYSTEM,
        [TaskCategory.SYSTEM, TaskCategory.MEMORY]
    )
    assert not security_manager._validate_category(
        TaskCategory.SANDBOX,
        [TaskCategory.SYSTEM, TaskCategory.MEMORY]
    )

def test_validate_parameters(security_manager):
    """Тест проверки параметров задач"""
    # Тест системных задач
    assert security_manager._validate_parameters(
        {"command": "restart"},
        "system"
    )
    assert not security_manager._validate_parameters(
        {"command": "invalid"},
        "system"
    )
    
    # Тест задач памяти
    assert security_manager._validate_parameters(
        {"command": "read", "path": "/memory/data"},
        "memory"
    )
    assert not security_manager._validate_parameters(
        {"command": "read", "path": "/invalid/path"},
        "memory"
    )

def test_validate_parallel_tasks(security_manager):
    """Тест проверки параллельных задач"""
    # Добавляем активные задачи
    security_manager.active_tasks = {
        "task1": datetime.now(),
        "task2": datetime.now() - timedelta(seconds=200),
        "task3": datetime.now() - timedelta(seconds=400)
    }
    
    assert security_manager._validate_parallel_tasks("new_task", 3)
    assert not security_manager._validate_parallel_tasks("new_task", 2)

def test_resource_tracking(security_manager):
    """Тест отслеживания ресурсов"""
    task_name = "test_task"
    
    # Начало задачи
    security_manager.track_task_start(task_name)
    assert task_name in security_manager.active_tasks
    assert task_name in security_manager.resource_usage
    
    # Обновление метрик
    security_manager.update_resource_usage(task_name)
    assert len(security_manager.resource_usage[task_name]) == 1
    
    # Завершение задачи
    security_manager.track_task_end(task_name)
    assert task_name not in security_manager.active_tasks
    assert task_name not in security_manager.resource_usage

def test_snapshot_creation_and_restore(security_manager, tmp_path):
    """Тест создания и восстановления снапшотов"""
    # Настраиваем директорию для снапшотов
    security_manager.snapshots_dir = tmp_path
    
    # Добавляем тестовые данные
    task_name = "test_task"
    security_manager.track_task_start(task_name)
    security_manager.update_resource_usage(task_name)
    
    # Создаем снапшот
    snapshot_path = security_manager.create_snapshot(task_name)
    assert Path(snapshot_path).exists()
    
    # Проверяем содержимое снапшота
    with open(snapshot_path) as f:
        snapshot = json.load(f)
        assert snapshot["task_name"] == task_name
        assert "timestamp" in snapshot
        assert "resource_usage" in snapshot
        assert "active_tasks" in snapshot
    
    # Очищаем текущее состояние
    security_manager.active_tasks.clear()
    security_manager.resource_usage.clear()
    
    # Восстанавливаем из снапшота
    assert security_manager.restore_from_snapshot(snapshot_path)
    assert task_name in security_manager.active_tasks
    assert task_name in security_manager.resource_usage

def test_resource_limits(security_manager):
    """Тест получения лимитов ресурсов"""
    limits = security_manager.get_resource_limits("system")
    assert "max_execution_time" in limits
    assert "max_memory_usage" in limits
    assert "max_parallel_tasks" in limits
    
    assert limits["max_execution_time"] == 300
    assert limits["max_memory_usage"] == 512
    assert limits["max_parallel_tasks"] == 1

def test_requires_confirmation(security_manager):
    """Тест проверки необходимости подтверждения"""
    assert security_manager.requires_confirmation("system")
    assert security_manager.requires_confirmation("sandbox")
    assert not security_manager.requires_confirmation("memory")

def test_validate_resources(security_manager, monkeypatch):
    """Тест проверки ресурсов"""
    # Мокаем использование ресурсов
    def mock_resource_usage():
        return ResourceUsage(
            cpu_percent=50.0,
            memory_percent=30.0,
            execution_time=10.0,
            timestamp=datetime.now()
        )
    
    monkeypatch.setattr(security_manager, "get_current_resource_usage", mock_resource_usage)
    
    policy = SecurityPolicy(
        required_access_level=AccessLevel.ADMIN,
        allowed_categories=[TaskCategory.SYSTEM],
        max_execution_time=300,
        max_memory_usage=512,
        requires_confirmation=True
    )
    
    assert security_manager._validate_resources("test_task", policy)
    
    # Тест превышения лимитов
    def mock_high_usage():
        return ResourceUsage(
            cpu_percent=95.0,
            memory_percent=60.0,
            execution_time=10.0,
            timestamp=datetime.now()
        )
    
    monkeypatch.setattr(security_manager, "get_current_resource_usage", mock_high_usage)
    assert not security_manager._validate_resources("test_task", policy) 