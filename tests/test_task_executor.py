def test_feedback_system_integration(task_executor, sample_task):
    """Тест интеграции системы обратной связи с TaskExecutor."""
    # Выполняем задачу три раза
    for _ in range(3):
        result = task_executor.execute_task(sample_task)
        assert result is not None
        assert result.get('status') == 'completed'
    
    # Проверяем метрики
    metrics = task_executor.feedback_system.get_task_metrics(sample_task.id)
    assert len(metrics) == 3
    
    # Проверяем анализ производительности
    analysis = task_executor.feedback_system.analyze_task_performance(sample_task.id)
    assert analysis['total_executions'] == 3
    assert 'execution_time' in analysis
    assert 'average_execution_time' in analysis
    assert 'success_rate' in analysis
    assert 'resource_usage' in analysis
    
    # Проверяем корректировку параметров
    adjusted_params = task_executor.feedback_system.adjust_task_parameters(sample_task.id)
    assert adjusted_params is not None
    assert 'param1' in adjusted_params
    assert adjusted_params['param1'].endswith('_optimized')
    assert 'optimization_level' in adjusted_params
    assert 'last_optimized' in adjusted_params

def test_task_performance_analysis(task_executor, sample_task):
    """Тест анализа производительности задачи."""
    # Создаем новый экземпляр FeedbackSystem с временным файлом
    task_executor.feedback_system = FeedbackSystem(use_temp_file=True)
    
    # Выполняем задачу три раза
    for _ in range(3):
        result = task_executor.execute_task(sample_task)
        assert result is not None
        assert result.get('status') == 'completed'
    
    # Получаем анализ производительности
    analysis = task_executor.feedback_system.analyze_task_performance(sample_task.id)
    
    # Проверяем результаты анализа
    assert analysis['total_executions'] == 3
    assert 'execution_time' in analysis
    assert 'average_execution_time' in analysis
    assert 'success_rate' in analysis
    assert 'resource_usage' in analysis
    assert analysis['success_rate'] == 1.0  # Все выполнения успешны 