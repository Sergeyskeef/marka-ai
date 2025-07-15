import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Добавляем путь к корню проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from langchain_api.main import app
from langchain_api.scripts.auto_sync_passport import ChangeReport
from langchain_api.routers import passport_sync

@pytest.fixture
def client():
    """Создает тестовый клиент FastAPI"""
    with TestClient(app) as client:
        yield client

@pytest.fixture
def mock_sync_service():
    """Создает мок PassportSyncService"""
    mock_service = MagicMock()
    mock_service.is_enabled.return_value = True
    mock_service.get_last_sync_time.return_value = "2025-03-20T12:00:00"
    mock_service.get_pending_changes_count.return_value = 3
    
    # Создаем ChangeReport правильно
    change_report = ChangeReport()
    change_report.changes = {
        "added_files": ["file1.txt"],
        "modified_files": ["file2.txt"],
        "removed_files": ["file3.txt"]
    }
    mock_service.get_pending_changes.return_value = [change_report]
    
    # Патчим глобальную переменную в модуле роутера
    with patch('langchain_api.routers.passport_sync.passport_sync_service', mock_service):
        yield mock_service

def test_get_sync_status(client, mock_sync_service):
    """Тест получения статуса синхронизации"""
    response = client.get("/passport/sync/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] == True
    assert data["last_sync"] == "2025-03-20T12:00:00"
    assert data["pending_changes"] == 3

def test_get_sync_status_not_initialized(client):
    """Тест получения статуса при неинициализированном сервисе"""
    with patch('langchain_api.routers.passport_sync.passport_sync_service', None):
        response = client.get("/passport/sync/status")
        assert response.status_code == 503
        assert response.json() == {"detail": "PassportSyncService не инициализирован"}

def test_apply_changes(client, mock_sync_service):
    """Тест применения изменений"""
    mock_sync_service.apply_changes.return_value = {
        "changes_applied": 3,
        "timestamp": "2025-03-20T12:00:00"
    }
    response = client.post("/passport/sync/apply")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert data["changes_applied"] == 3
    assert data["timestamp"] == "2025-03-20T12:00:00"

def test_apply_changes_not_initialized(client):
    """Тест применения изменений при неинициализированном сервисе"""
    with patch('langchain_api.routers.passport_sync.passport_sync_service', None):
        response = client.post("/passport/sync/apply")
        assert response.status_code == 503
        assert response.json() == {"detail": "PassportSyncService не инициализирован"}

def test_get_pending_changes(client, mock_sync_service):
    """Тест получения списка изменений"""
    response = client.get("/passport/sync/changes")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "added_files" in data[0]["changes"]
    assert "modified_files" in data[0]["changes"]
    assert "removed_files" in data[0]["changes"]
    assert data[0]["changes"]["added_files"] == ["file1.txt"]
    assert data[0]["changes"]["modified_files"] == ["file2.txt"]
    assert data[0]["changes"]["removed_files"] == ["file3.txt"]

def test_get_pending_changes_not_initialized(client):
    """Тест получения изменений при неинициализированном сервисе"""
    with patch('langchain_api.routers.passport_sync.passport_sync_service', None):
        response = client.get("/passport/sync/changes")
        assert response.status_code == 503
        assert response.json() == {"detail": "PassportSyncService не инициализирован"}

def test_clear_pending_changes(client, mock_sync_service):
    """Тест очистки списка изменений"""
    response = client.delete("/passport/sync/changes")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

def test_clear_pending_changes_not_initialized(client):
    """Тест очистки изменений при неинициализированном сервисе"""
    with patch('langchain_api.routers.passport_sync.passport_sync_service', None):
        response = client.delete("/passport/sync/changes")
        assert response.status_code == 503
        assert response.json() == {"detail": "PassportSyncService не инициализирован"} 