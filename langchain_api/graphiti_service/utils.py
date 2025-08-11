"""
Утилиты для сериализации данных в Neo4j
"""

import json
from typing import Any, Dict
from datetime import datetime


def process_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обрабатывает свойства для сохранения в Neo4j.
    Преобразует сложные типы в строки JSON.
    """
    processed = {}
    
    for key, value in props.items():
        if value is None:
            continue
            
        # Обработка datetime
        if isinstance(value, datetime):
            processed[key] = value.isoformat()
        # Обработка сложных типов (dict, list)
        elif isinstance(value, (dict, list)):
            processed[key] = json.dumps(value, ensure_ascii=False)
        # Обработка булевых значений
        elif isinstance(value, bool):
            processed[key] = value
        # Обработка чисел
        elif isinstance(value, (int, float)):
            processed[key] = value
        # Все остальное как строки
        else:
            processed[key] = str(value)
    
    return processed


def restore_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Восстанавливает свойства из Neo4j.
    Преобразует JSON строки обратно в объекты.
    """
    restored = {}
    
    for key, value in props.items():
        if value is None:
            restored[key] = None
            continue
            
        # Попытка десериализации JSON
        if isinstance(value, str):
            # Проверяем, похоже ли на JSON
            if value.startswith('{') or value.startswith('['):
                try:
                    restored[key] = json.loads(value)
                except json.JSONDecodeError:
                    restored[key] = value
            # Проверяем, похоже ли на datetime
            elif 'T' in value and (value.endswith('Z') or '+' in value or value.count(':') >= 2):
                try:
                    restored[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    restored[key] = value
            else:
                restored[key] = value
        else:
            restored[key] = value
    
    return restored