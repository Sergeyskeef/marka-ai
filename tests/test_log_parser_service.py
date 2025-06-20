import pytest
from pathlib import Path
from datetime import datetime, timedelta
from services.log_parser_service import LogParserService

@pytest.fixture
def log_parser(tmp_path):
    # Создаем временную директорию для логов
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return LogParserService(str(logs_dir))

@pytest.fixture
def sample_log_file(log_parser):
    # Создаем тестовый лог-файл с текущей датой
    log_file = log_parser.logs_dir / "test.log"
    now = datetime.now()
    log_content = f"""
{now.strftime('%Y-%m-%d %H:%M:%S')} INFO: Test info message
{now.strftime('%Y-%m-%d %H:%M:%S')} ERROR: Test error message
{now.strftime('%Y-%m-%d %H:%M:%S')} WARNING: Test warning message
{now.strftime('%Y-%m-%d %H:%M:%S')} DEBUG: Test debug message
"""
    log_file.write_text(log_content)
    return log_file

def test_get_log_files(log_parser, tmp_path):
    # Создаем тестовые лог-файлы
    (log_parser.logs_dir / "test1.log").touch()
    (log_parser.logs_dir / "test2.log").touch()
    
    log_files = log_parser.get_log_files()
    
    assert len(log_files) == 2
    assert all(f.suffix == '.log' for f in log_files)

def test_parse_log_file(log_parser, sample_log_file):
    entries = log_parser.parse_log_file(sample_log_file)
    
    assert len(entries) == 4
    assert entries[0]['level'] == 'info'
    assert entries[1]['level'] == 'error'
    assert entries[2]['level'] == 'warning'
    assert entries[3]['level'] == 'debug'

def test_get_recent_changes(log_parser, sample_log_file):
    # Убедимся, что файл существует и доступен
    assert sample_log_file.exists()
    assert sample_log_file.is_file()
    
    changes = log_parser.get_recent_changes(hours=24)
    
    assert len(changes) == 4
    assert all('timestamp' in entry for entry in changes)
    assert all('level' in entry for entry in changes)

def test_get_errors(log_parser, sample_log_file):
    # Убедимся, что файл существует и доступен
    assert sample_log_file.exists()
    assert sample_log_file.is_file()
    
    errors = log_parser.get_errors(hours=24)
    
    assert len(errors) == 1
    assert errors[0]['level'] == 'error'

def test_get_changes_summary(log_parser, sample_log_file):
    # Убедимся, что файл существует и доступен
    assert sample_log_file.exists()
    assert sample_log_file.is_file()
    
    summary = log_parser.get_changes_summary(hours=24)
    
    assert summary['total_entries'] == 4
    assert summary['errors'] == 1
    assert summary['warnings'] == 1
    assert summary['info'] == 1
    assert summary['debug'] == 1
    assert summary['files_modified'] == 1

def test_parse_log_line(log_parser):
    line = "2024-03-30 10:00:00 INFO: Test message"
    entry = log_parser._parse_log_line(line, "test.log")
    
    assert entry['timestamp'] == "2024-03-30 10:00:00"
    assert entry['level'] == 'info'
    assert entry['file'] == "test.log"
    assert "Test message" in entry['message']

def test_empty_log_line(log_parser):
    entry = log_parser._parse_log_line("", "test.log")
    assert entry is None

def test_invalid_log_line(log_parser):
    entry = log_parser._parse_log_line("Invalid log line", "test.log")
    assert entry['timestamp'] is None
    assert entry['level'] is None 