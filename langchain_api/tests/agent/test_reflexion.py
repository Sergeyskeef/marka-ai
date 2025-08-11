#!/usr/bin/env python3
"""
Тесты для системы саморефлексии агента
"""

import pytest
import time
import asyncio
import unittest.mock as mock
from unittest.mock import MagicMock, patch, AsyncMock

from core.agent.reflexion import (
    ReflexionAgent,
    reflexion_agent
)


class TestReflexionAgent:
    """Тесты для ReflexionAgent"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        self.agent = ReflexionAgent()
        
        # Мокаем драйвер Neo4j
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_driver.session.return_value.__enter__.return_value = self.mock_session
    
    def test_build_reflection_prompt_basic(self):
        """Тест построения базового промпта для рефлексии"""
        prompt = self.agent._build_reflection_prompt(
            user_question="Как дела?",
            attempt_result="Я не смог ответить",
            error_details=None,
            tool_outcomes=None
        )
        
        assert "Как дела?" in prompt
        assert "Я не смог ответить" in prompt
        assert "Что пошло не так?" in prompt
        assert "Что можно попробовать" in prompt
    
    def test_build_reflection_prompt_with_error(self):
        """Тест построения промпта с деталями ошибки"""
        prompt = self.agent._build_reflection_prompt(
            user_question="Посчитай 2+2",
            attempt_result="Ошибка выполнения",
            error_details="ValueError: invalid literal",
            tool_outcomes=None
        )
        
        assert "ValueError: invalid literal" in prompt
        assert "ДЕТАЛИ ОШИБКИ:" in prompt
    
    def test_build_reflection_prompt_with_tools(self):
        """Тест построения промпта с результатами инструментов"""
        tool_outcomes = [
            {"tool_name": "calculator", "status": "fail", "duration_ms": 100, "error": "division by zero"},
            {"tool_name": "search", "status": "success", "duration_ms": 50}
        ]
        
        prompt = self.agent._build_reflection_prompt(
            user_question="Раздели на ноль",
            attempt_result="Не получилось",
            error_details=None,
            tool_outcomes=tool_outcomes
        )
        
        assert "calculator: fail" in prompt
        assert "search: success" in prompt
        assert "division by zero" in prompt
        assert "РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ:" in prompt
    
    def test_format_tool_outcomes_empty(self):
        """Тест форматирования пустого списка инструментов"""
        result = self.agent._format_tool_outcomes([])
        assert result == "Инструменты не использовались"
        
        result = self.agent._format_tool_outcomes(None)
        assert result == "Инструменты не использовались"
    
    def test_format_tool_outcomes_with_data(self):
        """Тест форматирования результатов инструментов"""
        tool_outcomes = [
            {"tool_name": "calculator", "status": "success", "duration_ms": 50},
            {"tool_name": "web_search", "status": "fail", "duration_ms": 200, "error": "timeout"}
        ]
        
        result = self.agent._format_tool_outcomes(tool_outcomes)
        
        assert "calculator: success (50ms)" in result
        assert "web_search: fail (200ms)" in result
        assert "Ошибка: timeout" in result
    
    def test_extract_insights(self):
        """Тест извлечения инсайтов из рефлексии"""
        reflection1 = "Мне не хватает информации для ответа. Стоит попробовать другой подход."
        insights1 = self.agent._extract_insights(reflection1)
        
        assert "need_more_info" in insights1
        assert "try_different_approach" in insights1
        
        reflection2 = "Произошла ошибка в инструменте calculation."
        insights2 = self.agent._extract_insights(reflection2)
        
        assert "error_analysis" in insights2
        assert "tool_related" in insights2
    
    @pytest.mark.asyncio
    async def test_get_llm_reflection_success(self):
        """Тест успешного получения рефлексии от LLM"""
        # Мокаем ответ LLM
        mock_response = MagicMock()
        mock_response.content = "Анализ: проблема в том, что я не учел контекст. В следующий раз нужно использовать поиск в памяти."
        
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        
        with patch('langchain_api.core.agent.reflexion.chat_model', return_value=mock_model):
            result = await self.agent._get_llm_reflection("test prompt")
            
            assert result == "Анализ: проблема в том, что я не учел контекст. В следующий раз нужно использовать поиск в памяти."
            mock_model.ainvoke.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_llm_reflection_error(self):
        """Тест обработки ошибки при получении рефлексии от LLM"""
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = Exception("LLM error")
        
        with patch('langchain_api.core.agent.reflexion.chat_model', return_value=mock_model):
            result = await self.agent._get_llm_reflection("test prompt")
            
            assert "Не удалось получить рефлексию" in result
            assert "LLM error" in result
    
    @pytest.mark.asyncio
    async def test_save_diary_entry_success(self):
        """Тест успешного сохранения записи в дневник"""
        # Мокаем ответ Neo4j
        mock_record = MagicMock()
        self.mock_session.run.return_value.single.return_value = mock_record
        
        with patch.object(ReflexionAgent, 'driver', self.mock_driver):
            result = await self.agent._save_diary_entry(
                user_id="test_user",
                content="Test reflection",
                source="self",
                context={"key": "value"}
            )
            
            assert result["success"] is True
            assert result["user_id"] == "test_user"
            assert result["content"] == "Test reflection"
            assert result["source"] == "self"
            assert "diary_" in result["id"]
            
            # Проверяем что Neo4j запрос был выполнен
            self.mock_session.run.assert_called_once()
            call_args = self.mock_session.run.call_args
            params = call_args[0][1]
            assert params["user_id"] == "test_user"
            assert params["content"] == "Test reflection"
            assert params["source"] == "self"
    
    @pytest.mark.asyncio
    async def test_save_diary_entry_error(self):
        """Тест обработки ошибки при сохранении в дневник"""
        self.mock_session.run.side_effect = Exception("Neo4j error")
        
        with patch.object(ReflexionAgent, 'driver', self.mock_driver):
            result = await self.agent._save_diary_entry(
                user_id="test_user",
                content="Test reflection"
            )
            
            assert result["success"] is False
            assert "Neo4j error" in result["error"]
    
    @pytest.mark.asyncio
    async def test_self_reflect_success(self):
        """Тест успешной саморефлексии"""
        # Мокаем LLM
        mock_response = MagicMock()
        mock_response.content = "Анализ ошибки: нужно больше контекста"
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        
        # Мокаем сохранение в дневник
        mock_diary_entry = {
            "id": "diary_123",
            "success": True,
            "user_id": "test_user",
            "content": "Анализ ошибки: нужно больше контекста"
        }
        
        with patch('langchain_api.core.agent.reflexion.chat_model', return_value=mock_model), \
             patch.object(self.agent, '_save_diary_entry', return_value=mock_diary_entry):
            
            result = await self.agent.self_reflect(
                user_question="Как дела?",
                attempt_result="Не знаю",
                error_details="Нет данных",
                user_id="test_user"
            )
            
            assert result["success"] is True
            assert result["reflection"] == "Анализ ошибки: нужно больше контекста"
            assert result["diary_entry"]["id"] == "diary_123"
            assert len(result["insights"]) >= 0
    
    @pytest.mark.asyncio
    async def test_self_reflect_error(self):
        """Тест обработки ошибки в саморефлексии"""
        # Мокаем ошибку LLM
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = Exception("LLM failed")
        
        # Мокаем драйвер Neo4j чтобы избежать реального подключения
        mock_diary_entry = {"id": "test_diary", "success": True}
        
        with patch('langchain_api.core.agent.reflexion.chat_model', return_value=mock_model), \
             patch.object(self.agent, '_save_diary_entry', return_value=mock_diary_entry):
            
            result = await self.agent.self_reflect(
                user_question="Тест",
                attempt_result="Ошибка",
                user_id="test_user"
            )
            
            assert result["success"] is False
            assert "Partial failure" in result["error"]
            assert "Не удалось получить рефлексию" in result["reflection"]
            assert result["diary_entry"] is not None
    
    @pytest.mark.asyncio
    async def test_get_recent_reflections(self):
        """Тест получения последних записей рефлексии"""
        # Мокаем результаты из Neo4j
        mock_records = [
            {"d": {"id": "diary_1", "content": "Reflection 1"}},
            {"d": {"id": "diary_2", "content": "Reflection 2"}}
        ]
        self.mock_session.run.return_value = mock_records
        
        with patch.object(ReflexionAgent, 'driver', self.mock_driver):
            result = await self.agent.get_recent_reflections("test_user", limit=5)
            
            assert len(result) == 2
            assert result[0]["id"] == "diary_1"
            assert result[1]["id"] == "diary_2"
            
            # Проверяем запрос
            call_args = self.mock_session.run.call_args
            params = call_args[0][1]
            assert params["user_id"] == "test_user"
            assert params["limit"] == 5
    
    @pytest.mark.asyncio
    async def test_get_reflection_stats(self):
        """Тест получения статистики рефлексии"""
        # Мокаем результат запроса
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {
            "total_reflections": 10,
            "last_reflection_time": 1640995200.0,
            "first_reflection_time": 1640908800.0
        }[key]
        
        self.mock_session.run.return_value.single.return_value = mock_record
        
        with patch.object(ReflexionAgent, 'driver', self.mock_driver):
            result = await self.agent.get_reflection_stats("test_user")
            
            assert result["total_reflections"] == 10
            assert result["last_reflection_time"] == 1640995200.0
            assert result["first_reflection_time"] == 1640908800.0


class TestGlobalReflexionAgent:
    """Тесты для глобального экземпляра reflexion_agent"""
    
    def test_global_instance_exists(self):
        """Тест что глобальный экземпляр существует"""
        assert reflexion_agent is not None
        assert isinstance(reflexion_agent, ReflexionAgent)
    
    def test_global_instance_is_singleton(self):
        """Тест что глобальный экземпляр - синглтон"""
        from core.agent.reflexion import reflexion_agent as agent2
        assert reflexion_agent is agent2


@pytest.mark.integration
class TestReflexionAgentIntegration:
    """Интеграционные тесты с реальным Neo4j"""
    
    @pytest.mark.asyncio
    async def test_real_self_reflect(self):
        """Тест саморефлексии с реальным Neo4j"""
        # Используем уникальные ID для избежания конфликтов
        unique_id = f"test_{int(time.time())}"
        user_id = f"user_{unique_id}"
        
        agent = ReflexionAgent()
        
        try:
            # Мокаем только LLM, оставляем Neo4j реальным
            mock_response = MagicMock()
            mock_response.content = f"Тестовая рефлексия {unique_id}: проблема в недостатке данных. Нужно попробовать использовать поиск."
            mock_model = AsyncMock()
            mock_model.ainvoke.return_value = mock_response
            
            with patch('langchain_api.core.agent.reflexion.chat_model', return_value=mock_model):
                result = await agent.self_reflect(
                    user_question=f"Тестовый вопрос {unique_id}",
                    attempt_result="Не удалось ответить",
                    error_details="Нет данных",
                    user_id=user_id
                )
            
            assert result["success"] is True
            assert f"Тестовая рефлексия {unique_id}" in result["reflection"]
            assert result["diary_entry"]["success"] is True
            # Проверяем что хотя бы один инсайт извлечен
            assert len(result["insights"]) > 0
            # Проверяем что есть хотя бы один из ожидаемых инсайтов
            expected_insights = ["need_more_info", "try_different_approach", "error_analysis", "tool_related"]
            assert any(insight in result["insights"] for insight in expected_insights)
            
            # Проверяем что запись сохранилась
            recent = await agent.get_recent_reflections(user_id, limit=1)
            assert len(recent) == 1
            assert f"Тестовая рефлексия {unique_id}" in recent[0]["content"]
            
            # Проверяем статистику
            stats = await agent.get_reflection_stats(user_id)
            assert stats["total_reflections"] == 1
            
        finally:
            # Очищаем тестовые данные
            with agent.driver.session() as session:
                session.run(
                    "MATCH (u:User {id: $user_id})-[:WRITES]->(d:DiaryEntry) DETACH DELETE u, d",
                    {"user_id": user_id}
                )
            agent.close()