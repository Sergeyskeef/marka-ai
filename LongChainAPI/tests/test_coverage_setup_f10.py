"""
Тесты для задачи F-10: Coverage ≥ 50% & CI-rule
"""
import sys
sys.path.insert(0, '/workspace')
import os


def test_github_action():
    """Тест наличия GitHub Action для coverage"""
    print("\n=== Тест GitHub Action ===")
    
    # Проверяем файл workflow
    workflow_path = '/workspace/.github/workflows/test-coverage.yml'
    assert os.path.exists(workflow_path)
    print("✅ GitHub Action workflow существует")
    
    # Читаем содержимое
    with open(workflow_path, 'r') as f:
        content = f.read()
    
    # Проверяем ключевые элементы
    assert 'Test Coverage Check' in content
    print("✅ Название workflow корректное")
    
    assert 'pytest --cov' in content
    print("✅ Запуск pytest с coverage")
    
    assert 'COVERAGE < 50' in content
    print("✅ Проверка минимального покрытия 50%")
    
    assert 'coverage report' in content
    print("✅ Генерация отчета покрытия")
    
    assert 'Comment PR with coverage' in content
    print("✅ Комментирование PR с результатами")


def test_pytest_config():
    """Тест конфигурации pytest"""
    print("\n=== Тест конфигурации pytest ===")
    
    # Проверяем pytest.ini
    config_path = '/workspace/pytest.ini'
    assert os.path.exists(config_path)
    print("✅ pytest.ini существует")
    
    with open(config_path, 'r') as f:
        content = f.read()
    
    # Проверяем настройки
    assert '[pytest]' in content
    assert 'testpaths = tests' in content
    print("✅ Путь к тестам настроен")
    
    assert '[coverage:run]' in content
    assert 'source = .' in content
    print("✅ Настройки coverage определены")
    
    assert 'omit =' in content
    assert '*/tests/*' in content
    print("✅ Исключения из покрытия настроены")
    
    assert '[coverage:report]' in content
    assert 'show_missing = True' in content
    print("✅ Отчет покрытия настроен")


def test_coverage_script():
    """Тест скрипта проверки покрытия"""
    print("\n=== Тест скрипта coverage ===")
    
    # Проверяем скрипт
    script_path = '/workspace/scripts/check_coverage.sh'
    assert os.path.exists(script_path)
    print("✅ Скрипт check_coverage.sh существует")
    
    # Проверяем права на выполнение
    assert os.access(script_path, os.X_OK)
    print("✅ Скрипт исполняемый")
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Проверяем функциональность
    assert 'pytest --cov' in content
    print("✅ Запуск pytest с coverage")
    
    assert 'COVERAGE < 50' in content
    print("✅ Проверка минимального покрытия")
    
    assert 'HTML отчет' in content
    print("✅ Генерация HTML отчета")


def test_tests_structure():
    """Тест структуры тестов"""
    print("\n=== Тест структуры тестов ===")
    
    # Проверяем наличие директории tests
    tests_dir = '/workspace/tests'
    assert os.path.exists(tests_dir)
    assert os.path.isdir(tests_dir)
    print("✅ Директория tests существует")
    
    # Проверяем наличие README
    readme_path = os.path.join(tests_dir, 'README.md')
    assert os.path.exists(readme_path)
    print("✅ README.md для тестов существует")
    
    # Проверяем наличие тестов для каждой задачи
    test_files = [
        'test_sandbox_e2e.py',
        'test_sandbox_individual.py',
        'test_tools_registry_f2.py',
        'test_sandbox_exec_f4.py',
        'test_feedback_api_f5.py',
        'test_reflection_engine_f6.py',
        'test_error_middleware_f8.py'
    ]
    
    for test_file in test_files:
        path = os.path.join(tests_dir, test_file)
        assert os.path.exists(path), f"Файл {test_file} не найден"
    
    print(f"✅ Все {len(test_files)} тестовых файлов на месте")


def test_ci_integration():
    """Тест интеграции с CI"""
    print("\n=== Тест CI интеграции ===")
    
    # Проверяем workflow triggers
    with open('/workspace/.github/workflows/test-coverage.yml', 'r') as f:
        content = f.read()
    
    assert 'on:' in content
    assert 'push:' in content
    assert 'branches: [ main' in content
    print("✅ Workflow запускается на push в main")
    
    assert 'pull_request:' in content
    print("✅ Workflow запускается на PR")
    
    # Проверяем services
    assert 'services:' in content
    assert 'neo4j:' in content
    print("✅ Neo4j сервис настроен для тестов")
    
    # Проверяем artifacts
    assert 'Upload coverage reports' in content
    assert 'coverage.xml' in content
    assert 'htmlcov/' in content
    print("✅ Артефакты coverage сохраняются")


def main():
    print("🧪 Запуск тестов для F-10: Coverage ≥ 50% & CI-rule")
    
    test_github_action()
    test_pytest_config()
    test_coverage_script()
    test_tests_structure()
    test_ci_integration()
    
    print("\n🎉 Все тесты F-10 успешно пройдены!")
    print("\n📝 Рекомендации:")
    print("1. Запустите ./scripts/check_coverage.sh для локальной проверки")
    print("2. Создайте PR для проверки GitHub Action")
    print("3. Убедитесь, что покрытие ≥ 50%")


if __name__ == "__main__":
    main()