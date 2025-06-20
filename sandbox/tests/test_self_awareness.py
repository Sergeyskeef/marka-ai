import unittest
from datetime import datetime, timedelta
from langchain_api.sandbox.self_awareness import (
    MarkSelfAwareness,
    TaskResult,
    TaskAnalysis
)
import pytest
from pathlib import Path
import json
import shutil

class TestTaskSelfAnalysis(unittest.TestCase):
    def setUp(self):
        self.awareness = MarkSelfAwareness()
        
    def test_task_execution_analysis(self):
        # Создаем тестовый результат задачи
        task_result = TaskResult(
            task_id="test_task_1",
            status="completed",
            start_time=datetime.now() - timedelta(minutes=5),
            end_time=datetime.now(),
            success_rate=0.9,
            performance_metrics={
                "cpu_usage": 75,
                "memory_usage": 60
            },
            error_messages=["Timeout error occurred", "Network connection failed"],
            insights=["Task completed successfully", "Performance could be improved"]
        )
        
        # Анализируем выполнение задачи
        analysis = self.awareness.analyze_task_execution(task_result)
        
        # Проверяем результаты анализа
        self.assertIsNotNone(analysis.success_rate)
        self.assertIsNotNone(analysis.performance_score)
        self.assertIsNotNone(analysis.error_patterns)
        self.assertIsNotNone(analysis.recommendations)
        
        # Проверяем конкретные значения
        self.assertEqual(analysis.success_rate, 0.9)
        
    def test_error_categorization(self):
        task_result = TaskResult(
            task_id="test_task_2",
            status="failed",
            start_time=datetime.now() - timedelta(minutes=2),
            end_time=datetime.now(),
            success_rate=0.0,
            performance_metrics={},
            error_messages=[
                "Connection timeout after 30 seconds",
                "Memory limit exceeded",
                "Permission denied: cannot access file"
            ],
            insights=[]
        )
        
        analysis = self.awareness.analyze_task_execution(task_result)
        error_types = analysis.error_patterns
        
        self.assertEqual(error_types["timeout"], 1)
        self.assertEqual(error_types["memory"], 1)
        self.assertEqual(error_types["permission"], 1)
        
    def test_recommendations_generation(self):
        # Тест с высоким использованием ресурсов
        task_result = TaskResult(
            task_id="test_task_3",
            status="completed",
            start_time=datetime.now() - timedelta(minutes=1),
            end_time=datetime.now(),
            success_rate=0.7,
            performance_metrics={
                "cpu_usage": 90,
                "memory_usage": 85
            },
            error_messages=["Resource limit exceeded"],
            insights=[]
        )
        
        recommendations = self.awareness.get_task_recommendations(task_result)
        
        self.assertIn("Низкая эффективность использования ресурсов. Рекомендуется оптимизировать распределение ресурсов.", recommendations)
        self.assertIn("Низкий процент успешного выполнения. Рекомендуется проверить логи и обработаку ошибок.", recommendations)
        
    def test_efficiency_score_calculation(self):
        # Тест с хорошей производительностью
        task_result = TaskResult(
            task_id="test_task_4",
            status="completed",
            start_time=datetime.now() - timedelta(minutes=1),
            end_time=datetime.now(),
            success_rate=0.95,
            performance_metrics={
                "cpu_usage": 50,
                "memory_usage": 40
            },
            error_messages=[],
            insights=[]
        )
        
        analysis = self.awareness.analyze_task_execution(task_result)
        self.assertGreaterEqual(analysis.performance_score, 0.4)
        
        # Тест с плохой производительностью
        task_result.performance_metrics["cpu_usage"] = 90
        task_result.performance_metrics["memory_usage"] = 90
        analysis = self.awareness.analyze_task_execution(task_result)
        self.assertLess(analysis.performance_score, 0.8)

@pytest.fixture
def self_awareness(tmp_path):
    """Фикстура для MarkSelfAwareness"""
    awareness = MarkSelfAwareness()
    awareness.insights_dir = tmp_path / "insights"
    awareness.insights_dir.mkdir(exist_ok=True)
    return awareness

@pytest.fixture
def task_result():
    """Фикстура для TaskResult"""
    return TaskResult(
        task_id="test_task",
        status="completed",
        start_time=datetime.now() - timedelta(minutes=5),
        end_time=datetime.now(),
        success_rate=0.9,
        performance_metrics={
            "cpu_usage": 75.0,
            "memory_usage": 60.0,
            "execution_time": 300.0
        },
        error_messages=["Timeout error occurred"],
        insights=["Task completed successfully"]
    )

