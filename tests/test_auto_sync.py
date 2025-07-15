import time
from unittest.mock import MagicMock

import pytest
from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent

from scripts.auto_sync_passport import ChangeReport, PassportSyncHandler


@pytest.fixture
def mock_updater():
    """Создает мок PassportUpdater"""
    updater = MagicMock()
    updater.update_passport.return_value = True
    return updater

@pytest.fixture
def sync_handler(mock_updater):
    """Создает экземпляр PassportSyncHandler"""
    return PassportSyncHandler(mock_updater, sync_interval=1)

@pytest.fixture
def change_report():
    """Создает экземпляр ChangeReport"""
    return ChangeReport()

def test_should_ignore(sync_handler):
    """Тест проверки игнорируемых файлов"""
    # Проверяем игнорируемые файлы
    assert sync_handler.should_ignore('test.pyc')
    assert sync_handler.should_ignore('__pycache__/test.py')
    assert sync_handler.should_ignore('.git/config')
    assert sync_handler.should_ignore('test.log')
    assert sync_handler.should_ignore('test.json')
    assert sync_handler.should_ignore('test.md')
    assert sync_handler.should_ignore('test.txt')
    assert sync_handler.should_ignore('test.csv')
    assert sync_handler.should_ignore('test.db')
    assert sync_handler.should_ignore('test.sqlite')
    assert sync_handler.should_ignore('test.sqlite3')
    assert sync_handler.should_ignore('test.bak')
    assert sync_handler.should_ignore('test.tmp')
    assert sync_handler.should_ignore('test.temp')
    assert sync_handler.should_ignore('test.swp')
    assert sync_handler.should_ignore('test.swo')
    assert sync_handler.should_ignore('test.swn')
    assert sync_handler.should_ignore('test.sublime-workspace')
    assert sync_handler.should_ignore('test.sublime-project')
    assert sync_handler.should_ignore('.DS_Store')
    assert sync_handler.should_ignore('Thumbs.db')

    # Проверяем файлы, которые не должны игнорироваться
    assert not sync_handler.should_ignore('test.py')
    assert not sync_handler.should_ignore('src/test.py')
    assert not sync_handler.should_ignore('test/__init__.py')

def test_on_any_event(sync_handler, mock_updater):
    """Тест обработки событий файловой системы"""
    # Создаем тестовое событие
    event = FileModifiedEvent('test.py')

    # Проверяем обработку события
    sync_handler.on_any_event(event)
    mock_updater.update_passport.assert_called_once()

    # Проверяем игнорирование событий директорий
    event = FileCreatedEvent('test_dir', is_directory=True)
    sync_handler.on_any_event(event)
    assert mock_updater.update_passport.call_count == 1  # Не должно увеличиться

    # Проверяем игнорирование по интервалу
    event = FileModifiedEvent('test.py')
    sync_handler.on_any_event(event)
    assert mock_updater.update_passport.call_count == 1  # Не должно увеличиться из-за интервала

    # Ждем интервал и проверяем снова
    time.sleep(1.1)
    sync_handler.on_any_event(event)
    assert mock_updater.update_passport.call_count == 2  # Теперь должно увеличиться

def test_error_handling(sync_handler, mock_updater):
    """Тест обработки ошибок"""
    # Симулируем ошибку при обновлении паспорта
    mock_updater.update_passport.side_effect = Exception("Test error")

    event = FileModifiedEvent('test.py')
    sync_handler.on_any_event(event)  # Не должно вызвать исключение

    # Проверяем, что ошибка была обработана
    assert mock_updater.update_passport.call_count == 1

def test_sync_interval(sync_handler, mock_updater):
    """Тест интервала синхронизации"""
    event = FileModifiedEvent('test.py')

    # Первое событие
    sync_handler.on_any_event(event)
    assert mock_updater.update_passport.call_count == 1

    # Сразу после первого события
    sync_handler.on_any_event(event)
    assert mock_updater.update_passport.call_count == 1  # Не должно увеличиться

    # После интервала
    time.sleep(1.1)
    sync_handler.on_any_event(event)
    assert mock_updater.update_passport.call_count == 2  # Должно увеличиться

