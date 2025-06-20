import pytest
from datetime import datetime
from langchain_api.core.reflection.self_learning import (
    LearningPattern,
    SelfLearningSystem
)
from langchain_api.core.reflection.reasoning_chains import (
    ReasoningSystem,
    ReasoningStep
)

def test_learning_pattern_creation():
    """Тест создания паттерна обучения"""
    pattern = LearningPattern(
        id="pattern1",
        pattern_type="code_pattern",
        context={"code": "def test(): pass"},
        confidence=0.8,
        created_at=datetime.now(),
        last_used=datetime.now()
    )
    
    assert pattern.id == "pattern1"
    assert pattern.pattern_type == "code_pattern"
    assert pattern.context == {"code": "def test(): pass"}
    assert pattern.confidence == 0.8
    assert pattern.usage_count == 0
    assert pattern.success_rate == 0.0

def test_learning_pattern_serialization():
    """Тест сериализации паттерна обучения"""
    created_at = datetime.now()
    last_used = datetime.now()
    pattern = LearningPattern(
        id="pattern1",
        pattern_type="code_pattern",
        context={"code": "def test(): pass"},
        confidence=0.8,
        created_at=created_at,
        last_used=last_used,
        usage_count=5,
        success_rate=0.8
    )
    
    data = pattern.to_dict()
    assert data["id"] == "pattern1"
    assert data["pattern_type"] == "code_pattern"
    assert data["context"] == {"code": "def test(): pass"}
    assert data["confidence"] == 0.8
    assert data["usage_count"] == 5
    assert data["success_rate"] == 0.8
    
    restored_pattern = LearningPattern.from_dict(data)
    assert restored_pattern.id == pattern.id
    assert restored_pattern.pattern_type == pattern.pattern_type
    assert restored_pattern.context == pattern.context
    assert restored_pattern.confidence == pattern.confidence
    assert restored_pattern.usage_count == pattern.usage_count
    assert restored_pattern.success_rate == pattern.success_rate

def test_self_learning_system_creation():
    """Тест создания системы самообучения"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    assert len(learning_system.patterns) == 0
    assert len(learning_system.learning_history) == 0

def test_self_learning_system_pattern_analysis():
    """Тест анализа паттернов"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    # Создаем цепочку рассуждений
    chain = reasoning_system.create_chain("chain1")
    step = ReasoningStep(
        id="step1",
        content="Test step",
        context={"code": "def test(): pass"},
        timestamp=datetime.now(),
        confidence=0.8
    )
    reasoning_system.add_step("chain1", step)
    
    # Анализируем паттерны
    patterns = learning_system.analyze_patterns("chain1")
    assert len(patterns) == 1
    assert patterns[0].pattern_type == "code_pattern"
    assert patterns[0].context == {"code": "def test(): pass"}

def test_self_learning_system_pattern_update():
    """Тест обновления паттерна"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    # Создаем паттерн
    pattern = LearningPattern(
        id="pattern1",
        pattern_type="code_pattern",
        context={"code": "def test(): pass"},
        confidence=0.8,
        created_at=datetime.now(),
        last_used=datetime.now()
    )
    learning_system.patterns["pattern1"] = pattern
    
    # Обновляем паттерн
    learning_system.update_pattern("pattern1", True)
    assert pattern.usage_count == 1
    assert pattern.success_rate == 1.0
    
    learning_system.update_pattern("pattern1", False)
    assert pattern.usage_count == 2
    assert pattern.success_rate == 0.5

def test_self_learning_system_relevant_patterns():
    """Тест получения релевантных паттернов"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    # Создаем паттерны разных типов
    patterns = [
        LearningPattern(
            id=f"pattern{i}",
            pattern_type="code_pattern",
            context={"code": f"def test{i}(): pass"},
            confidence=0.8,
            created_at=datetime.now(),
            last_used=datetime.now()
        )
        for i in range(3)
    ]
    
    for pattern in patterns:
        learning_system.patterns[pattern.id] = pattern
    
    # Получаем релевантные паттерны
    context = {"code": "def new_test(): pass"}
    relevant_patterns = learning_system.get_relevant_patterns(context)
    assert len(relevant_patterns) == 3
    assert all(p.pattern_type == "code_pattern" for p in relevant_patterns)

def test_self_learning_system_learning_events():
    """Тест записи событий обучения"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    # Записываем событие
    learning_system.record_learning_event(
        "test_event",
        {"code": "def test(): pass"},
        True,
        ["pattern1", "pattern2"]
    )
    
    assert len(learning_system.learning_history) == 1
    event = learning_system.learning_history[0]
    assert event["event_type"] == "test_event"
    assert event["success"] is True
    assert event["patterns_used"] == ["pattern1", "pattern2"]

def test_self_learning_system_stats():
    """Тест получения статистики"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    # Создаем паттерны с разной статистикой
    patterns = [
        LearningPattern(
            id=f"pattern{i}",
            pattern_type="code_pattern",
            context={"code": f"def test{i}(): pass"},
            confidence=0.8,
            created_at=datetime.now(),
            last_used=datetime.now(),
            usage_count=i + 1,
            success_rate=0.8
        )
        for i in range(3)
    ]
    
    for pattern in patterns:
        learning_system.patterns[pattern.id] = pattern
    
    # Записываем события
    for _ in range(3):
        learning_system.record_learning_event(
            "test_event",
            {"code": "def test(): pass"},
            True,
            ["pattern1"]
        )
    
    # Получаем статистику
    stats = learning_system.get_learning_stats()
    assert stats["total_patterns"] == 3
    assert stats["total_events"] == 3
    assert stats["average_success_rate"] == pytest.approx(0.8)
    assert len(stats["most_used_patterns"]) == 3

def test_self_learning_system_serialization(tmp_path):
    """Тест сериализации системы обучения"""
    reasoning_system = ReasoningSystem()
    learning_system = SelfLearningSystem(reasoning_system)
    
    # Создаем паттерн
    pattern = LearningPattern(
        id="pattern1",
        pattern_type="code_pattern",
        context={"code": "def test(): pass"},
        confidence=0.8,
        created_at=datetime.now(),
        last_used=datetime.now()
    )
    learning_system.patterns["pattern1"] = pattern
    
    # Записываем событие
    learning_system.record_learning_event(
        "test_event",
        {"code": "def test(): pass"},
        True,
        ["pattern1"]
    )
    
    # Сохраняем состояние
    filepath = tmp_path / "learning_system.json"
    learning_system.save_state(str(filepath))
    
    # Загружаем состояние
    loaded_system = SelfLearningSystem.load_state(str(filepath), reasoning_system)
    assert len(loaded_system.patterns) == 1
    assert len(loaded_system.learning_history) == 1
    
    loaded_pattern = loaded_system.patterns["pattern1"]
    assert loaded_pattern.id == pattern.id
    assert loaded_pattern.pattern_type == pattern.pattern_type
    assert loaded_pattern.context == pattern.context 