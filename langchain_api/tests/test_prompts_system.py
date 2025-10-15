"""
Тесты для системы управления промптами
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import numpy as np

from app.prompts import (
    PromptManager, DynamicPromptRouter, PromptEvolution,
    ContextArchitect, PromptSystemFactory
)
from app.prompts.base import (
    PromptTemplate, PromptComponent, PromptLayer,
    PromptMetadata, PromptEvolutionRecord, PromptSuccessionPackage
)
from app.prompts.templates.mark_base import (
    create_mark_base_prompt, create_mark_code_expert_prompt,
    create_mark_learning_prompt
)
from app.agents.mark_agent import MarkAgent


@pytest.fixture
async def temp_storage():
    """Временная директория для хранения промптов"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
async def prompt_manager(temp_storage):
    """Фикстура для менеджера промптов"""
    manager = PromptManager(storage_path=temp_storage)
    await manager.startup()
    yield manager
    await manager.shutdown()


class TestPromptManager:
    """Тесты для менеджера промптов"""
    
    async def test_create_and_save_prompt(self, prompt_manager):
        """Тест создания и сохранения промпта"""
        prompt = create_mark_base_prompt()
        prompt_id = await prompt_manager.save_prompt(prompt)
        
        assert prompt_id == prompt.metadata.id
        
        # Проверяем что промпт сохранился
        loaded = await prompt_manager.get_prompt("mark_base")
        assert loaded is not None
        assert loaded.name == "mark_base"
        assert loaded.metadata.version == "1.0.0"
    
    async def test_get_prompt_versions(self, prompt_manager):
        """Тест версионирования промптов"""
        # Создаем несколько версий
        base = create_mark_base_prompt()
        await prompt_manager.save_prompt(base)
        
        # Создаем новую версию
        v2 = base.copy(deep=True)
        v2.metadata.version = "1.1.0"
        v2.metadata.updated_at = datetime.now()
        await prompt_manager.save_prompt(v2)
        
        # Проверяем что обе версии существуют
        v1_loaded = await prompt_manager.get_prompt("mark_base", "1.0.0")
        v2_loaded = await prompt_manager.get_prompt("mark_base", "1.1.0")
        
        assert v1_loaded.metadata.version == "1.0.0"
        assert v2_loaded.metadata.version == "1.1.0"
    
    async def test_promote_prompt(self, prompt_manager):
        """Тест продвижения промпта между окружениями"""
        # Создаем промпт в development
        prompt = create_mark_base_prompt()
        await prompt_manager.save_prompt(prompt)
        
        # Продвигаем в production
        promoted_id = await prompt_manager.promote_prompt(
            "mark_base",
            from_env="development",
            to_env="production"
        )
        
        # Проверяем что промпт есть в production
        prod_prompt = await prompt_manager.get_prompt(
            "mark_base",
            environment="production"
        )
        assert prod_prompt is not None
        assert prod_prompt.metadata.environment == "production"
    
    async def test_update_metrics(self, prompt_manager):
        """Тест обновления метрик"""
        prompt = create_mark_base_prompt()
        await prompt_manager.save_prompt(prompt)
        
        # Обновляем метрики
        await prompt_manager.update_metrics(
            "mark_base",
            "1.0.0",
            "development",
            {"quality_score": 0.85, "tokens_used": 1500}
        )
        
        # Проверяем что метрики обновились
        updated = await prompt_manager.get_prompt("mark_base")
        assert updated.metadata.performance_metrics["quality_score"] == 0.85
        assert updated.metadata.performance_metrics["tokens_used"] == 1500


