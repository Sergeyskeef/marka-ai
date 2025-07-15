import pytest
import json
import os
from datetime import datetime
from pathlib import Path
from scripts.self_analysis import SelfAnalyzer

@pytest.fixture
def analyzer(tmp_path):
    """Создаёт тестовую среду с временными файлами"""
    # Создаём временную структуру директорий
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    
    # Создаём тестовые логи
    with open(logs_dir / "test.log", "w", encoding="utf-8") as f:
        f.write("2025-03-20 10:00:00 INFO: Система запущена\n")
        f.write("2025-03-20 10:01:00 WARNING: Высокая нагрузка на память\n")
        f.write("2025-03-20 10:02:00 ERROR: Ошибка подключения к базе данных\n")
    
    # Создаём тестовый паспорт
    passport = {
        "version": "1.0.0",
        "last_update": datetime.now().isoformat(),
        "components": {
            "memory": {"status": "active"},
            "sandbox": {"status": "active"}
        }
    }
    
    with open(tmp_path / "marka_passport.json", "w", encoding="utf-8") as f:
        json.dump(passport, f)
    
    # Создаём тестовый лог песочницы
    with open(tmp_path / "sandbox_experiments.log", "w", encoding="utf-8") as f:
        f.write("2025-03-20 11:00:00 INFO: Запуск эксперимента\n")
        f.write("2025-03-20 11:01:00 WARNING: Медленный ответ от API\n")
    
    return SelfAnalyzer(project_root=str(tmp_path))

def test_analyze_logs(analyzer):
    """Тест анализа логов"""
    stats = analyzer.analyze_logs()
    
    assert 'errors' in stats
    assert 'warnings' in stats
    assert 'info' in stats
    assert 'last_update' in stats
    
    assert len(stats['errors']) > 0
    assert len(stats['warnings']) > 0
    assert len(stats['info']) > 0

def test_analyze_passport(analyzer):
    """Тест анализа паспорта"""
    stats = analyzer.analyze_passport()
    
    assert 'version' in stats
    assert 'last_update' in stats
    assert 'components' in stats
    assert 'status' in stats
    
    assert stats['status'] == 'valid'
    assert stats['version'] == '1.0.0'

def test_generate_report(analyzer):
    """Тест генерации отчёта"""
    report = analyzer.generate_report()
    
    assert 'timestamp' in report
    assert 'system_health' in report
    assert 'memory_status' in report
    assert 'performance_status' in report
    assert 'passport_status' in report
    assert 'recommendations' in report
    
    assert report['system_health']['status'] in ['good', 'warning', 'error']
    assert report['memory_status']['status'] in ['good', 'warning', 'error']
    assert report['performance_status']['status'] in ['good', 'warning', 'error']

def test_get_analysis(analyzer):
    """Тест получения человеко-понятного отчёта"""
    analysis = analyzer.get_analysis()
    
    assert isinstance(analysis, str)
    assert "Отчёт о состоянии системы" in analysis
    assert "Общее состояние" in analysis
    assert "Состояние памяти" in analysis
    assert "Производительность" in analysis
    assert "Статус паспорта" in analysis
    assert "Рекомендации" in analysis

def test_error_handling(analyzer, tmp_path):
    """Тест обработки ошибок"""
    # Создаём невалидный паспорт
    with open(tmp_path / "marka_passport.json", "w", encoding="utf-8") as f:
        f.write("invalid json")
    
    stats = analyzer.analyze_passport()
    assert stats['status'] == 'error'
    assert 'error' in stats

def test_performance(analyzer):
    """Тест производительности анализа"""
    import time
    
    start_time = time.time()
    for _ in range(100):  # 100 итераций для проверки производительности
        analyzer.get_analysis()
    end_time = time.time()
    
    # Проверяем, что анализ 100 отчётов занимает не более 5 секунд
    assert end_time - start_time < 5.0

def test_analyze_codebase(analyzer):
    """Тест анализа кодовой базы"""
    code_quality = analyzer.analyze_codebase()
    
    assert 'status' in code_quality
    assert 'message' in code_quality
    assert 'metrics' in code_quality
    
    metrics = code_quality['metrics']
    assert 'total_files' in metrics
    assert 'total_classes' in metrics
    assert 'total_functions' in metrics
    assert 'total_imports' in metrics
    assert 'avg_methods_per_class' in metrics
    assert 'avg_args_per_function' in metrics
    assert 'test_files' in metrics
    
    assert code_quality['status'] in ['good', 'warning', 'error']

def test_code_quality_recommendations(analyzer):
    """Тест рекомендаций по качеству кода"""
    # Создаем тестовые метрики с низким покрытием тестами
    code_quality = {
        'status': 'warning',
        'metrics': {
            'total_files': 100,
            'test_files': 20,  # 20% покрытия
            'avg_methods_per_class': 12  # Высокая сложность
        }
    }
    
    recommendations = analyzer._generate_recommendations(
        {'errors': [], 'warnings': []},
        {'status': 'valid'},
        code_quality
    )
    
    assert "увеличить покрытие тестами" in ' '.join(recommendations)
    assert "уменьшить сложность классов" in ' '.join(recommendations)

def test_code_quality_in_report(analyzer):
    """Тест включения качества кода в отчет"""
    report = analyzer.generate_report()
    
    assert 'code_quality' in report
    assert 'status' in report['code_quality']
    assert 'message' in report['code_quality']
    assert 'metrics' in report['code_quality']
    
    # Проверяем, что метрики кода включены в человеко-понятный отчет
    analysis = analyzer.get_analysis()
    assert "Качество кода:" in analysis
    assert "Метрики кода:" in analysis
    assert "Всего файлов:" in analysis
    assert "Всего классов:" in analysis
    assert "Всего функций:" in analysis 