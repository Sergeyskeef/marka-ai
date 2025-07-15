"""
Тесты для модуля task_analyzer.py.
"""

import json
from datetime import datetime, timedelta

import pytest

from utils.task_analyzer import TaskAnalysis, TaskAnalyzer, TaskMetrics


@pytest.fixture
def task_analyzer():
    """Фикстура для создания экземпляра TaskAnalyzer."""
    return TaskAnalyzer()

@pytest.fixture
def sample_metrics():
    """Фикстура для создания тестовых метрик."""
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=5)
    return TaskMetrics(
        task_id="test_task_1",
        task_type="development",
        start_time=start_time,
        end_time=end_time,
        cpu_usage=50.0,
        memory_usage=30.0,
        success=True,
        error_message=None,
        execution_time=300.0
    )

def test_add_metrics(task_analyzer, sample_metrics):
    """Тест добавления метрик."""
    task_analyzer.add_metrics(sample_metrics)
    assert len(task_analyzer.metrics_history) == 1
    assert task_analyzer.metrics_history[0].task_id == "test_task_1"

def test_analyze_task(task_analyzer, sample_metrics):
    """Тест анализа задачи."""
    task_analyzer.add_metrics(sample_metrics)
    analysis = task_analyzer.analyze_task("test_task_1")

    assert isinstance(analysis, TaskAnalysis)
    assert analysis.task_id == "test_task_1"
    assert analysis.task_type == "development"
    assert 0 <= analysis.performance_score <= 1
    assert 0 <= analysis.resource_efficiency <= 1
    assert isinstance(analysis.recommendations, list)
    assert isinstance(analysis.patterns, list)

def test_analyze_nonexistent_task(task_analyzer):
    """Тест анализа несуществующей задачи."""
    with pytest.raises(ValueError):
        task_analyzer.analyze_task("nonexistent_task")

def test_calculate_performance_score(task_analyzer, sample_metrics):
    """Тест расчета оценки производительности."""
    score = task_analyzer._calculate_performance_score(sample_metrics)
    assert 0 <= score <= 1

def test_calculate_resource_efficiency(task_analyzer, sample_metrics):
    """Тест расчета эффективности использования ресурсов."""
    efficiency = task_analyzer._calculate_resource_efficiency(sample_metrics)
    assert 0 <= efficiency <= 1

def test_generate_recommendations(task_analyzer):
    """Тест генерации рекомендаций."""
    # Тест с высоким использованием CPU
    high_cpu_metrics = TaskMetrics(
        task_id="high_cpu_task",
        task_type="system",
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(minutes=1),
        cpu_usage=90.0,
        memory_usage=30.0,
        success=True,
        error_message=None,
        execution_time=60.0
    )

    recommendations = task_analyzer._generate_recommendations(high_cpu_metrics)
    assert "Оптимизировать использование CPU" in recommendations

    # Тест с ошибкой
    failed_metrics = TaskMetrics(
        task_id="failed_task",
        task_type="development",
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(minutes=1),
        cpu_usage=30.0,
        memory_usage=30.0,
        success=False,
        error_message="Test error",
        execution_time=60.0
    )

    recommendations = task_analyzer._generate_recommendations(failed_metrics)
    assert "Исправить ошибку: Test error" in recommendations

def test_identify_patterns(task_analyzer):
    """Тест выявления паттернов."""
    # Добавляем несколько задач одного типа
    base_time = datetime.now()
    for i in range(3):
        metrics = TaskMetrics(
            task_id=f"task_{i}",
            task_type="development",
            start_time=base_time + timedelta(minutes=i),
            end_time=base_time + timedelta(minutes=i+5),
            cpu_usage=50.0,
            memory_usage=30.0,
            success=True,
            error_message=None,
            execution_time=300.0
        )
        task_analyzer.add_metrics(metrics)

    # Добавляем задачу с аномальным временем выполнения
    anomaly_metrics = TaskMetrics(
        task_id="anomaly_task",
        task_type="development",
        start_time=base_time + timedelta(minutes=10),
        end_time=base_time + timedelta(minutes=20),
        cpu_usage=50.0,
        memory_usage=30.0,
        success=True,
        error_message=None,
        execution_time=600.0  # В два раза больше среднего
    )
    task_analyzer.add_metrics(anomaly_metrics)

    patterns = task_analyzer._identify_patterns(anomaly_metrics)
    assert "Время выполнения значительно выше среднего" in patterns

def test_get_task_statistics(task_analyzer, sample_metrics):
    """Тест получения статистики."""
    task_analyzer.add_metrics(sample_metrics)
    stats = task_analyzer.get_task_statistics()

    assert stats["total_tasks"] == 1
    assert stats["successful_tasks"] == 1
    assert stats["success_rate"] == 1.0
    assert stats["average_execution_time"] == 300.0
    assert stats["average_cpu_usage"] == 50.0
    assert stats["average_memory_usage"] == 30.0

def test_export_analysis(task_analyzer, sample_metrics, tmp_path):
    """Тест экспорта анализа."""
    task_analyzer.add_metrics(sample_metrics)
    task_analyzer.analyze_task("test_task_1")

    export_path = tmp_path / "analysis.json"
    task_analyzer.export_analysis(str(export_path))

    assert export_path.exists()
    with open(export_path, encoding='utf-8') as f:
        data = json.load(f)
        assert "task_metrics" in data
        assert "statistics" in data
        assert len(data["task_metrics"]) == 1
        assert data["task_metrics"][0]["task_id"] == "test_task_1"
        assert data["task_metrics"][0]["task_type"] == "development"
        assert data["task_metrics"][0]["start_time"] == str(sample_metrics.start_time)
        assert data["task_metrics"][0]["end_time"] == str(sample_metrics.end_time)
        assert data["task_metrics"][0]["cpu_usage"] == 50.0
        assert data["task_metrics"][0]["memory_usage"] == 30.0
        assert data["task_metrics"][0]["success"] is True
        assert data["statistics"]["total_tasks"] == 1
        assert data["statistics"]["successful_tasks"] == 1
        assert data["statistics"]["success_rate"] == 1.0
        assert data["statistics"]["average_execution_time"] == 300.0
        assert data["statistics"]["average_cpu_usage"] == 50.0
        assert data["statistics"]["average_memory_usage"] == 30.0
