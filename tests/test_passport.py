import os
import json
import pytest
import datetime
from pathlib import Path
from scripts.update_passport import PassportUpdater
from unittest.mock import MagicMock, patch

@pytest.fixture
def project_root(tmp_path):
    """Создает временную директорию для тестов"""
    return tmp_path

@pytest.fixture
def passport_updater(project_root):
    """Создает экземпляр PassportUpdater"""
    return PassportUpdater(project_root)

@pytest.fixture
def sample_passport():
    """Возвращает пример паспорта"""
    return {
        'version': '1.0',
        'project_structure': {
            'files': ['main.py', 'test.py'],
            'directories': ['src', 'tests'],
            'python_modules': ['src/module.py']
        },
        'commands': [
            {'name': '/start', 'description': 'Start command', 'module': 'telegram_bot/bot.py'}
        ],
        'last_update': datetime.datetime.now().isoformat()
    }

@pytest.fixture
def mock_weaviate_client():
    """Создает мок клиента Weaviate"""
    with patch('weaviate.Client') as mock_client:
        client = MagicMock()
        client.schema.exists.return_value = False
        mock_client.return_value = client
        yield client

def test_scan_project_structure(passport_updater):
    """Тест сканирования структуры проекта"""
    structure = passport_updater.scan_project_structure()
    
    # Проверяем наличие основных директорий
    assert 'app' in structure['directories']
    assert 'scripts' in structure['directories']
    assert 'tests' in structure['directories']
    
    # Проверяем наличие основных файлов
    assert 'main.py' in [Path(f).name for f in structure['files']]
    assert 'README.md' in [Path(f).name for f in structure['files']]
    
    # Проверяем наличие Python-модулей
    assert 'bot.py' in [Path(f).name for f in structure['python_modules']]
    assert 'update_passport.py' in [Path(f).name for f in structure['python_modules']]

def test_passport_update(passport_updater):
    """Тест обновления паспорта"""
    # Сохраняем оригинальный паспорт
    original_passport = passport_updater.passport.copy()
    
    # Обновляем паспорт
    assert passport_updater.update_passport()
    
    # Проверяем, что паспорт обновился
    assert passport_updater.passport['last_update'] != original_passport['last_update']
    assert 'project_structure' in passport_updater.passport
    
    # Проверяем структуру проекта
    structure = passport_updater.passport['project_structure']
    assert 'files' in structure
    assert 'directories' in structure
    assert 'python_modules' in structure

def test_command_scanning(passport_updater):
    """Тест сканирования команд"""
    commands = passport_updater.scan_commands()
    
    # Проверяем, что команды не пусты
    assert len(commands) > 0
    
    # Проверяем структуру команд
    for cmd in commands:
        assert 'name' in cmd
        assert 'description' in cmd
        assert 'module' in cmd

def test_passport_versioning(passport_updater):
    """Тест версионирования паспорта"""
    # Обновляем паспорт
    passport_updater.update_passport()
    
    # Проверяем наличие версии
    assert 'version' in passport_updater.passport
    
    # Проверяем формат версии
    version = passport_updater.passport['version']
    assert isinstance(version, str)
    assert '.' in version

def test_error_handling(passport_updater):
    """Тест обработки ошибок"""
    # Тест с несуществующим путем
    invalid_updater = PassportUpdater('/invalid/path')
    assert not invalid_updater.update_passport()
    
    # Тест с некорректным JSON
    with open(passport_updater.passport_path, 'w') as f:
        f.write('invalid json')
    
    # Должен создать новый паспорт при ошибке
    assert passport_updater.update_passport()
    assert isinstance(passport_updater.passport, dict)

def test_integration_with_weaviate(passport_updater):
    """Интеграционный тест с Weaviate"""
    # TODO: Добавить тест после реализации сохранения снапшотов в Weaviate
    pass

def test_load_version_history(passport_updater, project_root):
    """Тест загрузки истории версий"""
    # Создаем тестовую историю версий
    history = [
        {
            'version': '1.0',
            'timestamp': datetime.datetime.now().isoformat(),
            'passport': {'version': '1.0'},
            'changes': {}
        }
    ]
    history_path = Path(project_root) / 'passport_history.json'
    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f)
        
    # Проверяем загрузку
    loaded_history = passport_updater._load_version_history()
    assert len(loaded_history) == 1
    assert loaded_history[0]['version'] == '1.0'

def test_create_version_snapshot(passport_updater, sample_passport):
    """Тест создания снапшота версии"""
    passport_updater.passport = sample_passport
    passport_updater._create_version_snapshot()
    
    assert len(passport_updater.version_history) == 1
    snapshot = passport_updater.version_history[0]
    assert snapshot['version'] == '1.0'
    assert 'timestamp' in snapshot
    assert 'passport' in snapshot
    assert 'changes' in snapshot

def test_detect_changes(passport_updater, sample_passport):
    """Тест определения изменений"""
    passport_updater.passport = sample_passport
    
    # Создаем новую структуру проекта
    new_structure = {
        'files': ['main.py', 'new_file.py'],
        'directories': ['src', 'new_dir'],
        'python_modules': ['src/module.py', 'src/new_module.py']
    }
    
    # Мокаем метод scan_project_structure
    passport_updater.scan_project_structure = lambda: new_structure
    
    changes = passport_updater._detect_changes()
    
    assert 'new_file.py' in changes['added_files']
    assert 'new_dir' in changes['added_dirs']
    assert 'src/new_module.py' in changes['added_modules']
    assert 'test.py' in changes['removed_files']

