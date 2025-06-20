import pytest
from langchain_api.services.task_executor import TaskExecutor, TaskPriority, TaskStatus, TaskCategory, AccessLevel
from unittest.mock import patch, MagicMock
import subprocess
from pathlib import Path
from langchain_api.services.security import SecurityManager
import os
import shutil

@pytest.fixture
def security_manager():
    """Фикстура для SecurityManager"""
    with patch('langchain_api.services.task_executor.SecurityManager') as mock:
        manager = mock.return_value
        manager.validate_task.return_value = True
        yield manager

@pytest.fixture
def task_executor(security_manager):
    """Фикстура для TaskExecutor"""
    executor = TaskExecutor()
    executor.security_manager = security_manager
    return executor

@pytest.fixture
def sample_task(task_executor):
    """Фикстура для тестовой задачи"""
    return task_executor.create_task(
        name="test_task",
        description="Test task description",
        priority=TaskPriority.MEDIUM,
        parameters={"command": "echo 'test'"},
        category=TaskCategory.SANDBOX,
        access_level=AccessLevel.ADMIN
    )

@pytest.fixture(autouse=True)
def create_snapshots_dir():
    path = os.path.join(os.path.dirname(__file__), '../../sandbox/snapshots')
    os.makedirs(path, exist_ok=True)
    yield
    shutil.rmtree(path, ignore_errors=True)

@pytest.fixture(autouse=True)
def mock_subprocess_run():
    with patch('subprocess.run') as mock_run:
        yield mock_run

def test_execute_sandbox_command_success(task_executor, sample_task):
    """Тест успешного выполнения команды в песочнице"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="test output")
        success, output = task_executor.execute_sandbox_command(sample_task.id, "echo 'test'")
        assert success
        assert "test output" in output

def test_execute_sandbox_command_failure(task_executor, sample_task):
    """Тест ошибки выполнения команды в песочнице"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="command not found")
        success, output = task_executor.execute_sandbox_command(sample_task.id, "invalid_command")
        assert not success
        assert "command not found" in output

def test_create_sandbox_diff_success(task_executor, sample_task):
    """Тест успешного создания диффа"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="diff output")
        success, output = task_executor.create_sandbox_diff(sample_task.id)
        assert success
        assert "diff output" in output

def test_apply_sandbox_changes_success(task_executor, sample_task):
    """Тест успешного применения изменений"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        success, output = task_executor.apply_sandbox_changes(sample_task.id)
        assert success
        assert "Изменения успешно применены" in output

def test_validate_sandbox_changes_success(task_executor, sample_task):
    """Тест успешной валидации изменений"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        success, output = task_executor.validate_sandbox_changes(sample_task.id)
        assert success
        assert "Изменения прошли валидацию" in output

def test_validate_sandbox_changes_no_changes(task_executor, sample_task):
    """Тест валидации при отсутствии изменений"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        success, output = task_executor.validate_sandbox_changes(sample_task.id)
        assert not success
        assert "Нет изменений для валидации" in output

def test_validate_sandbox_changes_test_failure(task_executor, sample_task):
    """Тест ошибки валидации при падении тестов"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="test failure")
        success, output = task_executor.validate_sandbox_changes(sample_task.id)
        assert not success
        assert "test failure" in output

def test_create_sandbox_snapshot(task_executor, sample_task):
    """Тест создания снапшота"""
    snapshot_path = task_executor._create_sandbox_snapshot(sample_task.id)
    assert isinstance(snapshot_path, str)
    assert sample_task.id in snapshot_path

def test_restore_sandbox_snapshot(task_executor, sample_task):
    """Тест успешного восстановления снапшота"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        snapshot_path = task_executor._create_sandbox_snapshot(sample_task.id)
        success = task_executor._restore_sandbox_snapshot(snapshot_path)
        assert success

def test_restore_sandbox_snapshot_failure(task_executor, sample_task):
    """Тест ошибки восстановления снапшота"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="restore failed")
        snapshot_path = task_executor._create_sandbox_snapshot(sample_task.id)
        success = task_executor._restore_sandbox_snapshot(snapshot_path)
        assert not success 