def test_analyze_task_execution(self_awareness, task_result):
    """Тест анализа выполнения задачи"""
    analysis = self_awareness.analyze_task_execution(task_result)
    
    assert isinstance(analysis, TaskAnalysis)
    assert analysis.task_id == task_result.task_id
    assert 0.0 <= analysis.success_rate <= 1.0
    assert 0.0 <= analysis.performance_score <= 1.0
    assert isinstance(analysis.error_patterns, dict)
    assert isinstance(analysis.recommendations, list)
    
    # Проверка сохранения в историю
    history = self_awareness.get_task_history(task_result.task_id)
    assert len(history) == 1
    assert history[0] == analysis

def test_calculate_performance_score(self_awareness):
    """Тест расчета оценки производительности"""
    metrics = {
        "cpu_usage": 75.0,
        "memory_usage": 60.0,
        "execution_time": 300.0
    }
    
    score = self_awareness._calculate_performance_score(metrics)
    assert 0.0 <= score <= 1.0
    
    # Тест с пустыми метриками
    empty_score = self_awareness._calculate_performance_score({})
    assert empty_score == 0.0

def test_analyze_error_patterns(self_awareness):
    """Тест анализа паттернов ошибок"""
    error_messages = [
        "Timeout error occurred",
        "Out of memory",
        "Permission denied: cannot access file",
        "Network connection failed",
        "Unknown error"
    ]
    
    patterns = self_awareness._analyze_error_patterns(error_messages)
    
    assert patterns["timeout"] == 1
    assert patterns["memory"] == 1
    assert patterns["permission"] == 1
    assert patterns["network"] == 1
    assert patterns["other"] == 1

def test_calculate_resource_efficiency(self_awareness):
    """Тест расчета эффективности ресурсов"""
    metrics = {
        "cpu_usage": 75.0,
        "memory_usage": 60.0
    }
    
    efficiency = self_awareness._calculate_resource_efficiency(metrics)
    assert 0.0 <= efficiency <= 1.0
    
    # Тест с пустыми метриками
    empty_efficiency = self_awareness._calculate_resource_efficiency({})
    assert empty_efficiency == 0.0

def test_generate_recommendations(self_awareness):
    """Тест генерации рекомендаций"""
    recommendations = self_awareness._generate_recommendations(
        success_rate=0.7,
        performance_score=0.6,
        error_patterns={
            "timeout": 2,
            "memory": 1,
            "permission": 0,
            "network": 0,
            "other": 0
        },
        resource_efficiency=0.5
    )
    
    assert isinstance(recommendations, list)
    assert len(recommendations) > 0
    assert all(isinstance(r, str) for r in recommendations)

def test_save_insights(self_awareness, task_result):
    """Тест сохранения инсайтов"""
    analysis = self_awareness.analyze_task_execution(task_result)
    
    # Проверка создания файла
    insight_files = list(self_awareness.insights_dir.glob("insight_*.json"))
    assert len(insight_files) == 1
    
    # Проверка содержимого
    with open(insight_files[0]) as f:
        insight = json.load(f)
        assert insight["task_id"] == task_result.task_id
        assert "timestamp" in insight
        assert "result" in insight
        assert "analysis" in insight

def test_get_task_recommendations(self_awareness, task_result):
    """Тест получения рекомендаций для задачи"""
    recommendations = self_awareness.get_task_recommendations(task_result)
    
    assert isinstance(recommendations, list)
    assert all(isinstance(r, str) for r in recommendations)

def test_get_task_history(self_awareness, task_result):
    """Тест получения истории анализа задачи"""
    # Добавляем несколько анализов
    analysis1 = self_awareness.analyze_task_execution(task_result)
    analysis2 = self_awareness.analyze_task_execution(task_result)
    
    history = self_awareness.get_task_history(task_result.task_id)
    assert len(history) == 2
    assert history[0] == analysis1
    assert history[1] == analysis2

def test_get_recent_insights(self_awareness, task_result):
    """Тест получения последних инсайтов"""
    # Создаем несколько инсайтов
    for i in range(3):
        task_result.task_id = f"test_task_{i}"
        self_awareness.analyze_task_execution(task_result)
    
    insights = self_awareness.get_recent_insights(limit=2)
    assert len(insights) == 2
    assert all(isinstance(i, dict) for i in insights)

if __name__ == '__main__':
    unittest.main() 