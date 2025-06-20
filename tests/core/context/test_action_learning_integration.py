"""
Тесты для интеграционного слоя между системой действий и системой обучения.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from langchain_api.core.context.action_learning_integration import ActionLearningIntegration
from langchain_api.core.context.action_types import ActionSystem, Action, ActionStatus, ActionPriority
from langchain_api.core.learning_system import LearningSystem
from langchain_api.core.memory.memory_manager import MemoryManager
from langchain_api.core.memory.enhanced_memory import EnhancedMemory

@pytest.fixture
def mock_action_system():
    system = Mock(spec=ActionSystem)
    system.action_tracker = Mock()
    return system

@pytest.fixture
def mock_learning_system():
    return Mock(spec=LearningSystem)

@pytest.fixture
def mock_memory_manager():
    manager = Mock(spec=MemoryManager)
    manager.store_insight = AsyncMock()
    return manager

@pytest.fixture
def mock_enhanced_memory():
    memory = Mock(spec=EnhancedMemory)
    memory.find_similar_actions = Mock()
    memory.store_action_result = AsyncMock()
    return memory

@pytest.fixture
def integration(mock_action_system, mock_learning_system, mock_memory_manager, mock_enhanced_memory):
    return ActionLearningIntegration(
        action_system=mock_action_system,
        learning_system=mock_learning_system,
        memory_manager=mock_memory_manager,
        enhanced_memory=mock_enhanced_memory
    )

@pytest.mark.asyncio
async def test_process_action_result(integration, mock_action_system, mock_learning_system):
    # Подготовка
    action_id = "test_action_id"
    result = {"status": "success"}
    mock_action = Mock(spec=Action)
    mock_action.id = action_id
    mock_action.type = "test_type"
    mock_action.status = ActionStatus.COMPLETED
    mock_action_system.action_tracker.get_action_by_id.return_value = mock_action
    
    mock_learning_system.analyze_action.return_value = {
        "patterns": {"test_pattern": "value"}
    }
    
    # Выполнение
    await integration.process_action_result(action_id, result)
    
    # Проверки
    mock_action_system.action_tracker.get_action_by_id.assert_called_once_with(action_id)
    mock_learning_system.analyze_action.assert_called_once()
    mock_learning_system.update_patterns.assert_called_once()
    integration.enhanced_memory.store_action_result.assert_called_once()
    integration.memory_manager.store_insight.assert_called_once()

@pytest.mark.asyncio
async def test_process_action_result_not_found(integration, mock_action_system):
    # Подготовка
    action_id = "non_existent_action"
    result = {"status": "success"}
    mock_action_system.action_tracker.get_action_by_id.return_value = None
    
    # Выполнение
    await integration.process_action_result(action_id, result)
    
    # Проверки
    mock_action_system.action_tracker.get_action_by_id.assert_called_once_with(action_id)
    integration.enhanced_memory.store_action_result.assert_not_called()
    integration.memory_manager.store_insight.assert_not_called()

def test_get_action_recommendations(integration, mock_learning_system, mock_enhanced_memory):
    # Подготовка
    context = {"test": "context"}
    mock_learning_system.generate_recommendations.return_value = [
        {"type": "test_recommendation"}
    ]
    mock_enhanced_memory.find_similar_actions.return_value = [
        {"action_id": "similar_action"}
    ]
    
    # Выполнение
    recommendations = integration.get_action_recommendations(context)
    
    # Проверки
    assert len(recommendations) == 1
    assert "similar_actions" in recommendations[0]
    mock_learning_system.generate_recommendations.assert_called_once_with(context)
    mock_enhanced_memory.find_similar_actions.assert_called_once()

def test_get_action_recommendations_empty(integration, mock_learning_system):
    # Подготовка
    context = {"test": "context"}
    mock_learning_system.generate_recommendations.return_value = []
    
    # Выполнение
    recommendations = integration.get_action_recommendations(context)
    
    # Проверки
    assert len(recommendations) == 0
    mock_learning_system.generate_recommendations.assert_called_once_with(context) 