import pytest
from unittest.mock import patch, MagicMock
from core.prompt_adapter import PromptAdapter, get_prompt_adapter

class TestPromptAdapter:
    """Тесты для адаптера промптов"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.adapter = PromptAdapter()
        self.user_id = "test_user_123"
    
    def test_get_user_preferences_default(self):
        """Тест получения предпочтений по умолчанию"""
        with patch('langchain_api.core.prompt_adapter.get_all_user_prefs') as mock_get_prefs:
            mock_get_prefs.return_value = {}
            
            prefs = self.adapter.get_user_preferences(self.user_id)
            
            assert prefs == {
                "style": "detailed",
                "detail_level": "medium"
            }
            mock_get_prefs.assert_called_once_with(self.user_id)
    
    def test_get_user_preferences_existing(self):
        """Тест получения существующих предпочтений"""
        with patch('langchain_api.core.prompt_adapter.get_all_user_prefs') as mock_get_prefs:
            mock_get_prefs.return_value = {
                "style": "brief",
                "detail_level": "quick"
            }
            
            prefs = self.adapter.get_user_preferences(self.user_id)
            
            assert prefs == {
                "style": "brief",
                "detail_level": "quick"
            }
            mock_get_prefs.assert_called_once_with(self.user_id)
    
    def test_get_user_preferences_error(self):
        """Тест обработки ошибки при получении предпочтений"""
        with patch('langchain_api.core.prompt_adapter.get_all_user_prefs') as mock_get_prefs:
            mock_get_prefs.side_effect = Exception("Database error")
            
            prefs = self.adapter.get_user_preferences(self.user_id)
            
            # Должны вернуться предпочтения по умолчанию
            assert prefs == {
                "style": "detailed",
                "detail_level": "medium"
            }
    
    def test_adapt_prompt_no_preferences(self):
        """Тест адаптации промпта без предпочтений"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {}
            
            base_prompt = "Base prompt"
            result = self.adapter.adapt_prompt(base_prompt, self.user_id)
            
            # Без предпочтений пользователя все равно добавляется модификатор режима по умолчанию
            assert "Base prompt" in result
            assert "Общайся в дружелюбном разговорном стиле" in result
    
    def test_adapt_prompt_with_style(self):
        """Тест адаптации промпта со стилем"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "brief"}
            
            base_prompt = "Base prompt"
            result = self.adapter.adapt_prompt(base_prompt, self.user_id)
            
            assert "Base prompt" in result
            assert "Отвечай кратко и по существу" in result
            assert "## Инструкции по стилю ответа:" in result
    
    def test_adapt_prompt_with_detail_level(self):
        """Тест адаптации промпта с уровнем детализации"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"detail_level": "comprehensive"}
            
            base_prompt = "Base prompt"
            result = self.adapter.adapt_prompt(base_prompt, self.user_id)
            
            assert "Base prompt" in result
            assert "исчерпывающий ответ" in result
            assert "## Инструкции по стилю ответа:" in result
    
    def test_adapt_prompt_with_mode(self):
        """Тест адаптации промпта с режимом"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {}
            
            base_prompt = "Base prompt"
            result = self.adapter.adapt_prompt(base_prompt, self.user_id, mode="code")
            
            assert "Base prompt" in result
            assert "технических аспектах" in result
            assert "## Инструкции по стилю ответа:" in result
    
    def test_adapt_prompt_full(self):
        """Тест полной адаптации промпта"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {
                "style": "creative",
                "detail_level": "detailed"
            }
            
            base_prompt = "Base prompt"
            result = self.adapter.adapt_prompt(base_prompt, self.user_id, mode="plan")
            
            assert "Base prompt" in result
            assert "творческий и образный стиль" in result
            assert "важные детали и нюансы" in result
            assert "план действий с четкими шагами" in result
            assert "## Инструкции по стилю ответа:" in result
    
    def test_adapt_chat_prompt(self):
        """Тест адаптации промпта для чата"""
        with patch.object(self.adapter, 'adapt_prompt') as mock_adapt:
            mock_adapt.return_value = "Adapted prompt"
            
            question = "Как дела?"
            context = "Контекст из памяти"
            
            result = self.adapter.adapt_chat_prompt(self.user_id, question, context)
            
            assert result == "Adapted prompt"
            mock_adapt.assert_called_once()
            
            # Проверяем аргументы вызова
            call_args = mock_adapt.call_args
            base_prompt = call_args[0][0]
            
            assert question in base_prompt
            assert context in base_prompt
            assert "умный помощник" in base_prompt
            assert call_args[0][1] == self.user_id
            assert call_args[1]["mode"] == "chat"
    
    def test_adapt_code_prompt(self):
        """Тест адаптации промпта для кода"""
        with patch.object(self.adapter, 'adapt_prompt') as mock_adapt:
            mock_adapt.return_value = "Code adapted prompt"
            
            code_request = "Напиши функцию сортировки"
            
            result = self.adapter.adapt_code_prompt(self.user_id, code_request)
            
            assert result == "Code adapted prompt"
            mock_adapt.assert_called_once()
            
            # Проверяем аргументы вызова
            call_args = mock_adapt.call_args
            base_prompt = call_args[0][0]
            
            assert code_request in base_prompt
            assert "опытный программист" in base_prompt
            assert call_args[0][1] == self.user_id
            assert call_args[1]["mode"] == "code"
    
    def test_adapt_planning_prompt(self):
        """Тест адаптации промпта для планирования"""
        with patch.object(self.adapter, 'adapt_prompt') as mock_adapt:
            mock_adapt.return_value = "Planning adapted prompt"
            
            task = "Организовать мероприятие"
            
            result = self.adapter.adapt_planning_prompt(self.user_id, task)
            
            assert result == "Planning adapted prompt"
            mock_adapt.assert_called_once()
            
            # Проверяем аргументы вызова
            call_args = mock_adapt.call_args
            base_prompt = call_args[0][0]
            
            assert task in base_prompt
            assert "стратегический планировщик" in base_prompt
            assert call_args[0][1] == self.user_id
            assert call_args[1]["mode"] == "plan"

