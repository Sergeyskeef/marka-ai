"""
Тесты для интеграции системы рассуждений с памятью.
"""

from datetime import datetime

import pytest

from langchain_api.core.memory.enhanced_memory import EnhancedMemory
from langchain_api.core.reflection.memory_integration import MemoryIntegration
from langchain_api.core.reflection.reasoning_chains import (
    ReasoningChain,
    ReasoningStep,
    ReasoningSystem,
)
from langchain_api.core.reflection.self_learning import SelfLearningSystem


@pytest.fixture
def memory():
    """Фикстура для создания экземпляра памяти."""
    return EnhancedMemory()

@pytest.fixture
def reasoning_system():
    """Фикстура для создания экземпляра системы рассуждений."""
    return ReasoningSystem()

@pytest.fixture
def learning_system(reasoning_system):
    """Фикстура для создания экземпляра системы обучения."""
    return SelfLearningSystem(reasoning_system)

@pytest.fixture
def memory_integration(memory, learning_system):
    """Фикстура для создания экземпляра интеграции."""
    return MemoryIntegration(memory, learning_system)

@pytest.fixture
def sample_chain():
    """Фикстура для создания тестовой цепочки рассуждений."""
    chain = ReasoningChain("test_chain")

    # Добавляем шаги
    step1 = ReasoningStep(
        id="step1",
        content="Первый шаг рассуждения",
        context={"type": "analysis", "domain": "test"},
        confidence=0.8,
        timestamp=datetime.utcnow()
    )

    step2 = ReasoningStep(
        id="step2",
        content="Второй шаг рассуждения",
        context={"type": "analysis", "domain": "test"},
        confidence=0.9,
        parent_id="step1",
        timestamp=datetime.utcnow()
    )

    chain.add_step(step1)
    chain.add_step(step2)

    return chain

def test_memory_integration_creation(memory_integration):
    """Тест создания интеграции."""
    assert memory_integration is not None
    assert memory_integration.memory is not None
    assert memory_integration.learning_system is not None

def test_save_reasoning_chain(memory_integration, sample_chain):
    """Тест сохранения цепочки рассуждений"""
    # Сохраняем цепочку
    chain_id = memory_integration.save_reasoning_chain(sample_chain)

    # Проверяем, что цепочка сохранена
    saved_chain = memory_integration.memory.get(chain_id)
    assert saved_chain is not None
    assert saved_chain['type'] == 'reasoning_chain'
    assert saved_chain['id'] == chain_id

    # Проверяем, что паттерн обучения создан
    patterns = memory_integration.learning_system.get_relevant_patterns(sample_chain.steps[0].context)
    assert len(patterns) > 0

def test_get_relevant_memories(memory_integration, sample_chain):
    """Тест получения релевантных воспоминаний"""
    # Сохраняем цепочку рассуждений
    chain_id = memory_integration.save_reasoning_chain(sample_chain)

    # Получаем релевантные воспоминания
    memories = memory_integration.get_relevant_memories(sample_chain.steps[0].context)

    # Проверяем, что найдены релевантные воспоминания
    assert len(memories) > 0
    assert any(m['type'] == 'reasoning_chain' for m in memories)

    # Проверяем, что найдена наша цепочка
    assert any(m['id'] == chain_id for m in memories)

    # Проверяем, что у всех воспоминаний есть оценка релевантности
    assert all('relevance' in m for m in memories)

def test_analyze_historical_experience(memory_integration, sample_chain):
    """Тест анализа исторического опыта."""
    # Сохраняем цепочку
    memory_integration.save_reasoning_chain(sample_chain)

    # Анализируем опыт
    context = {"type": "analysis", "domain": "test"}
    analysis = memory_integration.analyze_historical_experience(context)

    assert 'successful_patterns' in analysis
    assert 'reasoning_chains' in analysis
    assert 'total_experience' in analysis
    assert 'success_rate' in analysis
    assert 0 <= analysis['success_rate'] <= 1

def test_calculate_relevance(memory_integration):
    """Тест расчета релевантности."""
    memory = {
        'id': 'test_memory',
        'type': 'analysis',
        'content': 'Test content'
    }

    context = {
        'type': 'analysis',
        'key': 'value'
    }

    relevance = memory_integration._calculate_relevance(memory, context)
    assert 0 <= relevance <= 1

def test_calculate_success_rate(memory_integration):
    """Тест расчета показателя успешности."""
    memories = [
        {
            'type': 'pattern',
            'data': type('obj', (), {'success_rate': 0.8})()
        },
        {
            'type': 'memory',
            'data': {
                'type': 'reasoning_chain',
                'evaluation': 0.9
            }
        }
    ]

    success_rate = memory_integration._calculate_success_rate(memories)
    assert 0 <= success_rate <= 1
    assert success_rate == pytest.approx(0.85)  # (0.8 + 0.9) / 2
