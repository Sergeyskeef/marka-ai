import os
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from services.passport_sync_service import PassportSyncService
from scripts.auto_sync_passport import ChangeReport

@pytest.fixture
def project_root(tmp_path):
    """Создает временную директорию для тестов"""
    return tmp_path

@pytest.fixture
def mock_handler():
    """Создает мок PassportSyncHandler"""
    handler = MagicMock()
    handler.get_pending_changes.return_value = ChangeReport()
    handler.apply_changes.return_value = True
    return handler

@pytest.fixture
def mock_updater():
    """Создает мок PassportUpdater"""
    updater = MagicMock()
    return updater

@pytest.fixture
def sync_service(project_root, mock_updater, mock_handler):
    """Создает экземпляр PassportSyncService с моками"""
    with patch('services.passport_sync_service.PassportUpdater', return_value=mock_updater), \
         patch('services.passport_sync_service.PassportSyncHandler', return_value=mock_handler):
        service = PassportSyncService(project_root)
        return service

@pytest.mark.asyncio
async def test_start_service(sync_service):
    """Тест запуска сервиса"""
    with patch('watchdog.observers.Observer') as mock_observer:
        mock_observer.return_value = MagicMock()
        await sync_service.start()
        
        assert sync_service.is_running
        assert sync_service.observer is not None
        sync_service.observer.start.assert_called_once()

@pytest.mark.asyncio
async def test_stop_service(sync_service):
    """Тест остановки сервиса"""
    # Запускаем сервис
    with patch('watchdog.observers.Observer') as mock_observer:
        mock_observer.return_value = MagicMock()
        await sync_service.start()
        
    # Останавливаем сервис
    await sync_service.stop()
    
    assert not sync_service.is_running
    sync_service.observer.stop.assert_called_once()
    sync_service.observer.join.assert_called_once()

def test_register_notification_callback(sync_service):
    """Тест регистрации callback'а для уведомлений"""
    callback = MagicMock()
    sync_service.register_notification_callback(callback)
    assert callback in sync_service.notification_callbacks

def test_unregister_notification_callback(sync_service):
    """Тест удаления callback'а из уведомлений"""
    callback = MagicMock()
    sync_service.register_notification_callback(callback)
    sync_service.unregister_notification_callback(callback)
    assert callback not in sync_service.notification_callbacks

@pytest.mark.asyncio
async def test_notify_changes(sync_service):
    """Тест отправки уведомлений об изменениях"""
    callback = AsyncMock()
    sync_service.register_notification_callback(callback)
    
    changes = ChangeReport()
    changes.changes['added_files'].append('test.py')
    
    await sync_service._notify_changes(changes)
    callback.assert_called_once_with(changes)

@pytest.mark.asyncio
async def test_check_changes_loop(sync_service, mock_handler):
    """Тест цикла проверки изменений"""
    # Настраиваем мок для возврата изменений
    changes = ChangeReport()
    changes.changes['added_files'].append('test.py')
    mock_handler.get_pending_changes.return_value = changes
    
    # Запускаем сервис
    with patch('watchdog.observers.Observer') as mock_observer:
        mock_observer.return_value = MagicMock()
        await sync_service.start()
        
        # Ждем один цикл проверки
        await asyncio.sleep(0.1)
        
        # Останавливаем сервис
        await sync_service.stop()
        
        # Проверяем, что изменения были получены
        assert mock_handler.get_pending_changes.call_count > 0

@pytest.mark.asyncio
async def test_apply_changes(sync_service, mock_handler):
    """Тест применения изменений"""
    assert await sync_service.apply_changes()
    mock_handler.apply_changes.assert_called_once()

def test_get_pending_changes(sync_service, mock_handler):
    """Тест получения накопленных изменений"""
    changes = sync_service.get_pending_changes()
    assert isinstance(changes, ChangeReport)
    mock_handler.get_pending_changes.assert_called_once()

def test_clear_pending_changes(sync_service, mock_handler):
    """Тест очистки накопленных изменений"""
    sync_service.clear_pending_changes()
    mock_handler.clear_pending_changes.assert_called_once()

def test_service_status(sync_service, mock_handler):
    """Тест получения статуса сервиса"""
    status = sync_service.status
    assert isinstance(status, dict)
    assert 'is_running' in status
    assert 'project_root' in status
    assert 'sync_interval' in status
    assert 'has_pending_changes' in status 