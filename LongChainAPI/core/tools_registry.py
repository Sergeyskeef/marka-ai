"""
Tools Registry - система автоматического обнаружения и регистрации инструментов

Этот модуль обеспечивает:
- Автоматическое сканирование проекта для обнаружения инструментов
- Создание реестра инструментов с метаданными
- API для получения списка доступных инструментов
- Интеграцию с LLM для предоставления инструментов
"""

import ast
import json
import logging
import os
import re
from functools import wraps
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы для Markdown"""
    # Символы, которые нужно экранировать в Markdown V2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    pattern = '[' + re.escape(escape_chars) + ']'
    return re.sub(pattern, r'\\\g<0>', text)


# Глобальный реестр для декоратора
_global_registry = None


def register_tool(name: str = None, description: str = "", tags: list[str] = None, priority: float = 0.5):
    """
    Декоратор для регистрации функции как инструмента.
    
    Args:
        name: Имя инструмента (по умолчанию имя функции)
        description: Описание инструмента
        tags: Теги для категоризации
        priority: Приоритет инструмента (0-1)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Добавляем метаданные к функции
        tool_name = name or func.__name__
        wrapper._tool_metadata = {
            'name': tool_name,
            'description': description or func.__doc__ or "",
            'tags': tags or [],
            'priority': priority,
            'function': func
        }
        
        # Регистрируем в глобальном реестре, если он инициализирован
        global _global_registry
        if _global_registry:
            _global_registry.register_function_tool(wrapper)
        
        return wrapper
    return decorator


@dataclass
class ToolMetadata:
    """Метаданные инструмента"""
    name: str
    type: str  # 'script', 'function', 'class', 'service'
    description: str
    file_path: str
    line_number: int | None = None
    parameters: dict[str, Any] | None = None
    return_type: str | None = None
    dependencies: list[str] | None = None
    tags: list[str] | None = None
    priority: float = 0.5
    is_available: bool = True
    last_updated: datetime | None = None


