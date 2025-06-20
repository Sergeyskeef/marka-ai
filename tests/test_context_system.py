"""
Тесты для системы контекстного управления.
"""

import pytest
from datetime import datetime, timedelta
from ..core.context.context_manager import ContextManager
from ..core.context.action_tracker import ActionTracker
from ..core.context.action_analyzer import ActionAnalyzer
from ..memory.memory_manager import MemoryManager

@pytest.fixture
def memory_manager():
    """Фикстура для создания менеджера памяти."""
    return MemoryManager()

@pytest.fixture
def context_manager(memory_manager):
    """Фикстура для создания менеджера контекста."""
    return ContextManager(memory_manager)

@pytest.fixture
def action_tracker(memory_manager):
    """Фикстура для создания трекера действий."""
    return ActionTracker(memory_manager)

@pytest.fixture
def action_analyzer(memory_manager):
    """Фикстура для создания анализатора действий."""
    return ActionAnalyzer(memory_manager)

def test_context_manager_initialization(context_manager):
    """Тест инициализации менеджера контекста."""
    context = context_manager.get_context()
    assert 'session_id' in context
    assert 'timestamp' in context
    assert 'active_tasks' in context
    assert 'recent_actions' in context
    assert 'relevant_memories' in context
    assert 'user_state' in context
    assert 'system_state' in context

def test_context_update(context_manager):
    """Тест обновления контекста."""
    updates = {
        'session_id': 'test_session',
        'active_tasks': ['task1', 'task2']
    }
    context_manager.update_context(updates)
    context = context_manager.get_context()
    assert context['session_id'] == 'test_session'
    assert context['active_tasks'] == ['task1', 'task2']
    assert 'timestamp' in context

def test_context_history(context_manager):
    """Тест истории контекста."""
    updates1 = {'session_id': 'session1'}
    updates2 = {'session_id': 'session2'}
    context_manager.update_context(updates1)
    context_manager.update_context(updates2)
    history = context_manager.get_context_history()
    assert len(history) == 2
    assert history[0]['session_id'] == 'session1'
    assert history[1]['session_id'] == 'session2'

def test_action_tracker_tracking(action_tracker):
    """Тест отслеживания действий."""
    action_id = action_tracker.track_action(
        'test_action',
        {'param1': 'value1'},
        'test_session'
    )
    assert action_id is not None
    actions = action_tracker.get_actions()
    assert len(actions) == 1
    assert actions[0]['type'] == 'test_action'
    assert actions[0]['details'] == {'param1': 'value1'}

def test_action_tracker_filtering(action_tracker):
    """Тест фильтрации действий."""
    action_tracker.track_action('type1', {}, 'session1')
    action_tracker.track_action('type2', {}, 'session1')
    action_tracker.track_action('type1', {}, 'session1')
    
    type1_actions = action_tracker.get_actions(action_type='type1')
    assert len(type1_actions) == 2
    assert all(a['type'] == 'type1' for a in type1_actions)

def test_action_analyzer_analysis(action_analyzer, action_tracker):
    """Тест анализа действий."""
    # Создаем последовательность действий
    now = datetime.utcnow()
    actions = [
        {
            'type': 'test_action',
            'details': {'step': 1},
            'timestamp': (now + timedelta(minutes=i)).isoformat(),
            'session_id': 'test_session'
        }
        for i in range(3)
    ]
    
    for action in actions:
        action_tracker.track_action(
            action['type'],
            action['details'],
            action['session_id']
        )
        
    analysis = action_analyzer.analyze_actions(actions)
    assert 'action_types' in analysis
    assert 'sequences' in analysis
    assert 'time_patterns' in analysis
    assert analysis['total_actions'] == 3

def test_action_analyzer_recommendations(action_analyzer):
    """Тест генерации рекомендаций."""
    analysis = {
        'action_types': {'test_action': 15},  # Частое действие
        'sequences': [{'length': 5}],  # Длинная последовательность
        'time_patterns': {'avg_interval': 30}  # Малый интервал
    }
    
    recommendations = action_analyzer.generate_recommendations(analysis)
    assert len(recommendations) > 0
    assert any('оптимизации' in r for r in recommendations)
    assert any('длинная последовательность' in r for r in recommendations)
    assert any('пакетной обработки' in r for r in recommendations) 