def test_multiple_files(sync_handler, mock_updater):
    """Тест обработки нескольких файлов"""
    files = ['test1.py', 'test2.py', 'test3.py']

    # Создаем события для всех файлов
    for file in files:
        event = FileModifiedEvent(file)
        sync_handler.on_any_event(event)

    # Проверяем, что обновление произошло только один раз
    assert mock_updater.update_passport.call_count == 1

    # Ждем интервал и проверяем снова
    time.sleep(1.1)
    for file in files:
        event = FileModifiedEvent(file)
        sync_handler.on_any_event(event)

    # Проверяем, что обновление произошло еще один раз
    assert mock_updater.update_passport.call_count == 2

def test_change_report_initialization(change_report):
    """Тест инициализации отчета об изменениях"""
    assert isinstance(change_report.changes, dict)
    assert 'added_files' in change_report.changes
    assert 'removed_files' in change_report.changes
    assert 'modified_files' in change_report.changes
    assert 'added_dirs' in change_report.changes
    assert 'removed_dirs' in change_report.changes
    assert isinstance(change_report.timestamp, float)

def test_change_report_to_dict(change_report):
    """Тест преобразования отчета в словарь"""
    report_dict = change_report.to_dict()
    assert isinstance(report_dict, dict)
    assert 'changes' in report_dict
    assert 'timestamp' in report_dict
    assert 'formatted_time' in report_dict

def test_change_report_to_markdown(change_report):
    """Тест форматирования отчета в markdown"""
    # Добавляем тестовые изменения
    change_report.changes['added_files'].append('test.py')
    change_report.changes['modified_files'].append('main.py')

    markdown = change_report.to_markdown()
    assert isinstance(markdown, str)
    assert '# Отчет об изменениях' in markdown
    assert '## Добавленные файлы' in markdown
    assert '## Измененные файлы' in markdown
    assert '- test.py' in markdown
    assert '- main.py' in markdown

def test_change_report_empty(change_report):
    """Тест пустого отчета"""
    markdown = change_report.to_markdown()
    assert 'Изменений не обнаружено' in markdown

def test_pending_changes(sync_handler, mock_updater):
    """Тест накопления изменений"""
    # Создаем события разных типов
    events = [
        FileCreatedEvent('test1.py'),
        FileModifiedEvent('test2.py'),
        FileDeletedEvent('test3.py')
    ]

    # Обрабатываем события
    for event in events:
        sync_handler.on_any_event(event)

    # Проверяем накопленные изменения
    changes = sync_handler.get_pending_changes()
    assert 'test1.py' in changes.changes['added_files']
    assert 'test2.py' in changes.changes['modified_files']
    assert 'test3.py' in changes.changes['removed_files']

def test_clear_pending_changes(sync_handler, mock_updater):
    """Тест очистки накопленных изменений"""
    # Добавляем изменения
    sync_handler.on_any_event(FileCreatedEvent('test.py'))

    # Проверяем, что изменения накопились
    changes = sync_handler.get_pending_changes()
    assert 'test.py' in changes.changes['added_files']

    # Очищаем изменения
    sync_handler.clear_pending_changes()

    # Проверяем, что изменения очищены
    changes = sync_handler.get_pending_changes()
    assert not any(changes.changes.values())

def test_apply_changes(sync_handler, mock_updater):
    """Тест применения изменений"""
    # Добавляем изменения
    sync_handler.on_any_event(FileCreatedEvent('test.py'))

    # Применяем изменения
    assert sync_handler.apply_changes()
    mock_updater.update_passport.assert_called_once()

    # Проверяем, что изменения очищены после применения
    changes = sync_handler.get_pending_changes()
    assert not any(changes.changes.values())

def test_apply_changes_no_changes(sync_handler, mock_updater):
    """Тест применения изменений при их отсутствии"""
    assert sync_handler.apply_changes()
    mock_updater.update_passport.assert_not_called()

def test_apply_changes_error(sync_handler, mock_updater):
    """Тест обработки ошибки при применении изменений"""
    # Симулируем ошибку
    mock_updater.update_passport.return_value = False

    # Добавляем изменения
    sync_handler.on_any_event(FileCreatedEvent('test.py'))

    # Пытаемся применить изменения
    assert not sync_handler.apply_changes()

    # Проверяем, что изменения не очищены
    changes = sync_handler.get_pending_changes()
    assert 'test.py' in changes.changes['added_files']