class ToolsRegistry:
    """Реестр инструментов с автоматическим обнаружением"""

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.getcwd()
        self.tools: dict[str, ToolMetadata] = {}
        self.scan_directories = [
            'scripts',
            'utils',
            'services',
            'core',
            'sandbox'
        ]
        self.ignored_patterns = [
            '__pycache__',
            '.git',
            'tests',
            '*.pyc',
            '*.pyo'
        ]
        
        # Устанавливаем глобальный реестр
        global _global_registry
        _global_registry = self

    def scan_project(self) -> dict[str, ToolMetadata]:
        """Сканирует проект и обнаруживает все инструменты"""
        logger.info("Начинаю сканирование проекта для обнаружения инструментов")

        discovered_tools = {}

        for directory in self.scan_directories:
            dir_path = os.path.join(self.project_root, directory)
            if os.path.exists(dir_path):
                logger.info(f"Сканирую директорию: {directory}")
                tools = self._scan_directory(dir_path, directory)
                discovered_tools.update(tools)

        self.tools = discovered_tools
        logger.info(f"Обнаружено {len(discovered_tools)} инструментов")
        return discovered_tools

    def _scan_directory(self, dir_path: str, dir_name: str) -> dict[str, ToolMetadata]:
        """Сканирует конкретную директорию"""
        tools = {}

        for root, dirs, files in os.walk(dir_path):
            # Исключаем игнорируемые директории
            dirs[:] = [d for d in dirs if not any(pattern in d for pattern in self.ignored_patterns)]

            for file in files:
                if file.endswith('.py') and not any(pattern in file for pattern in self.ignored_patterns):
                    file_path = os.path.join(root, file)
                    file_tools = self._analyze_python_file(file_path, dir_name)
                    tools.update(file_tools)

        return tools

    def _analyze_python_file(self, file_path: str, dir_name: str) -> dict[str, ToolMetadata]:
        """Анализирует Python файл и извлекает инструменты"""
        tools = {}

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)

            # Анализируем функции
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    tool = self._extract_function_metadata(node, file_path, dir_name)
                    if tool:
                        tools[tool.name] = tool

                elif isinstance(node, ast.ClassDef):
                    tool = self._extract_class_metadata(node, file_path, dir_name)
                    if tool:
                        tools[tool.name] = tool

            # Проверяем, является ли файл скриптом
            if self._is_script_file(file_path, content):
                script_tool = self._extract_script_metadata(file_path, dir_name)
                if script_tool:
                    tools[script_tool.name] = script_tool

        except Exception as e:
            logger.warning(f"Ошибка при анализе файла {file_path}: {e}")

        return tools

    def _extract_function_metadata(self, node: ast.FunctionDef, file_path: str, dir_name: str) -> ToolMetadata | None:
        """Извлекает метаданные функции"""
        # Пропускаем приватные функции
        if node.name.startswith('_'):
            return None

        # Извлекаем docstring
        docstring = ast.get_docstring(node) or f"Функция {node.name}"

        # Анализируем параметры
        parameters = {}
        for arg in node.args.args:
            if arg.arg != 'self':
                parameters[arg.arg] = 'Any'

        # Определяем тип инструмента
        tool_type = 'function'
        if dir_name == 'scripts':
            tool_type = 'script_function'
        elif dir_name == 'services':
            tool_type = 'service_function'
        elif dir_name == 'utils':
            tool_type = 'utility_function'

        return ToolMetadata(
            name=node.name,
            type=tool_type,
            description=docstring,
            file_path=file_path,
            line_number=node.lineno,
            parameters=parameters,
            tags=[dir_name, 'function'],
            last_updated=datetime.now()
        )

    def _extract_class_metadata(self, node: ast.ClassDef, file_path: str, dir_name: str) -> ToolMetadata | None:
        """Извлекает метаданные класса"""
        # Пропускаем приватные классы
        if node.name.startswith('_'):
            return None

        # Извлекаем docstring
        docstring = ast.get_docstring(node) or f"Класс {node.name}"

        # Определяем тип инструмента
        tool_type = 'class'
        if dir_name == 'services':
            tool_type = 'service_class'
        elif dir_name == 'core':
            tool_type = 'core_class'

        return ToolMetadata(
            name=node.name,
            type=tool_type,
            description=docstring,
            file_path=file_path,
            line_number=node.lineno,
            tags=[dir_name, 'class'],
            last_updated=datetime.now()
        )

    def _is_script_file(self, file_path: str, content: str) -> bool:
        """Проверяет, является ли файл исполняемым скриптом"""
        os.path.basename(file_path)

        # Проверяем наличие shebang или main блока
        has_shebang = content.startswith('#!')
        # Ищем main блок с разными вариантами кавычек
        has_main = ('if __name__ == "__main__"' in content or
                   "if __name__ == '__main__'" in content)

        # Проверяем, что файл находится в директории scripts
        is_in_scripts = 'scripts' in file_path

        return (has_shebang or has_main) and is_in_scripts

    def _extract_script_metadata(self, file_path: str, dir_name: str) -> ToolMetadata | None:
        """Извлекает метаданные скрипта"""
        filename = os.path.basename(file_path)
        name = os.path.splitext(filename)[0]

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            # Ищем docstring в начале файла
            lines = content.split('\n')
            description = f"Скрипт {name}"

            for line in lines[:10]:  # Проверяем первые 10 строк
                if line.strip().startswith('"""') or line.strip().startswith("'''"):
                    description = line.strip().strip('"\'')
                    break
                elif line.strip().startswith('#'):
                    description = line.strip('# ').strip()
                    break

            return ToolMetadata(
                name=name,
                type='script',
                description=description,
                file_path=file_path,
                tags=[dir_name, 'script'],
                priority=0.8,  # Скрипты имеют высокий приоритет
                last_updated=datetime.now()
            )

        except Exception as e:
            logger.warning(f"Ошибка при анализе скрипта {file_path}: {e}")
            return None

    def get_tools(self, tool_type: str | None = None, tags: list[str] | None = None) -> list[ToolMetadata]:
        """Возвращает список инструментов с фильтрацией"""
        tools = list(self.tools.values())

        if tool_type:
            tools = [t for t in tools if t.type == tool_type]

        if tags:
            tools = [t for t in tools if any(tag in (t.tags or []) for tag in tags)]

        return sorted(tools, key=lambda x: x.priority, reverse=True)

    def get_tool(self, name: str) -> ToolMetadata | None:
        """Возвращает конкретный инструмент по имени"""
        return self.tools.get(name)

    def update_tool(self, name: str, **kwargs) -> bool:
        """Обновляет метаданные инструмента"""
        if name not in self.tools:
            return False

        tool = self.tools[name]
        for key, value in kwargs.items():
            if hasattr(tool, key):
                setattr(tool, key, value)

        tool.last_updated = datetime.now()
        return True

    def add_tool(self, tool: ToolMetadata) -> None:
        """Добавляет новый инструмент в реестр"""
        self.tools[tool.name] = tool

    def remove_tool(self, name: str) -> bool:
        """Удаляет инструмент из реестра"""
        if name in self.tools:
            del self.tools[name]
            return True
        return False

    def export_tools(self) -> dict[str, Any]:
        """Экспортирует реестр инструментов в словарь"""
        return {
            'tools': {name: asdict(tool) for name, tool in self.tools.items()},
            'total_count': len(self.tools),
            'last_scan': datetime.now().isoformat()
        }

    def register_function_tool(self, func: Callable) -> None:
        """Регистрирует функцию как инструмент"""
        if hasattr(func, '_tool_metadata'):
            metadata = func._tool_metadata
            tool = ToolMetadata(
                name=metadata['name'],
                type='function',
                description=metadata['description'],
                file_path=func.__module__,
                tags=metadata['tags'],
                priority=metadata['priority'],
                is_available=True,
                last_updated=datetime.now()
            )
            self.tools[tool.name] = tool
            logger.info(f"Зарегистрирована функция-инструмент: {tool.name}")

    def get_tools_for_llm(self) -> list[dict[str, Any]]:
        """Возвращает инструменты в формате для LLM"""
        llm_tools = []

        for tool in self.tools.values():
            if not tool.is_available:
                continue

            llm_tool = {
                'name': tool.name,
                'type': tool.type,
                'description': tool.description,
                'file_path': tool.file_path,
                'tags': tool.tags or [],
                'priority': tool.priority
            }

            if tool.parameters:
                llm_tool['parameters'] = tool.parameters

            llm_tools.append(llm_tool)

        return sorted(llm_tools, key=lambda x: x['priority'], reverse=True)
    
    def export_openai_functions(self) -> list[dict[str, Any]]:
        """
        Экспортирует инструменты в формате OpenAI Function Calling.
        
        Returns:
            Список функций в формате OpenAI
        """
        functions = []
        
        for tool in self.tools.values():
            if not tool.is_available or tool.type not in ['function', 'script']:
                continue
            
            # Экранируем описание для Markdown
            description = escape_markdown(tool.description)
            
            function_spec = {
                "name": tool.name.replace('-', '_').replace(' ', '_'),
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            
            # Добавляем параметры если есть
            if tool.parameters:
                for param_name, param_info in tool.parameters.items():
                    # Параметр может быть строкой или словарем
                    if isinstance(param_info, str):
                        # Простой тип без дополнительной информации
                        json_type = self._python_to_json_type(param_info)
                        function_spec["parameters"]["properties"][param_name] = {
                            "type": json_type,
                            "description": ""
                        }
                    else:
                        # Словарь с полной информацией
                        param_type = param_info.get('type', 'string')
                        param_desc = param_info.get('description', '')
                        
                        # Конвертируем Python типы в JSON Schema типы
                        json_type = self._python_to_json_type(param_type)
                        
                        function_spec["parameters"]["properties"][param_name] = {
                            "type": json_type,
                            "description": escape_markdown(param_desc)
                        }
                        
                        if param_info.get('required', False):
                            function_spec["parameters"]["required"].append(param_name)
            
            functions.append(function_spec)
        
        return functions
    
    def _python_to_json_type(self, python_type: str) -> str:
        """Конвертирует Python тип в JSON Schema тип"""
        type_mapping = {
            'str': 'string',
            'int': 'integer',
            'float': 'number',
            'bool': 'boolean',
            'list': 'array',
            'dict': 'object',
            'Any': 'string'
        }
        return type_mapping.get(python_type, 'string')

    def refresh(self) -> dict[str, ToolMetadata]:
        """Обновляет реестр инструментов"""
        logger.info("Обновляю реестр инструментов")
        return self.scan_project()

    def get_tools_status(self) -> dict[str, Any]:
        """
        Получение статуса инструментов.

        Returns:
            Словарь со статусом инструментов
        """
        status = {
            'total_tools': len(self.tools),
            'available_tools': len([t for t in self.tools.values() if t.is_available]),
            'tools_by_type': {},
            'tools_by_directory': {},
            'recently_updated': [],
            'high_priority_tools': []
        }

        # Группируем по типам
        for tool in self.tools.values():
            tool_type = tool.type
            if tool_type not in status['tools_by_type']:
                status['tools_by_type'][tool_type] = 0
            status['tools_by_type'][tool_type] += 1

            # Группируем по директориям
            dir_name = os.path.dirname(tool.file_path).split('/')[-1]
            if dir_name not in status['tools_by_directory']:
                status['tools_by_directory'][dir_name] = 0
            status['tools_by_directory'][dir_name] += 1

            # Высокоприоритетные инструменты
            if tool.priority > 0.8:
                status['high_priority_tools'].append({
                    'name': tool.name,
                    'type': tool.type,
                    'priority': tool.priority,
                    'description': tool.description[:100] + '...' if len(tool.description) > 100 else tool.description
                })

            # Недавно обновленные
            if tool.last_updated:
                from datetime import datetime, timedelta
                if tool.last_updated > datetime.now() - timedelta(hours=24):
                    status['recently_updated'].append({
                        'name': tool.name,
                        'type': tool.type,
                        'last_updated': tool.last_updated.isoformat()
                    })

        return status

    def get_tools_summary(self) -> dict[str, list[dict[str, str]]]:
        """
        Получение краткой сводки инструментов для Telegram бота.

        Returns:
            Словарь с группировкой инструментов по категориям
        """
        # Сначала сканируем проект, если инструменты не загружены
        if not self.tools:
            self.scan_project()

        summary = {}

        # Группируем инструменты по типам/категориям
        for tool in self.tools.values():
            if not tool.is_available:
                continue

            # Определяем категорию на основе типа и тегов
            category = self._get_tool_category(tool)

            if category not in summary:
                summary[category] = []

            summary[category].append({
                'name': tool.name,
                'description': tool.description[:100] + '...' if len(tool.description) > 100 else tool.description,
                'type': tool.type,
                'file_path': tool.file_path
            })

        # Сортируем инструменты в каждой категории по приоритету
        for category in summary:
            summary[category] = sorted(summary[category], key=lambda x: x['name'])

        return summary

    def _get_tool_category(self, tool: ToolMetadata) -> str:
        """Определяет категорию инструмента"""
        if 'scripts' in (tool.tags or []) or tool.type == 'script':
            return 'Скрипты'
        elif 'services' in (tool.tags or []) or 'service' in tool.type:
            return 'Сервисы'
        elif 'core' in (tool.tags or []) or 'core' in tool.type:
            return 'Ядро системы'
        elif 'utils' in (tool.tags or []) or 'utility' in tool.type:
            return 'Утилиты'
        elif 'sandbox' in (tool.tags or []):
            return 'Песочница'
        elif tool.type == 'function':
            return 'Функции'
        elif tool.type == 'class':
            return 'Классы'
        else:
            return 'Прочие'


# Глобальный экземпляр реестра
tools_registry = ToolsRegistry()


def get_tools_registry() -> ToolsRegistry:
    """Возвращает глобальный экземпляр реестра инструментов"""
    return tools_registry


def scan_and_register_tools() -> dict[str, ToolMetadata]:
    """Сканирует проект и регистрирует инструменты"""
    registry = get_tools_registry()
    return registry.scan_project()


def get_available_tools(tool_type: str | None = None, tags: list[str] | None = None) -> list[ToolMetadata]:
    """Возвращает доступные инструменты"""
    registry = get_tools_registry()
    return registry.get_tools(tool_type, tags)


def get_tools_for_llm() -> list[dict[str, Any]]:
    """Возвращает инструменты в формате для LLM"""
    registry = get_tools_registry()
    return registry.get_tools_for_llm()
