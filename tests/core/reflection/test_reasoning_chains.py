from datetime import datetime

import pytest

from core.reflection.reasoning_chains import (
    ReasoningChain,
    ReasoningStep,
    ReasoningSystem,
)


def test_reasoning_step_creation():
    """Тест создания шага рассуждения"""
    step = ReasoningStep(
        id="step1",
        content="Test step",
        context={"test": "context"},
        timestamp=datetime.now(),
        confidence=0.8
    )

    assert step.id == "step1"
    assert step.content == "Test step"
    assert step.context == {"test": "context"}
    assert step.confidence == 0.8
    assert step.parent_id is None
    assert step.children_ids == []

def test_reasoning_step_serialization():
    """Тест сериализации шага рассуждения"""
    timestamp = datetime.now()
    step = ReasoningStep(
        id="step1",
        content="Test step",
        context={"test": "context"},
        timestamp=timestamp,
        confidence=0.8
    )

    data = step.to_dict()
    assert data["id"] == "step1"
    assert data["content"] == "Test step"
    assert data["context"] == {"test": "context"}
    assert data["confidence"] == 0.8

    restored_step = ReasoningStep.from_dict(data)
    assert restored_step.id == step.id
    assert restored_step.content == step.content
    assert restored_step.context == step.context
    assert restored_step.confidence == step.confidence

def test_reasoning_chain_creation():
    """Тест создания цепочки рассуждений"""
    chain = ReasoningChain("chain1")
    assert chain.chain_id == "chain1"
    assert len(chain.steps) == 0
    assert chain.root_step_id is None

def test_reasoning_chain_add_step():
    """Тест добавления шага в цепочку"""
    chain = ReasoningChain("chain1")
    step = ReasoningStep(
        id="step1",
        content="Test step",
        context={"test": "context"},
        timestamp=datetime.now(),
        confidence=0.8
    )

    chain.add_step(step)
    assert len(chain.steps) == 1
    assert chain.root_step_id == "step1"
    assert chain.get_step("step1") == step

def test_reasoning_chain_hierarchy():
    """Тест иерархии шагов в цепочке"""
    chain = ReasoningChain("chain1")

    # Создаем корневой шаг
    root_step = ReasoningStep(
        id="root",
        content="Root step",
        context={},
        timestamp=datetime.now(),
        confidence=0.9
    )

    # Создаем дочерний шаг
    child_step = ReasoningStep(
        id="child",
        content="Child step",
        context={},
        timestamp=datetime.now(),
        confidence=0.8,
        parent_id="root"
    )

    chain.add_step(root_step)
    chain.add_step(child_step)

    assert len(chain.steps) == 2
    assert chain.root_step_id == "root"
    assert "child" in root_step.children_ids
    assert child_step.parent_id == "root"

def test_reasoning_chain_evaluation():
    """Тест оценки цепочки рассуждений"""
    chain = ReasoningChain("chain1")

    steps = [
        ReasoningStep(
            id=f"step{i}",
            content=f"Step {i}",
            context={},
            timestamp=datetime.now(),
            confidence=0.8
        )
        for i in range(3)
    ]

    for step in steps:
        chain.add_step(step)

    evaluation = chain.evaluate_logical_consistency()
    assert evaluation == pytest.approx(0.8)  # Используем pytest.approx() для сравнения

def test_reasoning_system_creation():
    """Тест создания системы рассуждений"""
    system = ReasoningSystem()
    assert len(system.chains) == 0
    assert system.current_chain_id is None

def test_reasoning_system_chain_management():
    """Тест управления цепочками в системе"""
    system = ReasoningSystem()

    # Создаем цепочку
    system.create_chain("chain1")
    assert len(system.chains) == 1
    assert system.current_chain_id == "chain1"

    # Добавляем шаг
    step = ReasoningStep(
        id="step1",
        content="Test step",
        context={},
        timestamp=datetime.now(),
        confidence=0.8
    )
    system.add_step("chain1", step)

    # Проверяем цепочку
    retrieved_chain = system.get_chain("chain1")
    assert retrieved_chain is not None
    assert len(retrieved_chain.steps) == 1
    assert retrieved_chain.get_step("step1") == step

def test_reasoning_system_context_analysis():
    """Тест анализа контекста"""
    system = ReasoningSystem()

    context = {
        "code": "def test(): pass",
        "text": "Some text",
        "other": "data"
    }

    analysis = system.analyze_context(context)
    assert analysis["context_size"] > 0
    assert analysis["has_code"] is True
    assert analysis["has_text"] is True

def test_reasoning_system_chain_evaluation():
    """Тест оценки цепочки в системе"""
    system = ReasoningSystem()
    system.create_chain("chain1")

    steps = [
        ReasoningStep(
            id=f"step{i}",
            content=f"Step {i}",
            context={},
            timestamp=datetime.now(),
            confidence=0.8
        )
        for i in range(3)
    ]

    for step in steps:
        system.add_step("chain1", step)

    evaluation = system.evaluate_chain("chain1")
    assert evaluation["logical_consistency"] == pytest.approx(0.8)
    assert evaluation["step_count"] == 3
    assert evaluation["depth"] == 1
    assert evaluation["average_confidence"] == pytest.approx(0.8)

def test_reasoning_system_serialization(tmp_path):
    """Тест сериализации системы"""
    system = ReasoningSystem()
    system.create_chain("chain1")

    step = ReasoningStep(
        id="step1",
        content="Test step",
        context={},
        timestamp=datetime.now(),
        confidence=0.8
    )
    system.add_step("chain1", step)

    # Сохраняем систему
    filepath = tmp_path / "reasoning_system.json"
    system.save_chains(str(filepath))

    # Загружаем систему
    loaded_system = ReasoningSystem.load_chains(str(filepath))
    assert len(loaded_system.chains) == 1
    assert loaded_system.current_chain_id == "chain1"

    loaded_chain = loaded_system.get_chain("chain1")
    assert loaded_chain is not None
    assert len(loaded_chain.steps) == 1
    assert loaded_chain.get_step("step1") is not None
