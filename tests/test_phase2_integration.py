"""
Интеграционные тесты для Фазы 2 - продвинутая система памяти
"""

import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from app.memory.neo4j_direct import neo4j_client
from app.learning.reap_cycle import REAPLearningCycle
from app.agents.advanced_memory_tools import *
from app.agents.learning_tools import *
from app.agents.vector_search_tools import *
from core.memory.graphiti_adapter import graphiti_adapter


class TestPhase2Integration:
    """Тесты для проверки полной функциональности Фазы 2"""
    
    @pytest.fixture
    async def memory_adapter(self):
        """Создание адаптера памяти"""
        adapter = AdvancedMemoryAdapter(graphiti_adapter)
        yield adapter
        # Cleanup если нужно
    
    @pytest.fixture
    async def reap_cycle(self, memory_adapter):
        """Создание REAP цикла"""
        cycle = REAPLearningCycle(memory_adapter)
        yield cycle
    
    @pytest.mark.asyncio
    async def test_fact_lifecycle(self, memory_adapter):
        """Тест полного жизненного цикла факта"""
        # 1. Создание факта
        fact_result = await memory_adapter.save_fact(
            subject="Python",
            predicate="является",
            object="интерпретируемым языком",
            confidence=0.95,
            source="test"
        )
        
        assert fact_result["success"] is True
        fact_id = fact_result["id"]
        assert fact_id.startswith("fact-")
        
        # 2. Обновление уверенности
        update_result = await memory_adapter.update_fact_confidence(
            fact_id=fact_id,
            new_confidence=0.98,
            reason="Подтверждено дополнительными источниками"
        )
        
        assert update_result["success"] is True
        assert update_result["fact"]["confidence"] == 0.98
        
        # 3. Замена факта новым
        supersede_result = await memory_adapter.supersede_fact(
            old_fact_id=fact_id,
            new_subject="Python",
            new_predicate="является",
            new_object="высокоуровневым интерпретируемым языком",
            reason="Уточнение определения"
        )
        
        assert supersede_result["success"] is True
        new_fact_id = supersede_result["id"]
        assert new_fact_id != fact_id
        
        # 4. Проверка что старый факт помечен как недействительный
        old_fact = await neo4j_client.get_node_by_id(fact_id, "Fact")
        assert old_fact is not None
        assert old_fact.get("valid_to") is not None  # Должна быть установлена дата окончания
    
    @pytest.mark.asyncio
    async def test_episode_with_relationships(self, memory_adapter):
        """Тест эпизода со связями"""
        # 1. Создаем факт
        fact_result = await memory_adapter.save_fact(
            subject="User",
            predicate="prefers",
            object="dark mode",
            confidence=0.9
        )
        fact_id = fact_result["id"]
        
        # 2. Создаем эпизод
        episode_result = await memory_adapter.save_episode(
            situation="Пользователь попросил включить темную тему",
            actions_taken=["Проверка настроек", "Активация темной темы", "Подтверждение изменений"],
            outcome="success",
            reasoning="Использовал факт о предпочтении пользователя",
            lesson_learned="Персонализация улучшает UX",
            satisfaction=0.95
        )
        episode_id = episode_result["id"]
        
        # 3. Создаем связь между эпизодом и фактом
        link_result = await neo4j_client.link_episode_to_fact(
            episode_id=episode_id,
            fact_id=fact_id,
            relationship_type="USED_FACT"
        )
        
        assert link_result is True
        
        # 4. Проверяем что связь создана
        query = """
        MATCH (e:Episode {id: $episode_id})-[r:USED_FACT]->(f:Fact {id: $fact_id})
        RETURN count(r) as count
        """
        results = await neo4j_client.run_custom_query(
            query, 
            {"episode_id": episode_id, "fact_id": fact_id}
        )
        
        assert len(results) > 0
        assert results[0]["count"] == 1
    
    @pytest.mark.asyncio
    async def test_skill_evolution(self, memory_adapter):
        """Тест эволюции навыка"""
        # 1. Создаем начальный навык
        skill_result = await memory_adapter.save_skill(
            name="code_optimization",
            trigger_patterns=["оптимизировать код", "улучшить производительность"],
            procedure="Анализ -> Профилирование -> Оптимизация",
            system_prompt="Ты эксперт по оптимизации кода",
            performance_score=0.7
        )
        skill_id = skill_result["id"]
        
        # 2. Эволюционируем навык
        evolve_result = await memory_adapter.evolve_skill(
            skill_id=skill_id,
            improved_procedure="Анализ -> Профилирование -> Оптимизация -> Тестирование",
            improved_prompt="Ты эксперт по оптимизации кода. Всегда проверяй результаты тестами.",
            performance_improvement=0.15,
            reason="Добавлен этап тестирования для проверки оптимизаций"
        )
        
        assert evolve_result["success"] is True
        new_skill_id = evolve_result["new_skill_id"]
        assert new_skill_id != skill_id
        assert evolve_result["version"] == 2
        assert evolve_result["improvement"] == 0.15
        
        # 3. Проверяем связь EVOLVED_FROM
        query = """
        MATCH (new:Skill {id: $new_id})-[r:EVOLVED_FROM]->(old:Skill {id: $old_id})
        RETURN r.reason as reason, r.improvement as improvement
        """
        results = await neo4j_client.run_custom_query(
            query,
            {"new_id": new_skill_id, "old_id": skill_id}
        )
        
        assert len(results) > 0
        assert results[0]["improvement"] == 0.15
    
    @pytest.mark.asyncio
    async def test_reap_cycle_reflection(self, memory_adapter, reap_cycle):
        """Тест фазы рефлексии REAP цикла"""
        # Создаем тестовый эпизод
        episode_result = await memory_adapter.save_episode(
            situation="Написание unit теста",
            actions_taken=["Анализ требований", "Написание теста", "Запуск pytest"],
            outcome="success",
            reasoning="Следовал TDD подходу",
            lesson_learned="TDD помогает писать качественный код",
            satisfaction=0.9
        )
        
        # Запускаем рефлексию
        reflection = await reap_cycle.reflect_on_experience(episode_result["id"])
        
        assert reflection is not None
        assert hasattr(reflection, 'patterns')
        assert hasattr(reflection, 'effectiveness')
        assert hasattr(reflection, 'insights')
        assert reflection.effectiveness >= 0.8  # Высокая эффективность из-за satisfaction=0.9
    
    @pytest.mark.asyncio
    async def test_vector_search_functionality(self, memory_adapter):
        """Тест векторного поиска"""
        # Создаем несколько фактов
        facts = [
            ("Python", "используется для", "машинного обучения"),
            ("Python", "популярен в", "data science"),
            ("JavaScript", "используется для", "веб-разработки"),
            ("Java", "популярен в", "enterprise разработке")
        ]
        
        fact_ids = []
        for subject, predicate, obj in facts:
            result = await memory_adapter.save_fact(subject, predicate, obj)
            fact_ids.append(result["id"])
        
        # Обновляем embeddings
        update_result = await update_memory_embeddings("Fact", force=True)
        assert "success" in update_result
        
        # Выполняем векторный поиск
        search_result = await vector_search("Python машинное обучение", limit=3)
        
        # Парсим результат
        import json
        results = json.loads(search_result)
        
        assert results["found"] > 0
        assert len(results["results"]) <= 3
        
        # Первый результат должен быть про Python и ML
        first_result = results["results"][0]
        assert "Python" in first_result["text"] or "машинн" in first_result["text"]
    
    @pytest.mark.asyncio
    async def test_memory_archival(self):
        """Тест архивации старых воспоминаний"""
        # Этот тест требует создания старых данных, что сложно в тестовой среде
        # Просто проверяем что метод работает без ошибок
        archived_count = await neo4j_client.archive_old_memories(days_threshold=365)
        
        assert isinstance(archived_count, int)
        assert archived_count >= 0
    
    @pytest.mark.asyncio
    async def test_memory_stats(self, memory_adapter):
        """Тест получения статистики памяти"""
        # Создаем разные типы памяти
        await memory_adapter.save_fact("Test", "is", "fact")
        await memory_adapter.save_episode(
            "Test episode", 
            ["action1"], 
            "success", 
            "test",
            "lesson"
        )
        await memory_adapter.save_skill(
            "test_skill",
            ["trigger"],
            "procedure",
            "prompt"
        )
        
        # Получаем статистику
        stats = await memory_adapter.get_memory_stats()
        
        assert "facts" in stats
        assert "episodes" in stats
        assert "skills" in stats
        assert "total" in stats
        assert stats["total"] >= 3  # Минимум 3 элемента которые мы создали
    
    @pytest.mark.asyncio
    async def test_analyze_skill_usage(self, memory_adapter):
        """Тест анализа использования навыков"""
        # Создаем навык и эпизоды
        skill_result = await memory_adapter.save_skill(
            name="test_analysis_skill",
            trigger_patterns=["test"],
            procedure="test procedure",
            system_prompt="test prompt"
        )
        
        # Создаем эпизоды с использованием навыка
        for i in range(3):
            await memory_adapter.save_episode(
                situation=f"Test situation {i}",
                actions_taken=["test action"],
                outcome="success" if i < 2 else "failure",
                reasoning="test",
                lesson_learned="test lesson",
                satisfaction=0.8 if i < 2 else 0.3,
                metadata={"skill_used": skill_result["name"]}
            )
        
        # Анализируем использование
        analysis_result = await analyze_skill_usage(skill_result["name"])
        
        import json
        analysis = json.loads(analysis_result)
        
        assert analysis["skill_name"] == "test_analysis_skill"
        assert analysis["total_uses"] >= 3
        assert analysis["success_rate"] >= 0.6  # 2 успеха из 3
    
    @pytest.mark.asyncio 
    async def test_neo4j_direct_connection(self):
        """Тест прямого подключения к Neo4j"""
        # Проверяем подключение
        await neo4j_client.connect()
        
        # Выполняем простой запрос
        result = await neo4j_client.run_custom_query("RETURN 1 as test")
        
        assert len(result) == 1
        assert result[0]["test"] == 1
        
        # Закрываем подключение
        await neo4j_client.close()


if __name__ == "__main__":
    # Запуск всех тестов
    pytest.main([__file__, "-v"])