class TestDynamicPromptRouter:
    """Тесты для динамического роутера"""
    
    async def test_select_prompt(self, prompt_manager):
        """Тест выбора промпта"""
        # Создаем несколько промптов
        base = create_mark_base_prompt()
        code = create_mark_code_expert_prompt()
        learning = create_mark_learning_prompt()
        
        await prompt_manager.save_prompt(base)
        await prompt_manager.save_prompt(code)
        await prompt_manager.save_prompt(learning)
        
        # Создаем роутер
        router = DynamicPromptRouter(prompt_manager)
        
        # Тестируем выбор для кода
        context = {
            "query": "Напиши функцию сортировки",
            "domain": "technical",
            "complexity": 0.7,
            "requires_tools": True
        }
        
        prompt, confidence = await router.select_prompt(context)
        assert prompt is not None
        assert confidence > 0
    
    async def test_update_reward(self, prompt_manager):
        """Тест обновления награды"""
        prompt = create_mark_base_prompt()
        await prompt_manager.save_prompt(prompt)

        router = DynamicPromptRouter(prompt_manager)

        context = {"query": "Привет", "complexity": 0.2}

        # Делаем несколько выборов и обновлений
        for i in range(5):
            selected, _ = await router.select_prompt(context)
            reward = 0.8 if i % 2 == 0 else 0.4
            await router.update_reward(selected.name, context, reward)

        # Проверяем статистику
        stats = await router.get_routing_stats()
        assert stats["total_selections"] == 5
        assert "mark_base" in stats["prompts"]


@pytest.mark.asyncio
async def test_mark_agent_injects_fractal_context_once(prompt_manager, monkeypatch):
    """Проверяем, что фрактальный контекст добавляется в системное сообщение один раз."""

    client = MagicMock()
    agent = MarkAgent(client=client, prompt_manager=prompt_manager, use_dynamic_prompts=True)

    # Дожидаемся завершения фоновой задачи и подготавливаем зависимости
    await asyncio.sleep(0)

    mock_prompt = MagicMock()
    mock_prompt.name = "mock_template"
    agent.prompt_router.select_prompt = AsyncMock(return_value=(mock_prompt, 0.9))
    agent.context_architect.architect_context = MagicMock(return_value=("Базовый системный контекст", {"score": 1.0}))

    zoom_items = [{"text": "Важный факт", "metadata": {"scale": "L1", "type": "Note"}}]
    monkeypatch.setattr(
        "app.agents.mark_agent.fractal_graph.retrieve_context",
        AsyncMock(return_value=zoom_items)
    )

    messages = await agent._prepare_messages_dynamic("Что нового?", context=None, user_id="user42")

    system_content = messages[0]["content"]
    assert system_content.count("Фрактальный контекст") == 1


class TestPromptEvolution:
    """Тесты для системы эволюции"""
    
    async def test_evolution_triggers(self, prompt_manager):
        """Тест триггеров эволюции"""
        prompt = create_mark_base_prompt()
        await prompt_manager.save_prompt(prompt)
        
        evolution = PromptEvolution(prompt_manager)
        
        # Проверяем триггеры
        stats = {
            "context_usage": 0.8,  # Превышает порог 75%
            "interactions": 10,
            "avg_quality": 7
        }
        
        triggered = await evolution._check_triggers(stats)
        assert len(triggered) > 0
        assert triggered[0].name == "context_usage"
    
    async def test_evolve_prompt(self, prompt_manager):
        """Тест эволюции промпта"""
        prompt = create_mark_base_prompt()
        await prompt_manager.save_prompt(prompt)
        
        evolution = PromptEvolution(prompt_manager)
        
        # Запускаем эволюцию
        new_id = await evolution.evolve_prompt(
            "mark_base",
            "development",
            "Тестовая эволюция"
        )
        
        # Проверяем что создалась новая версия
        history = await prompt_manager.get_prompt_history("mark_base", "development")
        assert len(history) == 2  # Оригинал + эволюция


