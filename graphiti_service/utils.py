#!/usr/bin/env python3
"""
Утилиты для GraphitiMemory
"""

import json
import logging
from typing import Any, Union

logger = logging.getLogger(__name__)

def safe_serialize(value: Any) -> str:
    """Безопасная сериализация значения в JSON строку"""
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Ошибка сериализации {value}: {e}")
            return str(value)
    return str(value)

def safe_deserialize(value: Union[str, Any]) -> Any:
    """Безопасная десериализация JSON строки"""
    if not isinstance(value, str):
        return value
    
    # Проверяем, является ли строка JSON
    if value.startswith('[') or value.startswith('{'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"Ошибка десериализации JSON: {value}")
            return value
    
    return value

def process_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Обработка свойств узла: сериализация списков и словарей"""
    processed = {}
    
    for key, value in properties.items():
        if value is None:
            continue
            
        if isinstance(value, (list, dict)):
            processed[key] = safe_serialize(value)
        else:
            processed[key] = value
    
    return processed

def restore_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Восстановление свойств узла: десериализация JSON строк"""
    restored = {}
    
    for key, value in properties.items():
        if value is None:
            continue
            
        restored[key] = safe_deserialize(value)
    
    return restored 