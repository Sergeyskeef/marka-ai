"""
Система инструментов для OpenAI Agents SDK
"""

import inspect
import json
from typing import Callable, Dict, Any, List, get_type_hints, get_args, get_origin, Union
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def create_openai_tool(func: Callable) -> Dict[str, Any]:
    """
    Декоратор для преобразования функции в OpenAI tool
    
    Автоматически извлекает:
    - Имя функции
    - Описание из docstring
    - Параметры с типами
    - Обязательные параметры
    
    Example:
        @create_openai_tool
        async def search_memory(query: str, limit: int = 5) -> str:
            '''Поиск информации в памяти агента'''
            return "результаты поиска"
    """
    # Получаем информацию о функции
    sig = inspect.signature(func)
    docstring = inspect.getdoc(func) or "No description provided"
    
    # Извлекаем параметры
    properties = {}
    required = []
    
    # Получаем type hints
    type_hints = get_type_hints(func)
    
    for param_name, param in sig.parameters.items():
        # Пропускаем self/cls
        if param_name in ['self', 'cls']:
            continue
            
        # Определяем тип
        param_type = type_hints.get(param_name, Any)
        json_type = _python_type_to_json_type(param_type)
        
        # Создаем описание параметра
        param_info = {
            "type": json_type
        }
        
        # Добавляем описание если есть в docstring
        param_desc = _extract_param_description(docstring, param_name)
        if param_desc:
            param_info["description"] = param_desc
            
        # Для enum типов
        if hasattr(param_type, '__members__'):
            param_info["enum"] = list(param_type.__members__.keys())

        # Для массивов необходимо указать схему элементов
        if json_type == "array":
            items_schema = _get_array_items_schema(param_type)
            if items_schema:
                param_info["items"] = items_schema
            
        properties[param_name] = param_info
        
        # Проверяем обязательность
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    # Формируем определение инструмента
    tool_definition = {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": docstring.split('\n')[0],  # Первая строка docstring
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }
    
    # Добавляем атрибут к функции для удобства
    func._openai_tool_definition = tool_definition
    
    # Возвращаем саму функцию (для использования как декоратор)
    return func


def _python_type_to_json_type(python_type) -> str:
    """Преобразование Python типа в JSON Schema тип"""
    # Обработка Union типов (Optional)
    origin = get_origin(python_type)
    if origin is Union:
        args = get_args(python_type)
        # Если это Optional (Union[X, None])
        if type(None) in args:
            non_none_types = [t for t in args if t != type(None)]
            if len(non_none_types) == 1:
                return _python_type_to_json_type(non_none_types[0])
    
    # Базовые типы
    type_mapping = {
        str: "string",
        int: "integer", 
        float: "number",
        bool: "boolean",
        list: "array",
        List: "array",
        dict: "object",
        Dict: "object"
    }
    
    # Проверяем origin для generic типов
    if origin in type_mapping:
        return type_mapping[origin]
    
    # Проверяем сам тип
    if python_type in type_mapping:
        return type_mapping[python_type]
    
    # По умолчанию
    return "string"


def _unwrap_optional(python_type):
    """Возвращает базовый тип для Optional[T] (Union[T, None])."""
    origin = get_origin(python_type)
    if origin is Union:
        args = [t for t in get_args(python_type) if t is not type(None)]  # noqa: E721
        if len(args) == 1:
            return args[0]
    return python_type


def _get_array_items_schema(python_type) -> Dict[str, Any] | None:
    """Построить JSON Schema для элементов массива на основе аннотации типа.
    Примеры:
      - List[str]      -> {"type": "string"}
      - list[int]      -> {"type": "integer"}
      - List[Dict]     -> {"type": "object"}
      - Без указания   -> {"type": "string"} (безопасный дефолт)
    """
    base = _unwrap_optional(python_type)
    origin = get_origin(base)
    if origin in (list, List):
        args = get_args(base)
        if args:
            inner = args[0]
            return {"type": _python_type_to_json_type(inner)}
        # Не указан тип элементов — используем безопасный дефолт
        return {"type": "string"}
    return None


def _extract_param_description(docstring: str, param_name: str) -> str:
    """Извлечение описания параметра из docstring"""
    lines = docstring.split('\n')
    in_params = False
    
    for line in lines:
        line = line.strip()
        
        # Начало секции параметров
        if line.lower() in ['args:', 'arguments:', 'parameters:', 'params:']:
            in_params = True
            continue
            
        # Конец секции параметров
        if in_params and line and not line.startswith(' ') and ':' in line:
            in_params = False
            
        # Ищем описание параметра
        if in_params and param_name in line:
            # Форматы: "param_name: description" или "param_name (type): description"
            parts = line.split(':', 1)
            if len(parts) > 1:
                return parts[1].strip()
                
    return ""


class ToolRegistry:
    """Реестр инструментов для удобного управления"""
    
    def __init__(self):
        self.tools = {}
        self.definitions = []
        
    def register(self, func: Callable, name: str = None):
        """
        Регистрация инструмента
        
        Args:
            func: Функция-инструмент
            name: Опциональное имя (по умолчанию имя функции)
        """
        tool_name = name or func.__name__
        
        # Создаем определение если его нет
        if hasattr(func, '_openai_tool_definition'):
            definition = func._openai_tool_definition
        else:
            # Применяем декоратор и получаем определение
            func = create_openai_tool(func)
            definition = func._openai_tool_definition
            
        self.tools[tool_name] = func
        self.definitions.append(definition)
        
        logger.info(f"✅ Зарегистрирован инструмент: {tool_name}")
        
    def get_all_definitions(self) -> List[Dict[str, Any]]:
        """Получить все определения инструментов"""
        return self.definitions
        
    def get_function(self, name: str) -> Callable:
        """Получить функцию по имени"""
        return self.tools.get(name)
        
    def clear(self):
        """Очистить реестр"""
        self.tools.clear()
        self.definitions.clear()


# Глобальный реестр инструментов
tool_registry = ToolRegistry()


def register_tool(name: str = None):
    """
    Декоратор для регистрации инструмента в глобальном реестре
    
    Example:
        @register_tool()
        async def my_tool(param: str) -> str:
            return "result"
    """
    def decorator(func: Callable) -> Callable:
        # Применяем create_openai_tool если еще не применен
        if not hasattr(func, '_openai_tool_definition'):
            func = create_openai_tool(func)
        
        # Регистрируем в глобальном реестре
        tool_registry.register(func, name)
        
        return func
        
    return decorator


# Вспомогательные функции для работы с результатами
def format_tool_result(data: Any, success: bool = True) -> Dict[str, Any]:
    """
    Форматирование результата выполнения инструмента
    
    Args:
        data: Данные результата
        success: Успешность выполнения
        
    Returns:
        Отформатированный результат
    """
    if isinstance(data, dict):
        return {
            "success": success,
            **data
        }
    elif isinstance(data, str):
        return {
            "success": success,
            "result": data
        }
    else:
        return {
            "success": success,
            "result": json.dumps(data, ensure_ascii=False)
        }


def format_tool_error(error: Exception) -> Dict[str, Any]:
    """
    Форматирование ошибки выполнения инструмента
    
    Args:
        error: Исключение
        
    Returns:
        Отформатированная ошибка
    """
    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__
    }