"""
Комплексный интеграционный тест всех фаз проекта
Проверяет совместную работу Phase 1 и Phase 2
"""

import asyncio
import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.chat_handler import enhanced_chat, simple_chat
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from app.learning.reap_cycle import REAPLearningCycle
from core.memory.graphiti_adapter import graphiti_adapter


class TestAllPhasesIntegration:
    """Тесты полной интеграции всех фаз"""
    
    @pytest.mark.asyncio
    async def test_full_conversation_flow(self):
        """Тест полного цикла разговора с использованием всех возможностей"""
        
        # 1. Простой вопрос (Phase 1)
        result1 = await enhanced_chat(
            question="Привет! Меня зовут Александр, я люблю Python",
            user_id="test_user_alex",
            mode="chat"
        )
        
        assert result1["content"] is not None
        assert not result1.get("error", False)
        assert result1["metadata"]["tools_available"] > 0
        
        # 2. Сохранение факта о пользователе (Phase 2)
        result2 = await enhanced_chat(
            question="Запомни, что я предпочитаю писать тесты перед кодом (TDD)",
            user_id="test_user_alex",
            mode="chat"
        )
        
        assert "запомн" in result2["content"].lower() or "сохран" in result2["content"].lower()
        
        # 3. Использование сохраненного контекста (Phase 1 + 2)
        result3 = await enhanced_chat(
            question="Какой подход к разработке я предпочитаю?",
            user_id="test_user_alex",
            mode="chat"
        )
        
        assert "TDD" in result3["content"] or "тест" in result3["content"].lower()
        assert result3["metadata"]["context_used"] is True
        
        # 4. Анализ производительности (Phase 2)
        result4 = await enhanced_chat(
            question="Проанализируй мою эффективность обучения",
            user_id="test_user_alex",
            mode="analysis"
        )
        
        assert result4["content"] is not None
        # Должен использовать инструменты анализа
        assert len(result4.get("tool_calls", [])) > 0
    
    @pytest.mark.asyncio
    async def test_memory_evolution_flow(self):
        """Тест эволюции памяти через взаимодействие"""
        
        adapter = AdvancedMemoryAdapter(graphiti_adapter)
        
        # 1. Создаем начальный факт
        fact1 = await adapter.save_fact(
            subject="Python",
            predicate="версия",
            object="3.9",
            confidence=0.9
        )
        
        # 2. Обновляем факт через чат
        result = await enhanced_chat(
            question="Обнови информацию: Python теперь версии 3.12",
            mode="task"
        )
        
        # 3. Проверяем что факт обновился
        # Должен быть вызван инструмент обновления
        assert "обнов" in result["content"].lower() or "update" in result["content"].lower()
    
    @pytest.mark.asyncio
    async def test_learning_cycle_integration(self):
        """Тест интеграции цикла обучения с чатом"""
        
        # 1. Создаем несколько эпизодов через чат
        for i in range(3):
            await enhanced_chat(
                question=f"Реши задачу номер {i}: отсортировать список [3,1,4,1,5]",
                mode="task"
            )
        
        # 2. Запускаем анализ обучения
        result = await enhanced_chat(
            question="Запусти цикл самообучения и проанализируй мой опыт",
            mode="task"
        )
        
        # Должен использовать learning tools
        assert any("learning" in str(tc) for tc in result.get("tool_calls", []))
    
    @pytest.mark.asyncio
    async def test_simple_chat_compatibility(self):
        """Тест обратной совместимости simple_chat"""
        
        # Phase 1 функция должна работать с новыми возможностями Phase 2
        result = await simple_chat(
            question="Что ты знаешь о Python?",
            chat_id=12345
        )
        
        assert "answer" in result  # Старый формат
        assert result["answer"] is not None
        assert "metadata" in result
        assert result["metadata"]["context_used"] is not None
    
    @pytest.mark.asyncio
    async def test_tool_calls_across_phases(self):
        """Тест вызова инструментов из разных фаз"""
        
        result = await enhanced_chat(
            question="Сохрани факт что Earth is a planet, затем найди все факты о Earth",
            mode="task"
        )
        
        # Должны быть вызваны инструменты из обеих фаз
        tool_calls = result.get("tool_calls", [])
        assert len(tool_calls) >= 2
        
        # Проверяем что использовались разные типы инструментов
        tool_names = [tc.get("name", "") for tc in tool_calls]
        # save_fact или remember_fact из Phase 2
        assert any("fact" in name for name in tool_names)
        # search_memory из Phase 1 или vector_search из Phase 2
        assert any("search" in name for name in tool_names)
    
    @pytest.mark.asyncio
    async def test_error_handling_consistency(self):
        """Тест согласованности обработки ошибок между фазами"""
        
        # Некорректный запрос
        result = await enhanced_chat(
            question="",  # Пустой вопрос
            user_id="test_user"
        )
        
        # Не должно быть критической ошибки
        assert result["content"] is not None
        assert not result.get("error", False) or "error" in result["metadata"]
    
    @pytest.mark.asyncio
    async def test_performance_with_all_tools(self):
        """Тест производительности со всеми инструментами"""
        import time
        
        start_time = time.time()
        
        # Сложный запрос использующий множество инструментов
        result = await enhanced_chat(
            question="""Сделай следующее:
            1. Запомни что я эксперт в Machine Learning
            2. Найди всю информацию обо мне
            3. Проанализируй мои навыки
            4. Дай рекомендации по обучению""",
            user_id="test_ml_expert",
            mode="task"
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        assert result["content"] is not None
        assert duration < 30  # Не должно занимать больше 30 секунд
        assert len(result.get("tool_calls", [])) >= 3  # Минимум 3 инструмента
    
    @pytest.mark.asyncio
    async def test_memory_persistence(self):
        """Тест персистентности памяти между вызовами"""
        
        user_id = "test_persistence_user"
        
        # Сохраняем информацию
        await enhanced_chat(
            question="Запомни: мой любимый цвет - синий",
            user_id=user_id
        )
        
        # Создаем новый экземпляр чата (симуляция перезапуска)
        from app.agents.chat_handler import _agent_instance
        _agent_instance = None  # Сброс глобального экземпляра
        
        # Проверяем что информация сохранилась
        result = await enhanced_chat(
            question="Какой мой любимый цвет?",
            user_id=user_id
        )
        
        assert "синий" in result["content"].lower() or "blue" in result["content"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])