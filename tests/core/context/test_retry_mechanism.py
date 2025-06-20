"""
Тесты для механизма повторных попыток в системе действий.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from langchain_api.core.context.action_system import ActionSystem, ActionPriority, ActionStatus
from langchain_api.core.context.action import Action
from langchain_api.core.context.retry_config import RetryConfig, RetryStrategy
from langchain_api.core.memory.memory_manager import MemoryManager

class FailingAction(Action):
    """Тестовое действие, которое всегда завершается с ошибкой"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = 0
        
    async def execute(self) -> Dict[str, Any]:
        """Всегда вызывает ошибку"""
        self.attempts += 1
        raise Exception("Test error")
        
    def validate(self) -> bool:
        """Всегда валидно"""
        return True
        
    async def rollback(self) -> bool:
        """Всегда успешный откат"""
        return True

class EventuallySuccessfulAction(Action):
    """Тестовое действие, которое успешно выполняется после нескольких попыток"""
    
    def __init__(self, *args, success_after: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = 0
        self.success_after = success_after
        
    async def execute(self) -> Dict[str, Any]:
        """Успешно выполняется после указанного количества попыток"""
        self.attempts += 1
        if self.attempts < self.success_after:
            raise Exception(f"Attempt {self.attempts} failed")
        return {'result': 'success', 'attempts': self.attempts}
        
    def validate(self) -> bool:
        """Всегда валидно"""
        return True
        
    async def rollback(self) -> bool:
        """Всегда успешный откат"""
        return True

@pytest.fixture
def memory_manager():
    """Фикстура для менеджера памяти"""
    return MemoryManager()

@pytest.fixture
def action_system(memory_manager):
    """Фикстура для системы действий"""
    return ActionSystem(memory_manager)

@pytest.fixture
def retry_config():
    """Фикстура для конфигурации повторных попыток"""
    return RetryConfig(
        max_retries=3,
        initial_delay=0.1,
        max_delay=1.0,
        strategy=RetryStrategy.EXPONENTIAL,
        backoff_factor=2
    )

@pytest.mark.asyncio
async def test_fixed_retry_strategy(action_system, memory_manager):
    """Тест стратегии с фиксированным интервалом"""
    config = RetryConfig(
        max_retries=3,
        initial_delay=0.1,
        max_delay=1.0,
        strategy=RetryStrategy.FIXED
    )
    
    action = FailingAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        retry_config=config
    )
    
    await action_system.add_action(action)
    start_time = datetime.now()
    
    # Выполняем действие (оно должно завершиться с ошибкой)
    try:
        await action_system.execute_next_action()
        pytest.fail("Expected Exception")
    except Exception:
        pass
    
    # Проверяем, что действие находится в очереди повторных попыток
    assert action.id in action_system.retry_queue
    assert action.retry_count == 1
    
    # Проверяем, что задержка соответствует фиксированной стратегии
    retry_info = action_system.retry_queue[action.id]
    assert retry_info['next_retry'] - start_time >= timedelta(seconds=0.1)
    assert retry_info['next_retry'] - start_time <= timedelta(seconds=0.2)

@pytest.mark.asyncio
async def test_exponential_retry_strategy(action_system, memory_manager):
    """Тест экспоненциальной стратегии повторных попыток"""
    config = RetryConfig(
        max_retries=3,
        initial_delay=0.1,
        max_delay=1.0,
        strategy=RetryStrategy.EXPONENTIAL,
        backoff_factor=2
    )
    
    action = FailingAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        retry_config=config
    )
    
    await action_system.add_action(action)
    start_time = datetime.now()
    
    # Выполняем действие (оно должно завершиться с ошибкой)
    try:
        await action_system.execute_next_action()
        pytest.fail("Expected Exception")
    except Exception:
        pass
    
    # Проверяем, что задержка увеличивается экспоненциально
    retry_info = action_system.retry_queue[action.id]
    expected_delay = 0.1 * (2 ** (action.retry_count - 1))
    actual_delay = (retry_info['next_retry'] - start_time).total_seconds()
    assert abs(actual_delay - expected_delay) < 0.1

