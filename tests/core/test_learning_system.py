import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch

from core.learning_system import LearningSystem
from core.memory.enhanced_memory import EnhancedMemory
from core.context.context_manager import ContextManager

@pytest.fixture
def mock_memory():
    """Фикстура для создания мока EnhancedMemory"""
    memory = Mock(spec=EnhancedMemory)
    memory.store_patterns = Mock()
    return memory

@pytest.fixture
def mock_context_manager():
    """Фикстура для создания мока ContextManager"""
    context_manager = Mock(spec=ContextManager)
    context_manager.get_current_context = Mock(return_value={'test_context': 'value'})
    return context_manager

@pytest.fixture
def learning_system(mock_memory, mock_context_manager):
    """Фикстура для создания экземпляра LearningSystem"""
    return LearningSystem(mock_memory, mock_context_manager)

def test_init(learning_system, mock_memory, mock_context_manager):
    """Тест инициализации LearningSystem"""
    assert learning_system.memory == mock_memory
    assert learning_system.context_manager == mock_context_manager
    assert learning_system.patterns == {}
    assert learning_system.learning_history == []

def test_analyze_action(learning_system):
    """Тест анализа действия"""
    # Подготовка тестовых данных
    test_action = {
        'type': 'test_action',
        'parameters': {'param1': 'value1'},
        'result': {'success': True}
    }
    
    # Вызов тестируемого метода
    result = learning_system.analyze_action(test_action)
    
    # Проверка результатов
    assert isinstance(result, dict)
    assert 'timestamp' in result
    assert 'action' in result
    assert 'context' in result
    assert 'success_metrics' in result
    assert 'patterns' in result
    assert result['action'] == test_action
    assert len(learning_system.learning_history) == 1

def test_update_patterns(learning_system):
    """Тест обновления паттернов"""
    # Подготовка тестовых данных
    test_analysis = {
        'patterns': {
            'pattern1': {'data': 'value1'},
            'pattern2': {'data': 'value2'}
        }
    }
    
    # Вызов тестируемого метода
    learning_system.update_patterns(test_analysis)
    
    # Проверка результатов
    assert 'pattern1' in learning_system.patterns
    assert 'pattern2' in learning_system.patterns
    learning_system.memory.store_patterns.assert_called_once()

def test_generate_recommendations(learning_system):
    """Тест генерации рекомендаций"""
    # Подготовка тестовых данных
    test_context = {'context_key': 'context_value'}
    
    # Вызов тестируемого метода
    recommendations = learning_system.generate_recommendations(test_context)
    
    # Проверка результатов
    assert isinstance(recommendations, list)

def test_evaluate_action_success(learning_system):
    """Тест оценки успешности действия"""
    # Подготовка тестовых данных
    test_action = {
        'type': 'test_action',
        'result': {'success': True}
    }
    
    # Вызов тестируемого метода
    metrics = learning_system._evaluate_action_success(test_action)
    
    # Проверка результатов
    assert isinstance(metrics, dict)

def test_extract_patterns(learning_system):
    """Тест извлечения паттернов"""
    # Подготовка тестовых данных
    test_action = {
        'type': 'test_action',
        'parameters': {'param1': 'value1'}
    }
    test_context = {'context_key': 'context_value'}
    
    # Вызов тестируемого метода
    patterns = learning_system._extract_patterns(test_action, test_context)
    
    # Проверка результатов
    assert isinstance(patterns, dict)

def test_update_existing_pattern(learning_system):
    """Тест обновления существующего паттерна"""
    # Подготовка тестовых данных
    pattern_key = 'test_pattern'
    new_data = {'data': 'new_value'}
    
    # Добавляем существующий паттерн
    learning_system.patterns[pattern_key] = {'data': 'old_value'}
    
    # Вызов тестируемого метода
    learning_system._update_existing_pattern(pattern_key, new_data)
    
    # Проверка результатов
    assert learning_system.patterns[pattern_key] == new_data

def test_get_relevant_patterns(learning_system):
    """Тест получения релевантных паттернов"""
    # Подготовка тестовых данных
    test_context = {'context_key': 'context_value'}
    
    # Вызов тестируемого метода
    patterns = learning_system._get_relevant_patterns(test_context)
    
    # Проверка результатов
    assert isinstance(patterns, list)

def test_create_recommendation(learning_system):
    """Тест создания рекомендации"""
    # Подготовка тестовых данных
    test_pattern = {'pattern_key': 'pattern_value'}
    test_context = {'context_key': 'context_value'}
    
    # Вызов тестируемого метода
    recommendation = learning_system._create_recommendation(test_pattern, test_context)
    
    # Проверка результатов
    assert recommendation is None or isinstance(recommendation, dict)

def test_error_handling(learning_system):
    """Тест обработки ошибок"""
    # Подготовка тестовых данных
    invalid_action = None
    
    # Проверка обработки ошибки при анализе действия
    with pytest.raises(Exception):
        learning_system.analyze_action(invalid_action)
    
    # Проверка обработки ошибки при обновлении паттернов
    with pytest.raises(Exception):
        learning_system.update_patterns(None)
    
    # Проверка обработки ошибки при генерации рекомендаций
    with pytest.raises(Exception):
        learning_system.generate_recommendations(None) 