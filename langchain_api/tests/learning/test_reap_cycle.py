"""REAP Learning Cycle - unit/integration tests."""

import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def real_episode_id():
    """Создает реальный эпизод в Graphiti и возвращает его ID."""
    from app.learning.reap_cycle import reap_cycle

    episode = await reap_cycle.memory.save_episode(
        situation=f"REAP fixture episode {uuid.uuid4()}",
        actions_taken=["prepare", "execute", "review"],
        outcome="success",
        reasoning="Fixture preparation for reflection test",
        lesson_learned="Graphiti episode accessible by ID",
        satisfaction=0.8,
    )

    assert episode.get("success") is True
    episode_id = episode.get("id")
    assert isinstance(episode_id, str) and episode_id
    return episode_id


@pytest.mark.asyncio
async def test_reap_cycle_end_to_end():
    """Полный прогон REAP: Reflect -> Extract -> Apply -> Persist."""
    from app.learning.reap_cycle import reap_cycle

    # 1) Создаём эпизод-источник
    episode = await reap_cycle.memory.save_episode(
        situation="REAP unit test: simple success case",
        actions_taken=["analyze", "implement", "verify"],
        outcome="success",
        reasoning="Followed the plan and validated outcome",
        lesson_learned="Planning + verification improves reliability",
        satisfaction=0.9,
    )
    assert episode.get("success") is True
    episode_id = episode.get("id")
    assert isinstance(episode_id, str) and len(episode_id) > 0

    # 2) Reflect
    reflection = await reap_cycle.reflect_on_episode(episode_id)
    assert hasattr(reflection, "patterns")
    assert hasattr(reflection, "effectiveness")

    # 3) Extract
    knowledge = await reap_cycle.extract_knowledge(reflection)
    assert hasattr(knowledge, "new_facts")
    assert hasattr(knowledge, "lessons")

    # 4) Apply
    applied = await reap_cycle.apply_knowledge(knowledge)
    assert isinstance(applied, dict)
    assert "facts_saved" in applied

    # 5) Persist
    persisted = await reap_cycle.persist_learnings()
    assert isinstance(persisted, dict)


@pytest.mark.asyncio
async def test_run_learning_cycle_wrapper():
    """Проверяем единый вызов run_learning_cycle()."""
    from app.learning.reap_cycle import reap_cycle

    result = await reap_cycle.run_learning_cycle(auto_mode=False)
    assert isinstance(result, dict)
    assert result.get("status") in {"completed", "skip", "error"}


@pytest.mark.asyncio
async def test_reflect_on_real_episode_id(real_episode_id):
    """Проверяем, что рефлексия по реальному ID проходит успешно."""
    from app.learning.reap_cycle import reap_cycle

    reflection = await reap_cycle.reflect_on_episode(real_episode_id)

    assert reflection.effectiveness > 0
    assert reflection.recommendations
    assert reflection.recommendations != ["Эпизод не найден"]


