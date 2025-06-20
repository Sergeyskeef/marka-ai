"""
Тесты для системы действий.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
from langchain_api.core.context.action_system import ActionSystem
from langchain_api.core.context.action import Action
from langchain_api.core.context.action_types import ActionPriority, ActionStatus, ActionType
from langchain_api.core.context.retry_config import RetryConfig

class TestAction(Action):
    """Тестовое действие для проверки системы."""
    
    async def execute(self):
        """Тестовое выполнение."""
        return {"result": "test"}
        
    def validate(self):
        """Тестовая валидация."""
        return True
        
    async def rollback(self):
        """Тестовый откат."""
        return True
        
    def calculate_dynamic_priority(self) -> float:
        """Расчет динамического приоритета."""
        base_priority = self.priority.get_weight()
        wait_time_factor = min(self.wait_time / 3600, 1.0)  # Нормализуем время ожидания до 1 часа
        retry_factor = min(self.retry_count / 3, 1.0)  # Нормализуем количество попыток до 3
        type_factor = ActionType(self.type).get_importance()
        
        # Комбинируем факторы с новыми весами
        dynamic_priority = (
            base_priority * 1.0 +  # Уменьшаем вес базового приоритета
            wait_time_factor * 10.0 +  # Значительно увеличиваем вес времени ожидания
            retry_factor * 2.0 +  # Оставляем вес количества попыток
            type_factor * 1.0  # Оставляем вес типа действия как есть
        )
        
        return dynamic_priority

@pytest.fixture
def memory_manager():
    """Фикстура для менеджера памяти."""
    manager = Mock()
    manager.memory_registry = {
        'Experience': Mock()
    }
    return manager

@pytest.fixture
def action_system(memory_manager):
    """Фикстура для системы действий."""
    system = ActionSystem(memory_manager)
    system.register_action_type("test", TestAction)
    return system

@pytest.fixture
def test_action(memory_manager):
    """Фикстура для тестового действия"""
    return TestAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session'
    )

@pytest.mark.asyncio
async def test_add_action(action_system):
    """Тест добавления действия."""
    test_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    action_id = await action_system.add_action(test_action)
    assert action_id == test_action.id
    assert len(action_system.action_queue) == 1
    assert action_system.action_queue[0].id == test_action.id

@pytest.mark.asyncio
async def test_action_priority(action_system):
    """Тест приоритетов действий."""
    low_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.LOW
    )
    
    high_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.HIGH
    )
    
    await action_system.add_action(low_action)
    await action_system.add_action(high_action)
    
    assert len(action_system.action_queue) == 2
    assert action_system.action_queue[0].priority == ActionPriority.HIGH
    assert action_system.action_queue[1].priority == ActionPriority.LOW

@pytest.mark.asyncio
async def test_action_dependencies(action_system):
    """Тест зависимостей действий."""
    action1 = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    action2 = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    await action_system.add_action(action1)
    await action_system.add_action(action2, dependencies=[action1.id])
    
    assert len(action_system.action_queue) == 2
    assert action_system.action_queue[0].id == action1.id
    assert action_system.action_queue[1].id == action2.id
    assert action2.id in action_system.action_dependencies
    assert action1.id in action_system.action_dependencies[action2.id]

@pytest.mark.asyncio
async def test_execute_action(action_system):
    """Тест выполнения действия."""
    test_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    await action_system.add_action(test_action)
    result = await action_system.execute_next_action()
    
    assert result == {"result": "test"}
    assert test_action.status == ActionStatus.COMPLETED.value

@pytest.mark.asyncio
async def test_cancel_action(action_system):
    """Тест отмены действия."""
    test_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    await action_system.add_action(test_action)
    success = await action_system.cancel_action(test_action.id)
    
    assert success
    assert test_action.status == ActionStatus.CANCELLED.value

@pytest.mark.asyncio
async def test_rollback_action(action_system):
    """Тест отката действия."""
    test_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    await action_system.add_action(test_action)
    result = await action_system.execute_next_action()
    assert result == {"result": "test"}
    
    success = await action_system.rollback_action(test_action.id)
    assert success
    assert test_action.status == ActionStatus.ROLLED_BACK.value

@pytest.mark.asyncio
async def test_queue_status(action_system):
    """Тест статуса очереди."""
    test_action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    await action_system.add_action(test_action)
    status = action_system.get_queue_status()
    
    assert status['actions_count'] == 1
    assert len(status['actions']) == 1
    assert status['actions'][0]['id'] == test_action.id

@pytest.mark.asyncio
async def test_dynamic_priority_calculation(action_system):
    """Тест расчета динамического приоритета."""
    # Создаем действия с разными параметрами
    action1 = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.LOW
    )
    
    action2 = TestAction(
        action_type=ActionType.USER.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.HIGH
    )
    
    # Добавляем действия в очередь
    await action_system.add_action(action1)
    await action_system.add_action(action2)
    
    # Проверяем, что действие с более высоким базовым приоритетом имеет больший динамический приоритет
    assert action2.calculate_dynamic_priority() > action1.calculate_dynamic_priority()
    
    # Имитируем ожидание в очереди
    action1.created_at = datetime.utcnow() - timedelta(hours=2)
    action1.update_wait_time()
    
    # Проверяем, что время ожидания увеличило приоритет
    assert action1.calculate_dynamic_priority() > action2.calculate_dynamic_priority()

@pytest.mark.asyncio
async def test_retry_priority_increase(action_system):
    """Тест увеличения приоритета при повторных попытках."""
    action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL,
        retry_config=RetryConfig(max_retries=3)
    )
    
    initial_priority = action.calculate_dynamic_priority()
    
    # Имитируем несколько попыток выполнения
    for _ in range(3):
        action.increment_retry_count()
    
    # Проверяем, что приоритет увеличился
    assert action.calculate_dynamic_priority() > initial_priority

@pytest.mark.asyncio
async def test_queue_sorting_by_dynamic_priority(action_system):
    """Тест сортировки очереди по динамическому приоритету."""
    # Создаем действия
    actions = []
    for i in range(3):
        action = TestAction(
            action_type=ActionType.SYSTEM.value,
            memory_manager=action_system.memory_manager,
            session_id="test_session",
            priority=ActionPriority.NORMAL
        )
        actions.append(action)
    
    # Добавляем действия в очередь
    for action in actions:
        await action_system.add_action(action)
    
    # Имитируем разные условия для действий
    actions[0].created_at = datetime.utcnow() - timedelta(hours=2)  # Долгое ожидание
    actions[1].retry_count = 3  # Много попыток
    actions[2].priority = ActionPriority.HIGH  # Высокий базовый приоритет
    
    # Обновляем время ожидания
    for action in actions:
        action.update_wait_time()
    
    # Проверяем порядок в очереди
    queue_status = action_system.get_queue_status()
    queue_actions = queue_status['actions']
    
    # Проверяем, что действия отсортированы по убыванию динамического приоритета
    for i in range(len(queue_actions) - 1):
        assert queue_actions[i]['dynamic_priority'] >= queue_actions[i + 1]['dynamic_priority']

@pytest.mark.asyncio
async def test_priority_update_on_retry(action_system):
    """Тест обновления приоритета при повторной попытке."""
    action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL,
        retry_config=RetryConfig(max_retries=3)
    )
    
    # Добавляем действие в очередь
    await action_system.add_action(action)
    
    # Имитируем ошибку выполнения
    action.execute = AsyncMock(side_effect=Exception("Test error"))
    
    # Выполняем действие
    await action_system.execute_next_action()
    
    # Проверяем, что действие добавлено в очередь повторных попыток
    assert action.id in action_system.retry_queue
    
    # Имитируем время для следующей попытки
    action_system.retry_queue[action.id]['next_retry'] = datetime.utcnow()
    
    # Проверяем, что приоритет обновляется при возврате в основную очередь
    await action_system.execute_next_action()
    assert action.calculate_dynamic_priority() > 0

@pytest.mark.asyncio
async def test_priority_factors(action_system):
    """Тест влияния различных факторов на приоритет."""
    action = TestAction(
        action_type=ActionType.SYSTEM.value,
        memory_manager=action_system.memory_manager,
        session_id="test_session",
        priority=ActionPriority.NORMAL
    )
    
    # Проверяем базовый приоритет
    base_priority = action.calculate_dynamic_priority()
    
    # Проверяем влияние времени ожидания
    action.created_at = datetime.utcnow() - timedelta(hours=2)
    action.update_wait_time()
    wait_priority = action.calculate_dynamic_priority()
    assert wait_priority > base_priority
    
    # Проверяем влияние попыток
    action.retry_count = 3
    retry_priority = action.calculate_dynamic_priority()
    assert retry_priority > wait_priority
    
    # Проверяем влияние типа действия
    action.type = ActionType.USER.value
    type_priority = action.calculate_dynamic_priority()
    assert type_priority != retry_priority  # Приоритет должен измениться 