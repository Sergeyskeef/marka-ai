import pytest
import json
from pathlib import Path
from datetime import datetime
from core.feedback_system import FeedbackSystem

@pytest.fixture
def feedback_system(tmp_path):
    metrics_file = tmp_path / "test_metrics.json"
    return FeedbackSystem(str(metrics_file))

@pytest.fixture
def sample_metrics():
    return {
        'execution_time': 45.5,
        'success': True,
        'cpu_usage': 75.0,
        'memory_usage': 65.0,
        'parameters': {
            'timeout': 30,
            'max_retries': 3,
            'max_parallel_tasks': 4,
            'buffer_size': 1024
        }
    }

def test_record_task_execution(feedback_system, sample_metrics):
    task_id = "test_task_1"
    feedback_system.record_task_execution(task_id, sample_metrics)
    
    assert task_id in feedback_system.metrics
    assert len(feedback_system.metrics[task_id]) == 1
    assert 'timestamp' in feedback_system.metrics[task_id][0]
    assert feedback_system.metrics[task_id][0]['execution_time'] == 45.5

def test_analyze_task_performance(feedback_system, sample_metrics):
    task_id = "test_task_2"
    # Добавляем несколько записей для анализа
    for i in range(3):
        metrics = sample_metrics.copy()
        metrics['success'] = i < 2  # Два успешных, один неуспешный
        feedback_system.record_task_execution(task_id, metrics)
    
    analysis = feedback_system.analyze_task_performance(task_id)
    
    assert analysis['total_executions'] == 3
    assert analysis['average_execution_time'] == 45.5
    assert analysis['success_rate'] == pytest.approx(2/3)
    assert analysis['resource_usage']['cpu'] == 75.0
    assert analysis['resource_usage']['memory'] == 65.0

def test_get_optimization_suggestions(feedback_system):
    task_id = "test_task_3"
    # Добавляем метрики с высоким использованием ресурсов
    metrics = {
        'execution_time': 90.0,
        'success': True,
        'cpu_usage': 85.0,
        'memory_usage': 90.0,
        'parameters': {
            'timeout': 30,
            'max_retries': 3,
            'max_parallel_tasks': 4,
            'buffer_size': 1024
        }
    }
    feedback_system.record_task_execution(task_id, metrics)
    
    suggestions = feedback_system.get_optimization_suggestions(task_id)
    
    assert len(suggestions) > 0
    assert any(s['type'] == 'execution_time' for s in suggestions)
    assert any(s['type'] == 'resource_usage' for s in suggestions)

def test_adjust_task_parameters(feedback_system):
    task_id = "test_task_4"
    # Добавляем метрики с низкой успешностью
    metrics = {
        'execution_time': 30.0,
        'success': False,
        'cpu_usage': 90.0,
        'memory_usage': 85.0,
        'parameters': {
            'timeout': 30,
            'max_retries': 3,
            'max_parallel_tasks': 4,
            'buffer_size': 1024
        }
    }
    feedback_system.record_task_execution(task_id, metrics)
    
    adjusted_params = feedback_system.adjust_task_parameters(task_id)
    
    assert adjusted_params['timeout'] == 45  # 30 * 1.5
    assert adjusted_params['max_retries'] == 4
    assert adjusted_params['max_parallel_tasks'] == 3
    assert adjusted_params['buffer_size'] == 512

def test_empty_metrics(feedback_system):
    task_id = "non_existent_task"
    
    analysis = feedback_system.analyze_task_performance(task_id)
    assert analysis == {}
    
    suggestions = feedback_system.get_optimization_suggestions(task_id)
    assert suggestions == []
    
    adjusted_params = feedback_system.adjust_task_parameters(task_id)
    assert adjusted_params == {} 