class TestContextArchitect:
    """Тесты для архитектора контекста"""
    
    def test_layer_positioning(self):
        """Тест расположения слоев"""
        architect = ContextArchitect()
        
        prompt = create_mark_base_prompt()
        
        # Проверяем что критические слои в правильных позициях
        position_map = architect.layer_position_map
        
        assert position_map[PromptLayer.INSTRUCTIONS].value <= 2  # В начале
        assert position_map[PromptLayer.USER_QUERY].value >= 6    # В конце
        assert position_map[PromptLayer.EXAMPLES].value == 4      # В середине
    
    def test_context_optimization(self):
        """Тест оптимизации контекста"""
        architect = ContextArchitect(max_context_tokens=1000)
        
        prompt = create_mark_base_prompt()
        context_data = {
            "user_query": "Тестовый запрос",
            "model_name": "gpt-4.1-mini",
            "user_id": "test123"
        }
        
        # Строим контекст
        optimized, metrics = architect.architect_context(
            prompt,
            context_data,
            optimization_mode="balanced"
        )
        
        assert optimized is not None
        assert metrics["total_tokens"] > 0
        assert metrics["quality_score"] > 0
    
    def test_attention_analysis(self):
        """Тест анализа распределения внимания"""
        architect = ContextArchitect()
        prompt = create_mark_base_prompt()
        
        analysis = architect.analyze_attention_distribution(prompt)
        
        assert "layers" in analysis
        assert "recommendations" in analysis
        
        # Проверяем что инструкции имеют высокий вес
        instructions_weight = analysis["layers"]["INSTRUCTIONS"]["attention_weight"]
        assert instructions_weight >= 0.9


class TestPromptSystemFactory:
    """Тесты для фабрики системы"""
    
    async def test_create_system(self, temp_storage):
        """Тест создания полной системы"""
        system = await PromptSystemFactory.create_system(
            storage_path=temp_storage
        )
        
        assert "manager" in system
        assert "router" in system
        assert "evolution" in system
        assert "architect" in system
        
        # Проверяем что компоненты работают
        prompt = create_mark_base_prompt()
        await system["manager"].save_prompt(prompt)
        
        loaded = await system["manager"].get_prompt("mark_base")
        assert loaded is not None
        
        # Останавливаем систему
        await PromptSystemFactory.shutdown_system(system)


class TestPromptTemplates:
    """Тесты для шаблонов промптов"""
    
    def test_base_prompt_structure(self):
        """Тест структуры базового промпта"""
        prompt = create_mark_base_prompt()
        
        assert prompt.name == "mark_base"
        assert len(prompt.components) > 0
        
        # Проверяем наличие ключевых слоев
        assert PromptLayer.INSTRUCTIONS in prompt.components
        assert PromptLayer.TOOL_DEFINITIONS in prompt.components
        assert PromptLayer.USER_QUERY in prompt.components
    
    def test_prompt_rendering(self):
        """Тест рендеринга промпта"""
        prompt = create_mark_base_prompt()
        
        context = {
            "model_name": "gpt-4.1-mini",
            "user_id": "user123",
            "user_query": "Тестовый вопрос"
        }
        
        rendered = prompt.render(context)
        
        assert "gpt-4.1-mini" in rendered
        assert "user123" in rendered
        assert "Тестовый вопрос" in rendered
    
    def test_token_estimation(self):
        """Тест оценки токенов"""
        prompt = create_mark_base_prompt()
        tokens = prompt.estimate_tokens()
        
        assert tokens > 0
        assert tokens < 10000  # Разумный предел


@pytest.mark.asyncio
async def test_full_workflow(temp_storage):
    """Интеграционный тест полного workflow"""
    # Создаем систему
    system = await PromptSystemFactory.create_system(
        storage_path=temp_storage
    )
    
    # Создаем и сохраняем промпты
    base = create_mark_base_prompt()
    code = create_mark_code_expert_prompt()
    
    await system["manager"].save_prompt(base)
    await system["manager"].save_prompt(code)
    
    # Выбираем промпт через роутер
    context = {
        "query": "Напиши код для сортировки",
        "domain": "technical",
        "complexity": 0.8
    }
    
    selected, confidence = await system["router"].select_prompt(context)
    assert selected is not None
    
    # Строим оптимизированный контекст
    context_data = {
        "user_query": context["query"],
        "model_name": "gpt-4"
    }
    
    optimized, metrics = system["architect"].architect_context(
        selected,
        context_data
    )
    
    assert optimized is not None
    assert len(optimized) > 0
    
    # Обновляем награду
    await system["router"].update_reward(selected.name, context, 0.9)
    
    # Получаем статистику
    stats = await system["router"].get_routing_stats()
    assert stats["total_selections"] == 1
    
    # Останавливаем систему
    await PromptSystemFactory.shutdown_system(system)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])