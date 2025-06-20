"""
Тесты для базового класса Action.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from ....core.context.action import Action
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
def action(memory_manager):
    """Фикстура для тестового действия."""
    return TestAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        details={'test': 'details'}
    )

def test_action_initialization(action):
    """Тест инициализации действия."""
    assert action.type == 'test'
    assert action.session_id == 'test_session'
    assert action.details == {'test': 'details'}
    assert action.status == 'created'
    assert action.result is None
    assert action.error is None
    assert isinstance(action.timestamp, str)
    assert isinstance(action.id, str)

def test_action_to_dict(action):
    """Тест преобразования действия в словарь."""
    action_dict = action.to_dict()
    assert action_dict['type'] == 'test'
    assert action_dict['session_id'] == 'test_session'
    assert action_dict['details'] == {'test': 'details'}
    assert action_dict['status'] == 'created'
    assert action_dict['result'] is None
    assert action_dict['error'] is None
    assert 'timestamp' in action_dict
    assert 'id' in action_dict

def test_action_update_status(action):
    """Тест обновления статуса действия."""
    action.update_status('running')
    assert action.status == 'running'
    
    action.update_status('completed', result={'test': 'result'})
    assert action.status == 'completed'
    assert action.result == {'test': 'result'}
    
    action.update_status('failed', error='test error')
    assert action.status == 'failed'
    assert action.error == 'test error'

def test_action_from_dict(memory_manager):
    """Тест создания действия из словаря."""
    data = {
        'id': 'test_id',
        'type': 'test',
        'details': {'test': 'details'},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'session_id': 'test_session',
        'status': 'created',
        'result': None,
        'error': None
    }
    
    action = TestAction.from_dict(data, memory_manager)
    assert action.id == 'test_id'
    assert action.type == 'test'
    assert action.details == {'test': 'details'}
    assert action.session_id == 'test_session'
    assert action.status == 'created'
    assert action.result is None
    assert action.error is None

@pytest.mark.asyncio
async def test_action_execute(action):
    """Тест выполнения действия."""
    result = await action.execute()
    assert result == {'test': 'result'}

def test_action_validate(action):
    """Тест валидации действия."""
    assert action.validate() is True 