@pytest.mark.asyncio
async def test_linear_retry_strategy(action_system, memory_manager):
    """Тест линейной стратегии повторных попыток"""
    config = RetryConfig(
        max_retries=3,
        initial_delay=0.1,
        max_delay=1.0,
        strategy=RetryStrategy.LINEAR,
        backoff_factor=0.1
    )
    
    action = FailingAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        retry_config=config
    )
    
    await action_system.add_action(action)
    start_time = datetime.now()
    
    # Выполняем действие (оно должно завершиться с ошибкой)
    try:
        await action_system.execute_next_action()
        pytest.fail("Expected Exception")
    except Exception:
        pass
    
    # Проверяем, что задержка увеличивается линейно
    retry_info = action_system.retry_queue[action.id]
    expected_delay = 0.1 + (action.retry_count - 1) * 0.1
    actual_delay = (retry_info['next_retry'] - start_time).total_seconds()
    assert abs(actual_delay - expected_delay) < 0.1

@pytest.mark.asyncio
async def test_max_retries_exceeded():
    """Тест превышения максимального количества попыток"""
    retry_config = RetryConfig(
        max_retries=3,
        initial_delay=0.1,
        max_delay=1.0,
        strategy=RetryStrategy.FIXED
    )
    
    memory_manager = MemoryManager()
    action_system = ActionSystem(memory_manager)
    action_system.register_action_type('test', FailingAction)
    action = FailingAction(
        action_type='test',
        memory_manager=memory_manager,
        retry_config=retry_config,
        session_id='test_session'
    )
    action_id = await action_system.add_action(action)
    
    # Проверяем, что на каждой попытке выбрасывается исключение
    for attempt in range(retry_config.max_retries):
        try:
            await action_system.execute_next_action()
            pytest.fail("Expected Exception")
        except Exception as exc_info:
            assert str(exc_info) == "Test error"
            assert action.retry_count == attempt + 1
            assert action.status == ActionStatus.RUNNING.value
            assert action.id in action_system.retry_queue
            
        # Ждем немного перед следующей попыткой
        await asyncio.sleep(0.1)
    
    # Последняя попытка должна завершиться с ошибкой и пометить действие как FAILED
    try:
        await action_system.execute_next_action()
        pytest.fail("Expected Exception")
    except Exception as exc_info:
        assert str(exc_info) == "Test error"
        assert action.status == ActionStatus.FAILED.value
        assert action.retry_count == retry_config.max_retries
        assert action.id not in action_system.retry_queue

@pytest.mark.asyncio
async def test_successful_retry(action_system, memory_manager, retry_config):
    """Тест успешного повторного выполнения"""
    action = EventuallySuccessfulAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        retry_config=retry_config,
        success_after=2
    )
    
    await action_system.add_action(action)
    
    # Первая попытка должна завершиться с ошибкой
    try:
        await action_system.execute_next_action()
        pytest.fail("Expected Exception")
    except Exception:
        pass
    
    # Проверяем, что действие находится в очереди повторных попыток
    assert action.id in action_system.retry_queue
    assert action.retry_count == 1
    
    # Ждем, пока можно будет повторить попытку
    await asyncio.sleep(0.2)
    
    # Вторая попытка должна быть успешной
    result = await action_system.execute_next_action()
    assert result['result'] == 'success'
    assert result['attempts'] == 2
    assert action.status == ActionStatus.COMPLETED.value
    assert action.id not in action_system.retry_queue

def test_retry_config_serialization(retry_config):
    """Тест сериализации конфигурации повторных попыток"""
    config_dict = retry_config.to_dict()
    new_config = RetryConfig.from_dict(config_dict)
    
    assert new_config.max_retries == retry_config.max_retries
    assert new_config.initial_delay == retry_config.initial_delay
    assert new_config.max_delay == retry_config.max_delay
    assert new_config.strategy == retry_config.strategy
    assert new_config.backoff_factor == retry_config.backoff_factor

@pytest.mark.asyncio
async def test_queue_status_with_retries(action_system, memory_manager, retry_config):
    """Тест статуса очереди с учетом повторных попыток"""
    action = FailingAction(
        action_type='test',
        memory_manager=memory_manager,
        session_id='test_session',
        retry_config=retry_config
    )
    
    await action_system.add_action(action)
    
    # Выполняем действие (оно должно завершиться с ошибкой)
    try:
        await action_system.execute_next_action()
        pytest.fail("Expected Exception")
    except Exception:
        pass
    
    # Проверяем статус очереди
    status = action_system.get_queue_status()
    assert status['queue_length'] == 0
    assert len(status['retry_queue']) == 1
    assert status['retry_queue'][0]['id'] == action.id
    assert status['retry_queue'][0]['retry_count'] == 1
    assert 'next_retry' in status['retry_queue'][0] 