def test_increment_version(passport_updater, sample_passport):
    """Тест увеличения версии"""
    passport_updater.passport = sample_passport
    passport_updater._increment_version()
    assert passport_updater.passport['version'] == '1.1'

def test_update_passport_with_versioning(passport_updater, sample_passport):
    """Тест обновления паспорта с версионированием"""
    passport_updater.passport = sample_passport
    
    # Создаем тестовую структуру проекта
    test_structure = {
        'files': ['main.py'],
        'directories': ['src'],
        'python_modules': ['src/module.py']
    }
    passport_updater.scan_project_structure = lambda: test_structure
    
    # Обновляем паспорт
    assert passport_updater.update_passport()
    
    # Проверяем результаты
    assert passport_updater.passport['version'] == '1.1'
    assert len(passport_updater.version_history) == 1
    assert 'last_update' in passport_updater.passport

def test_error_handling(passport_updater):
    """Тест обработки ошибок"""
    # Тест с несуществующей директорией
    passport_updater.project_root = Path('/non_existent_path')
    assert not passport_updater.update_passport()
    
    # Тест с некорректным паспортом
    passport_updater.passport = {'version': 'invalid'}
    assert not passport_updater._increment_version()

def test_integration_with_weaviate(passport_updater, sample_passport):
    """Тест интеграции с Weaviate"""
    # TODO: Добавить тесты интеграции с Weaviate после реализации
    pass

def test_init_weaviate(passport_updater, mock_weaviate_client):
    """Тест инициализации Weaviate"""
    assert passport_updater.weaviate_client is not None
    mock_weaviate_client.schema.create_class.assert_called_once()

def test_save_to_weaviate(passport_updater, mock_weaviate_client, sample_passport):
    """Тест сохранения в Weaviate"""
    snapshot = {
        'version': '1.0',
        'timestamp': datetime.datetime.now().isoformat(),
        'passport': sample_passport,
        'changes': {}
    }
    
    assert passport_updater._save_to_weaviate(snapshot)
    mock_weaviate_client.data_object.create.assert_called_once()

def test_load_from_weaviate(passport_updater, mock_weaviate_client):
    """Тест загрузки из Weaviate"""
    # Настраиваем мок для возврата тестовых данных
    mock_weaviate_client.query.get.return_value.with_where.return_value.do.return_value = {
        "data": {
            "Get": {
                "PassportSnapshot": [{
                    "version": "1.0",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "passport": json.dumps({"version": "1.0"}),
                    "changes": json.dumps({})
                }]
            }
        }
    }
    
    snapshot = passport_updater._load_from_weaviate("1.0")
    assert snapshot is not None
    assert snapshot["version"] == "1.0"

def test_get_version(passport_updater, mock_weaviate_client, sample_passport):
    """Тест получения версии"""
    # Добавляем версию в локальную историю
    passport_updater.passport = sample_passport
    passport_updater._create_version_snapshot()
    
    # Проверяем получение версии
    version = passport_updater.get_version("1.0")
    assert version is not None
    assert version["version"] == "1.0"
    
    # Проверяем получение несуществующей версии
    version = passport_updater.get_version("2.0")
    assert version is None

def test_rollback_to_version(passport_updater, mock_weaviate_client, sample_passport):
    """Тест отката к версии"""
    # Добавляем версию в локальную историю
    passport_updater.passport = sample_passport
    passport_updater._create_version_snapshot()
    
    # Проверяем откат к существующей версии
    assert passport_updater.rollback_to_version("1.0")
    assert passport_updater.passport["version"] == "1.0"
    
    # Проверяем откат к несуществующей версии
    assert not passport_updater.rollback_to_version("2.0")

def test_version_history_integration(passport_updater, mock_weaviate_client, sample_passport):
    """Интеграционный тест версионирования"""
    # Создаем несколько версий
    passport_updater.passport = sample_passport
    passport_updater._create_version_snapshot()  # v1.0
    
    passport_updater.passport["version"] = "1.1"
    passport_updater._create_version_snapshot()  # v1.1
    
    # Проверяем историю версий
    history = passport_updater.get_version_history()
    assert len(history) == 2
    assert history[0]["version"] == "1.0"
    assert history[1]["version"] == "1.1"
    
    # Проверяем откат к предыдущей версии
    assert passport_updater.rollback_to_version("1.0")
    assert passport_updater.passport["version"] == "1.0"

def test_error_handling_weaviate(passport_updater, mock_weaviate_client):
    """Тест обработки ошибок Weaviate"""
    # Симулируем ошибку при сохранении
    mock_weaviate_client.data_object.create.side_effect = Exception("Test error")
    
    snapshot = {
        'version': '1.0',
        'timestamp': datetime.datetime.now().isoformat(),
        'passport': {},
        'changes': {}
    }
    
    assert not passport_updater._save_to_weaviate(snapshot)
    
    # Симулируем ошибку при загрузке
    mock_weaviate_client.query.get.side_effect = Exception("Test error")
    assert passport_updater._load_from_weaviate("1.0") is None 