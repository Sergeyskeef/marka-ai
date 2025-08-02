#!/usr/bin/env python3
"""
Guardrails клиент для Марк v2
Обеспечивает валидацию входящих и исходящих данных для LLM
"""
import logging
import os
import yaml
from typing import Any, Dict, Optional, Union
from pathlib import Path

from langchain_api.core.graphiti_config import is_guardrails_enabled, get_guardrails_config_path

logger = logging.getLogger(__name__)


class GuardrailsValidator:
    """Валидатор для входящих и исходящих данных с использованием Guardrails"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.enabled = is_guardrails_enabled()
        self.config_path = config_path or get_guardrails_config_path()
        self.config = self._load_config() if self.enabled else {}
        
        if self.enabled:
            logger.info(f"✅ Guardrails включен, конфигурация: {self.config_path}")
        else:
            logger.info("⚠️ Guardrails отключен")
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию Guardrails из файла"""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(f"Файл конфигурации Guardrails не найден: {self.config_path}")
                return {}
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"✅ Конфигурация Guardrails загружена: {len(config.get('rails', {}))} правил")
            return config
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации Guardrails: {e}")
            return {}
    
    def validate_input(self, text: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Валидация входящего текста"""
        if not self.enabled:
            return {"valid": True, "issues": []}
        
        issues = []
        
        # Проверка длины
        max_length = self.config.get('rails', {}).get('input', {}).get('flows', [{}])[0].get('steps', [{}])[0].get('config', {}).get('max_length', 4096)
        if len(text) > max_length:
            issues.append(f"Текст превышает максимальную длину {max_length} символов")
        
        # Проверка минимальной длины
        min_length = self.config.get('rails', {}).get('input', {}).get('flows', [{}])[0].get('steps', [{}])[0].get('config', {}).get('min_length', 1)
        if len(text) < min_length:
            issues.append(f"Текст короче минимальной длины {min_length} символов")
        
        # Простая проверка на нецензурную лексику (можно расширить)
        profanity_words = ['bad_word1', 'bad_word2']  # Заглушка
        for word in profanity_words:
            if word.lower() in text.lower():
                issues.append("Обнаружена нецензурная лексика")
                break
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "text_length": len(text)
        }
    
    def validate_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация исходящего ответа"""
        if not self.enabled:
            return {"valid": True, "issues": []}
        
        issues = []
        
        # Проверка обязательных полей
        required_fields = ["role", "content"]
        for field in required_fields:
            if field not in response:
                issues.append(f"Отсутствует обязательное поле: {field}")
        
        # Проверка роли
        if "role" in response:
            allowed_roles = ["assistant", "user", "system"]
            if response["role"] not in allowed_roles:
                issues.append(f"Недопустимая роль: {response['role']}")
        
        # Проверка длины контента
        if "content" in response:
            max_length = 8192
            if len(response["content"]) > max_length:
                issues.append(f"Контент превышает максимальную длину {max_length} символов")
        
        # Проверка tool_calls если есть
        if "tool_calls" in response:
            if not isinstance(response["tool_calls"], list):
                issues.append("tool_calls должен быть списком")
            else:
                allowed_tools = self.config.get('tools', {}).get('validation', {}).get('allowed_tools', [])
                for tool_call in response["tool_calls"]:
                    if "function" in tool_call and "name" in tool_call["function"]:
                        tool_name = tool_call["function"]["name"]
                        if tool_name not in allowed_tools:
                            issues.append(f"Недопустимый инструмент: {tool_name}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "response_keys": list(response.keys())
        }
    
    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация вызова инструмента"""
        if not self.enabled:
            return {"valid": True, "issues": []}
        
        issues = []
        
        # Проверка разрешенных инструментов
        allowed_tools = self.config.get('tools', {}).get('validation', {}).get('allowed_tools', [])
        if tool_name not in allowed_tools:
            issues.append(f"Инструмент {tool_name} не разрешен")
        
        # Проверка количества аргументов
        max_args = 10  # Заглушка
        if len(arguments) > max_args:
            issues.append(f"Слишком много аргументов: {len(arguments)}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "tool_name": tool_name,
            "args_count": len(arguments)
        }


# Глобальный экземпляр валидатора
guardrails_validator = GuardrailsValidator()


def get_guardrails_validator() -> GuardrailsValidator:
    """Получить глобальный экземпляр валидатора Guardrails"""
    return guardrails_validator


def is_guardrails_enabled() -> bool:
    """Проверить, включены ли Guardrails"""
    return guardrails_validator.enabled


def validate_llm_input(text: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Валидация входящего текста для LLM"""
    return guardrails_validator.validate_input(text, user_id)


def validate_llm_output(response: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация исходящего ответа от LLM"""
    return guardrails_validator.validate_output(response)


def validate_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация вызова инструмента"""
    return guardrails_validator.validate_tool_call(tool_name, arguments)


# Декоратор для автоматической валидации
def with_guardrails(func):
    """Декоратор для автоматической валидации входящих и исходящих данных"""
    def wrapper(*args, **kwargs):
        if not is_guardrails_enabled():
            return func(*args, **kwargs)
        
        # Валидация входящих данных
        if args and hasattr(args[0], 'content'):
            # FastAPI request object
            input_validation = validate_llm_input(args[0].content)
            if not input_validation["valid"]:
                logger.warning(f"❌ Валидация входящих данных не прошла: {input_validation['issues']}")
                from fastapi import HTTPException
                raise HTTPException(status_code=422, detail=f"Валидация не прошла: {input_validation['issues']}")
        elif args and isinstance(args[0], str):
            # String input
            input_validation = validate_llm_input(args[0])
            if not input_validation["valid"]:
                logger.warning(f"❌ Валидация входящих данных не прошла: {input_validation['issues']}")
                raise ValueError(f"Валидация входящих данных не прошла: {input_validation['issues']}")
        
        # Выполнение функции
        result = func(*args, **kwargs)
        
        # Валидация исходящих данных
        if isinstance(result, dict):
            output_validation = validate_llm_output(result)
            if not output_validation["valid"]:
                logger.warning(f"❌ Валидация исходящих данных не прошла: {output_validation['issues']}")
                raise ValueError(f"Валидация исходящих данных не прошла: {output_validation['issues']}")
        
        return result
    
    return wrapper 