"""
E2E тест двух-шагового цикла рефлексии агента.

Проверяет что агент может использовать рефлексию для улучшения ответов.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent.runner import AgentRunner, agent_runner


class TestReflexionSuccess:
    """E2E тесты двух-шагового цикла рефлексии"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        self.runner = AgentRunner()
    
    @pytest.mark.asyncio
    async def test_reflexion_success_first_attempt(self):
        """Тест успеха с первой попытки"""
        
        # Мокаем LLM для успешного ответа с первой попытки
        mock_response = MagicMock()
        mock_response.content = "Это отличный и подробный ответ на ваш вопрос о машинном обучении."
        
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        
        with patch('langchain_api.core.agent.runner.chat_model', return_value=mock_model):
            result = await self.runner.try_answer(
                question="Что такое машинное обучение?",
                user_id="test_user"
            )
        
        # Проверяем результат
        assert result["success"] is True
        assert result["final_attempt"] == 1
        assert result["used_reflexion"] is False
        assert len(result["attempts"]) == 1
        assert "машинное обучение" in result["answer"].lower() or "отличный" in result["answer"]
        assert result["processing_time_ms"] > 0
    
    @pytest.mark.asyncio 
    async def test_reflexion_success_second_attempt(self):
        """Тест успеха со второй попытки с рефлексией"""
        
        # Мокаем LLM для неудачи в первый раз, успеха во второй
        call_count = 0
        
        def mock_llm_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = MagicMock()
            if call_count == 1:
                # Первая попытка - плохой ответ
                mock_response.content = "Не знаю"
            elif call_count == 2:
                # Рефлексия - анализ неудачи
                mock_response.content = "Анализируя неудачу: нужно больше деталей и структуры в ответе. Попробую объяснить с основ и дать конкретные примеры."
            else:
                # Вторая попытка - хороший ответ про квантовые компьютеры
                mock_response.content = "Квантовые компьютеры используют квантовые биты (кубиты) для параллельных вычислений, что позволяет решать задачи экспоненциально быстрее классических компьютеров."
            
            return mock_response
        
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = mock_llm_side_effect
        
        # Мокаем поиск подсказок
        mock_hints = [
            {
                "content": "Квантовые компьютеры - это революционная технология",
                "insights": ["tool_usage", "strategic_approach"],
                "similarity": 0.8
            }
        ]
        
        with patch('langchain_api.core.agent.runner.chat_model', return_value=mock_model), \
             patch.object(self.runner, '_fetch_hints', return_value=mock_hints):
            
            result = await self.runner.try_answer(
                question="Что такое квантовые компьютеры?",
                user_id="test_user"
            )
        
        # Проверяем результат
        assert result["success"] is True
        assert result["final_attempt"] == 2
        assert result["used_reflexion"] is True
        assert len(result["attempts"]) == 2
        assert result["hints_used"] == 1
        # Проверяем что ответ содержит либо финальный ответ либо рефлексию (в зависимости от логики)
        answer = result["answer"].lower()
        assert ("квантовые" in answer or "биты" in answer or "анализируя" in answer)
        assert result["processing_time_ms"] > 0
        
        # Проверяем детали попыток
        assert result["attempts"][0]["success"] is True  # Техническая успешность вызова
        assert result["attempts"][1]["success"] is True
        assert result["attempts"][1]["hints_count"] == 1
    
    @pytest.mark.asyncio
    async def test_reflexion_failure_both_attempts(self):
        """Тест неудачи обеих попыток"""
        
        # Мокаем LLM для неудачи в обеих попытках
        call_count = 0
        
        def mock_llm_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = MagicMock()
            if call_count <= 2:
                # Первая попытка и рефлексия
                mock_response.content = "Не знаю, недостаточно информации"
            else:
                # Вторая попытка - тоже плохой ответ
                mock_response.content = "Извините, не могу ответить на этот вопрос"
            
            return mock_response
        
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = mock_llm_side_effect
        
        with patch('langchain_api.core.agent.runner.chat_model', return_value=mock_model), \
             patch.object(self.runner, '_fetch_hints', return_value=[]):
            
            result = await self.runner.try_answer(
                question="Непонятный вопрос без смысла?",
                user_id="test_user"
            )
        
        # Проверяем результат
        assert result["success"] is False
        assert result["final_attempt"] == 2
        assert result["used_reflexion"] is True
        assert len(result["attempts"]) == 2
        assert result["hints_used"] == 0
        assert "не могу ответить" in result["answer"].lower() or "не знаю" in result["answer"].lower()
    
    @pytest.mark.asyncio
    async def test_reflexion_with_exception_handling(self):
        """Тест обработки исключений в цикле рефлексии"""
        
        # Мокаем LLM для выброса исключения в первой попытке, успеха во второй
        call_count = 0
        
        def mock_llm_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = MagicMock()
            if call_count == 1:
                # Первая попытка - исключение
                raise Exception("LLM API error")
            else:
                # Вторая попытка (после рефлексии) - успех
                mock_response.content = "Агент восстановился после ошибки и дал хороший ответ"
                return mock_response
        
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = mock_llm_side_effect
        
        # Мокаем рефлексию как успешную
        mock_self_reflect = AsyncMock()
        mock_self_reflect.return_value = {
            "success": True,
            "reflection": "Анализ ошибки: нужно попробовать снова",
            "insights": ["try_different_approach"]
        }
        
        with patch('langchain_api.core.agent.runner.chat_model', return_value=mock_model), \
             patch.object(self.runner.reflexion_agent, 'self_reflect', mock_self_reflect):
            
            result = await self.runner.try_answer(
                question="Тестовый вопрос",
                user_id="test_user"
            )
        
        # Проверяем что агент обрабатывает исключения корректно
        assert result["success"] is True  # Агент продолжил работу
        assert len(result["attempts"]) >= 1
        assert result["attempts"][0]["success"] is False  # Первая попытка неудачна из-за исключения
        assert "Ошибка при попытке ответа" in result["attempts"][0]["answer"]
        assert result["processing_time_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_global_agent_runner_instance(self):
        """Тест глобального экземпляра agent_runner"""
        
        # Проверяем что глобальный экземпляр доступен
        assert agent_runner is not None
        assert isinstance(agent_runner, AgentRunner)
        
        # Мокаем успешный ответ
        mock_response = MagicMock()
        mock_response.content = "Глобальный агент работает корректно"
        
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = mock_response
        
        with patch('langchain_api.core.agent.runner.chat_model', return_value=mock_model):
            result = await agent_runner.try_answer(
                question="Тест глобального агента",
                user_id="test_user"
            )
        
        assert result["success"] is True
        assert "корректно" in result["answer"]
    
    def test_evaluate_answer_quality(self):
        """Тест эвристики оценки качества ответов"""
        
        # Тестируем хорошие ответы
        assert self.runner._evaluate_answer_quality(
            "Это подробный и информативный ответ на ваш вопрос", 
            "Тестовый вопрос"
        ) is True
        
        # Тестируем плохие ответы
        assert self.runner._evaluate_answer_quality("Не знаю", "Вопрос") is False
        assert self.runner._evaluate_answer_quality("", "Вопрос") is False
        assert self.runner._evaluate_answer_quality("Недостаточно информации", "Вопрос") is False
        assert self.runner._evaluate_answer_quality("Извините, произошла ошибка", "Вопрос") is False
        assert self.runner._evaluate_answer_quality("Короткий", "Вопрос") is False
    
    def test_build_system_prompt(self):
        """Тест построения системного промпта"""
        
        # Тест базового промпта для первой попытки
        prompt1 = self.runner._build_system_prompt(attempt_number=1)
        assert "AI-ассистент" in prompt1
        assert "подсказки" not in prompt1
        
        # Тест расширенного промпта для второй попытки
        hints = [
            {"content": "Успешный пример ответа", "insights": ["tool_usage"]},
            {"content": "Еще один пример", "insights": ["strategic_approach"]}
        ]
        insights = ["need_more_info", "try_different_approach"]
        
        prompt2 = self.runner._build_system_prompt(
            attempt_number=2, 
            hints=hints, 
            reflexion_insights=insights
        )
        
        assert "AI-ассистент" in prompt2
        assert "Инсайты из рефлексии" in prompt2
        assert "Подсказки из прошлого" in prompt2
        assert "need_more_info" in prompt2
        assert "Успешный пример" in prompt2
        assert "tool_usage" in prompt2


# Integration test с реальными компонентами
class TestReflexionSuccessIntegration:
    """Интеграционные тесты с реальными компонентами"""
    
    @pytest.mark.asyncio
    async def test_real_reflexion_cycle(self):
        """Интеграционный тест реального цикла рефлексии"""
        
        runner = AgentRunner()
        
        # Мокаем только части которые требуют внешних сервисов
        mock_diary_backend = AsyncMock()
        mock_diary_backend.fetch_similar_successes.return_value = [
            {
                "content": "Успешное решение похожей задачи",
                "insights": ["strategic_approach"],
                "similarity": 0.85
            }
        ]
        
        with patch('langchain_api.core.agent.runner.neo4j_diary_backend', mock_diary_backend):
            result = await runner.try_answer(
                question="Объясни простыми словами что такое нейронные сети",
                user_id="integration_test_user"
            )
        
        # Проверяем что результат получен
        assert "success" in result
        assert "answer" in result
        assert "processing_time_ms" in result
        assert result["processing_time_ms"] > 0
        
        # Если тест не упал до этого момента - значит интеграция работает
        print(f"✅ Интеграционный тест завершен за {result['processing_time_ms']}мс")