class TestFeedbackAdaptation:
    """Тесты для адаптации на основе обратной связи"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.adapter = PromptAdapter()
        self.user_id = "test_user_123"
    
    def test_feedback_positive(self):
        """Тест положительной обратной связи"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "brief"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "positive"
            )
            
            assert "Отлично" in result
            assert "том же стиле" in result
    
    def test_feedback_negative_brief_style(self):
        """Тест отрицательной обратной связи для краткого стиля"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "brief"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "negative"
            )
            
            assert "не понравился" in result
            assert "Подробно" in result
    
    def test_feedback_negative_detailed_style(self):
        """Тест отрицательной обратной связи для подробного стиля"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "detailed"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "negative"
            )
            
            assert "не понравился" in result
            assert "Кратко" in result
    
    def test_feedback_negative_creative_style(self):
        """Тест отрицательной обратной связи для творческого стиля"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "creative"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "negative"
            )
            
            assert "не понравился" in result
            assert "Аналитично" in result
    
    def test_feedback_negative_analytical_style(self):
        """Тест отрицательной обратной связи для аналитического стиля"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "analytical"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "negative"
            )
            
            assert "не понравился" in result
            assert "Креативно" in result
    
    def test_feedback_retry(self):
        """Тест обратной связи 'повторить'"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "brief"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "retry"
            )
            
            assert "по-другому" in result
            assert "предпочтений" in result
    
    def test_feedback_clarify(self):
        """Тест обратной связи 'уточнить'"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "brief"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "clarify"
            )
            
            assert "уточните" in result
            assert "более точный ответ" in result
    
    def test_feedback_unknown_type(self):
        """Тест неизвестного типа обратной связи"""
        with patch.object(self.adapter, 'get_user_preferences') as mock_get_prefs:
            mock_get_prefs.return_value = {"style": "brief"}
            
            result = self.adapter.get_feedback_adapted_response(
                self.user_id, "original response", "unknown"
            )
            
            assert "Спасибо за обратную связь" in result

class TestGlobalAdapter:
    """Тесты для глобального экземпляра адаптера"""
    
    def test_get_prompt_adapter(self):
        """Тест получения глобального экземпляра"""
        adapter = get_prompt_adapter()
        assert isinstance(adapter, PromptAdapter)
        
        # Проверяем, что возвращается тот же экземпляр
        adapter2 = get_prompt_adapter()
        assert adapter is adapter2