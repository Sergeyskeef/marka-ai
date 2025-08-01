#!/usr/bin/env python3
"""
Tool Registry v1 - система регистрации и управления инструментами
"""

import json
import logging
import inspect
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ToolDefinition:
    """Определение инструмента"""
    name: str
    description: str
    function: Callable
    args_schema: Dict[str, Any]
    category: str = "general"
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для сохранения"""
        return {
            "name": self.name,
            "description": self.description,
            "args_schema": self.args_schema,
            "category": self.category,
            "tags": self.tags,
            "function_name": self.function.__name__,
            "module": self.function.__module__
        }

class ToolRegistry:
    """Реестр инструментов"""
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.categories: Dict[str, List[str]] = {}
        logger.info("🔧 ToolRegistry инициализирован")
    
    def register_tool(self, tool_def: ToolDefinition) -> bool:
        """Регистрирует инструмент"""
        try:
            self.tools[tool_def.name] = tool_def
            
            # Добавляем в категорию
            if tool_def.category not in self.categories:
                self.categories[tool_def.category] = []
            self.categories[tool_def.category].append(tool_def.name)
            
            logger.info(f"✅ Зарегистрирован инструмент: {tool_def.name} ({tool_def.category})")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации инструмента {tool_def.name}: {e}")
            return False
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Получает инструмент по имени"""
        return self.tools.get(name)
    
    def list_tools(self, category: Optional[str] = None) -> List[ToolDefinition]:
        """Список инструментов"""
        if category:
            tool_names = self.categories.get(category, [])
            return [self.tools[name] for name in tool_names if name in self.tools]
        return list(self.tools.values())
    
    def get_tools_dict(self) -> List[Dict[str, Any]]:
        """Возвращает список инструментов в виде словарей"""
        return [tool.to_dict() for tool in self.tools.values()]

# Глобальный экземпляр реестра
tool_registry = ToolRegistry()

def tool(name: str, description: str, category: str = "general", tags: List[str] = None):
    """Декоратор для регистрации инструментов"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Анализируем сигнатуру функции
        sig = inspect.signature(func)
        args_schema = {}
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            param_info = {
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any",
                "required": param.default == inspect.Parameter.empty,
                "default": param.default if param.default != inspect.Parameter.empty else None
            }
            args_schema[param_name] = param_info
        
        # Создаем определение инструмента
        tool_def = ToolDefinition(
            name=name,
            description=description,
            function=func,
            args_schema=args_schema,
            category=category,
            tags=tags or []
        )
        
        # Регистрируем инструмент
        tool_registry.register_tool(tool_def)
        
        return wrapper
    return decorator

# Примеры инструментов
@tool(
    name="run_code",
    description="Выполняет Python код в безопасной песочнице",
    category="code",
    tags=["execution", "sandbox"]
)
def run_code(code: str, timeout: int = 30) -> Dict[str, Any]:
    """Выполняет код в песочнице"""
    import subprocess
    import tempfile
    import os
    import time
    
    start_time = time.time()
    
    # Предварительная обработка кода
    processed_code = _preprocess_code(code)
    
    try:
        # Создаем временный файл для кода
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(processed_code)
            temp_file = f.name
        
        # Выполняем код в песочнице
        result = subprocess.run(
            ['python', temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd='/sandbox'  # Рабочая директория песочницы
        )
        
        execution_time = time.time() - start_time
        
        # Собираем вывод
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        # Формируем результат
        if stdout and stderr:
            output = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
        elif stdout:
            output = stdout
        elif stderr:
            output = f"STDERR:\n{stderr}"
        else:
            output = "(пусто)"
        
        # Очищаем временный файл
        try:
            os.unlink(temp_file)
        except:
            pass
        
        return {
            "success": result.returncode == 0,
            "output": output,
            "execution_time": execution_time,
            "returncode": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": f"❌ Превышено время выполнения ({timeout} сек)",
            "execution_time": timeout,
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "output": f"❌ Ошибка выполнения: {str(e)}",
            "execution_time": time.time() - start_time,
            "returncode": -1
        }

@tool(
    name="search_memory",
    description="Ищет информацию в памяти Graphiti",
    category="memory",
    tags=["search", "graphiti"]
)
def search_memory(query: str, limit: int = 5) -> Dict[str, Any]:
    """Поиск в памяти"""
    return {
        "query": query,
        "results": [],
        "total": 0
    }

def get_tools_for_agent() -> List[Dict[str, Any]]:
    """Возвращает список инструментов для агента"""
    return tool_registry.get_tools_dict()

def _preprocess_code(code: str) -> str:
    """Предварительная обработка кода для исправления распространенных ошибок"""
    # Заменяем символы умножения и деления
    code = code.replace('×', '*')
    code = code.replace('÷', '/')
    code = code.replace('−', '-')  # длинное тире на обычный минус
    
    # Заменяем кавычки на стандартные
    code = code.replace('"', '"').replace('"', '"')
    code = code.replace(''', "'").replace(''', "'")
    
    # Исправляем print без скобок (для Python 2 совместимости)
    if 'print ' in code and '(' not in code.split('print ')[1][:10]:
        # Это сложная логика, лучше оставить как есть
        pass
    
    return code 