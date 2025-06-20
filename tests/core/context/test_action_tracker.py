"""
Тесты для ActionTracker.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any
from ....core.context.action import Action
from ....core.context.action_tracker import ActionTracker
from ....core.memory.memory_manager import MemoryManager

class TestAction(Action):
    """Тестовая реализация Action для тестирования."""
    
    async def execute(self) -> Dict[str, Any]:
        """Тестовая реализация execute."""
        return {'test': 'result'}
        
    def validate(self) -> bool:
        """Тестовая реализация validate."""
        return True

@pytest.fixture
def memory_manager():
    """Фикстура для MemoryManager."""
    return MemoryManager()

@pytest.fixture
def action_tracker(memory_manager):
    """Фикстура для ActionTracker."""
    return ActionTracker(memory_manager)

@pytest.fixture
def test_action(memory_manager):
    """Фикстура для тестового действия."""
    return TestAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        details={'test': 'details'}
    )

def test_track_action(action_tracker, test_action):
    """Тест отслеживания действия."""
    action_id = action_tracker.track_action(test_action)
    assert action_id == test_action.id
    assert len(action_tracker.actions) == 1
    assert action_tracker.actions[0] == test_action

def test_get_actions(action_tracker, test_action):
    """Тест получения списка действий."""
    action_tracker.track_action(test_action)
    actions = action_tracker.get_actions()
    assert len(actions) == 1
    assert actions[0] == test_action
    
    # Тест фильтрации по типу
    actions = action_tracker.get_actions(action_type='test')
    assert len(actions) == 1
    assert actions[0] == test_action
    
    actions = action_tracker.get_actions(action_type='other')
    assert len(actions) == 0

def test_get_action_sequence(action_tracker, test_action):
    """Тест получения последовательности действий."""
    action_tracker.track_action(test_action)
    
    start_time = datetime.utcnow() - timedelta(minutes=5)
    end_time = datetime.utcnow() + timedelta(minutes=5)
    
    actions = action_tracker.get_action_sequence(start_time, end_time)
    assert len(actions) == 1
    assert actions[0] == test_action
    
    # Тест за пределами временного диапазона
    future_start = datetime.utcnow() + timedelta(hours=1)
    future_end = datetime.utcnow() + timedelta(hours=2)
    
    actions = action_tracker.get_action_sequence(future_start, future_end)
    assert len(actions) == 0

def test_generate_report(action_tracker, test_action):
    """Тест генерации отчета."""
    action_tracker.track_action(test_action)
    
    report = action_tracker.generate_report()
    assert report['total_actions'] == 1
    assert report['action_types']['test'] == 1
    
    # Тест с временным диапазоном
    start_time = datetime.utcnow() - timedelta(minutes=5)
    end_time = datetime.utcnow() + timedelta(minutes=5)
    
    report = action_tracker.generate_report(start_time, end_time)
    assert report['total_actions'] == 1
    assert report['time_range']['start'] == start_time.isoformat()
    assert report['time_range']['end'] == end_time.isoformat()

def test_get_action_by_id(action_tracker, test_action):
    """Тест получения действия по ID."""
    action_tracker.track_action(test_action)
    
    found_action = action_tracker.get_action_by_id(test_action.id)
    assert found_action == test_action
    
    # Тест с несуществующим ID
    not_found = action_tracker.get_action_by_id('non_existent')
    assert not_found is None

def test_get_actions_by_status(action_tracker, test_action):
    """Тест получения действий по статусу."""
    action_tracker.track_action(test_action)
    
    actions = action_tracker.get_actions_by_status('created')
    assert len(actions) == 1
    assert actions[0] == test_action
    
    # Изменяем статус
    test_action.update_status('running')
    actions = action_tracker.get_actions_by_status('running')
    assert len(actions) == 1
    assert actions[0] == test_action

def test_get_actions_by_session(action_tracker, test_action):
    """Тест получения действий по ID сессии."""
    action_tracker.track_action(test_action)
    
    actions = action_tracker.get_actions_by_session('test_session')
    assert len(actions) == 1
    assert actions[0] == test_action
    
    # Тест с несуществующей сессией
    actions = action_tracker.get_actions_by_session('other_session')
    assert len(actions) == 0 