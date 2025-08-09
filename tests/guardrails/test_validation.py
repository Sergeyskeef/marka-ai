#!/usr/bin/env python3
"""
Тесты для Guardrails валидации
"""
import pytest
from unittest.mock import patch, MagicMock

from core.guardrails_client import (
    GuardrailsValidator,
    validate_llm_input,
    validate_llm_output,
    validate_tool_call,
    with_guardrails
)


class TestGuardrailsValidator:
    """Тесты для GuardrailsValidator"""
    
    def test_init_disabled(self):
        """Тест инициализации с отключенными Guardrails"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=False):
            validator = GuardrailsValidator()
            assert not validator.enabled
            assert validator.config == {}
    
    def test_init_enabled(self):
        """Тест инициализации с включенными Guardrails"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.GuardrailsValidator._load_config') as mock_load:
                mock_load.return_value = {
                    'rails': {
                        'input': {
                            'flows': [
                                {
                                    'name': 'input_validation',
                                    'steps': [
                                        {
                                            'name': 'check_length',
                                            'config': {
                                                'max_length': 100,
                                                'min_length': 1
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
                validator = GuardrailsValidator()
                assert validator.enabled
                assert 'rails' in validator.config
    
    def test_validate_input_disabled(self):
        """Тест валидации входящих данных при отключенных Guardrails"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=False):
            validator = GuardrailsValidator()
            result = validator.validate_input("test text")
            assert result["valid"] is True
            assert result["issues"] == []
    
    def test_validate_input_too_long(self):
        """Тест валидации слишком длинного текста"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.GuardrailsValidator._load_config') as mock_load:
                mock_load.return_value = {
                    'rails': {
                        'input': {
                            'flows': [
                                {
                                    'name': 'input_validation',
                                    'steps': [
                                        {
                                            'name': 'check_length',
                                            'config': {
                                                'max_length': 10,
                                                'min_length': 1
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
                validator = GuardrailsValidator()
                result = validator.validate_input("This is a very long text that exceeds the limit")
                assert result["valid"] is False
                assert "превышает максимальную длину" in result["issues"][0]
    
    def test_validate_input_too_short(self):
        """Тест валидации слишком короткого текста"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.GuardrailsValidator._load_config') as mock_load:
                mock_load.return_value = {
                    'rails': {
                        'input': {
                            'flows': [
                                {
                                    'name': 'input_validation',
                                    'steps': [
                                        {
                                            'name': 'check_length',
                                            'config': {
                                                'max_length': 100,
                                                'min_length': 5
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
                validator = GuardrailsValidator()
                result = validator.validate_input("Hi")
                assert result["valid"] is False
                assert "короче минимальной длины" in result["issues"][0]
    
    def test_validate_output_disabled(self):
        """Тест валидации исходящих данных при отключенных Guardrails"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=False):
            validator = GuardrailsValidator()
            result = validator.validate_output({"role": "assistant", "content": "test"})
            assert result["valid"] is True
            assert result["issues"] == []
    
    def test_validate_output_missing_required_fields(self):
        """Тест валидации ответа без обязательных полей"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            validator = GuardrailsValidator()
            result = validator.validate_output({"content": "test"})  # Нет поля role
            assert result["valid"] is False
            assert "Отсутствует обязательное поле: role" in result["issues"]
    
    def test_validate_output_invalid_role(self):
        """Тест валидации ответа с недопустимой ролью"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            validator = GuardrailsValidator()
            result = validator.validate_output({"role": "invalid", "content": "test"})
            assert result["valid"] is False
            assert "Недопустимая роль: invalid" in result["issues"]
    
    def test_validate_output_content_too_long(self):
        """Тест валидации ответа с слишком длинным контентом"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            validator = GuardrailsValidator()
            long_content = "x" * 9000  # Больше лимита 8192
            result = validator.validate_output({"role": "assistant", "content": long_content})
            assert result["valid"] is False
            assert "превышает максимальную длину" in result["issues"][0]
    
    def test_validate_tool_call_disabled(self):
        """Тест валидации вызова инструмента при отключенных Guardrails"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=False):
            validator = GuardrailsValidator()
            result = validator.validate_tool_call("test_tool", {"arg1": "value1"})
            assert result["valid"] is True
            assert result["issues"] == []
    
    def test_validate_tool_call_not_allowed(self):
        """Тест валидации неразрешенного инструмента"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.GuardrailsValidator._load_config') as mock_load:
                mock_load.return_value = {
                    'tools': {
                        'validation': {
                            'allowed_tools': ['allowed_tool']
                        }
                    }
                }
                validator = GuardrailsValidator()
                result = validator.validate_tool_call("forbidden_tool", {"arg1": "value1"})
                assert result["valid"] is False
                assert "не разрешен" in result["issues"][0]


class TestGuardrailsFunctions:
    """Тесты для функций Guardrails"""
    
    def test_validate_llm_input(self):
        """Тест функции validate_llm_input"""
        with patch('langchain_api.core.guardrails_client.guardrails_validator') as mock_validator:
            mock_validator.validate_input.return_value = {"valid": True, "issues": []}
            result = validate_llm_input("test text")
            mock_validator.validate_input.assert_called_once_with("test text", None)
            assert result["valid"] is True
    
    def test_validate_llm_output(self):
        """Тест функции validate_llm_output"""
        with patch('langchain_api.core.guardrails_client.guardrails_validator') as mock_validator:
            mock_validator.validate_output.return_value = {"valid": True, "issues": []}
            result = validate_llm_output({"role": "assistant", "content": "test"})
            mock_validator.validate_output.assert_called_once_with({"role": "assistant", "content": "test"})
            assert result["valid"] is True
    
    def test_validate_tool_call(self):
        """Тест функции validate_tool_call"""
        with patch('langchain_api.core.guardrails_client.guardrails_validator') as mock_validator:
            mock_validator.validate_tool_call.return_value = {"valid": True, "issues": []}
            result = validate_tool_call("test_tool", {"arg1": "value1"})
            mock_validator.validate_tool_call.assert_called_once_with("test_tool", {"arg1": "value1"})
            assert result["valid"] is True


class TestGuardrailsDecorator:
    """Тесты для декоратора with_guardrails"""
    
    def test_decorator_disabled(self):
        """Тест декоратора при отключенных Guardrails"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=False):
            
            @with_guardrails
            def test_function(text):
                return {"role": "assistant", "content": text}
            
            result = test_function("Hello")
            assert result["role"] == "assistant"
            assert result["content"] == "Hello"
    
    def test_decorator_enabled_valid_input(self):
        """Тест декоратора с валидными входящими данными"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.validate_llm_input') as mock_validate_input:
                with patch('langchain_api.core.guardrails_client.validate_llm_output') as mock_validate_output:
                    mock_validate_input.return_value = {"valid": True, "issues": []}
                    mock_validate_output.return_value = {"valid": True, "issues": []}
                    
                    @with_guardrails
                    def test_function(text):
                        return {"role": "assistant", "content": text}
                    
                    result = test_function("Hello")
                    assert result["role"] == "assistant"
                    assert result["content"] == "Hello"
    
    def test_decorator_enabled_invalid_input(self):
        """Тест декоратора с невалидными входящими данными"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.validate_llm_input') as mock_validate_input:
                mock_validate_input.return_value = {"valid": False, "issues": ["Text too long"]}
                
                @with_guardrails
                def test_function(text):
                    return {"role": "assistant", "content": text}
                
                with pytest.raises(ValueError, match="Валидация входящих данных не прошла"):
                    test_function("Very long text")
    
    def test_decorator_enabled_invalid_output(self):
        """Тест декоратора с невалидными исходящими данными"""
        with patch('langchain_api.core.guardrails_client.is_guardrails_enabled', return_value=True):
            with patch('langchain_api.core.guardrails_client.validate_llm_input') as mock_validate_input:
                with patch('langchain_api.core.guardrails_client.validate_llm_output') as mock_validate_output:
                    mock_validate_input.return_value = {"valid": True, "issues": []}
                    mock_validate_output.return_value = {"valid": False, "issues": ["Invalid role"]}
                    
                    @with_guardrails
                    def test_function(text):
                        return {"invalid": "response"}
                    
                    with pytest.raises(ValueError, match="Валидация исходящих данных не прошла"):
                        test_function("Hello")


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 