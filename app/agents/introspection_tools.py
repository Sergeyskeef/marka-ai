"""
Инструменты интроспекции для самоосознания агента
"""

import json
import inspect
import os
from typing import Dict, List, Any, Optional
from pathlib import Path
import ast
import logging

from .tools import create_openai_tool
from ..config import settings

logger = logging.getLogger(__name__)


@create_openai_tool
async def analyze_my_capabilities() -> str:
    """
    Анализирует собственные возможности и инструменты агента.
    Возвращает детальную информацию о доступных функциях, их назначении и ограничениях.
    """
    try:
        # Импортируем все модули с инструментами
        from . import (
            memory_tools, 
            advanced_memory_tools,
            vector_search_tools,
            learning_tools,
            file_tools,
            test_tools,
            code_analysis_tools,
            dependency_tools
        )
        
        capabilities = {
            "tools": {},
            "limitations": [],
            "recommendations": []
        }
        
        # Анализируем каждый модуль
        tool_modules = [
            ("Память", memory_tools),
            ("Продвинутая память", advanced_memory_tools),
            ("Векторный поиск", vector_search_tools),
            ("Обучение", learning_tools),
            ("Работа с файлами", file_tools),
            ("Тестирование", test_tools),
            ("Анализ кода", code_analysis_tools),
            ("Управление зависимостями", dependency_tools)
        ]
        
        for category, module in tool_modules:
            capabilities["tools"][category] = []
            
            # Ищем все функции с декоратором @create_openai_tool
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) and hasattr(obj, '__wrapped__'):
                    doc = inspect.getdoc(obj) or "Нет описания"
                    sig = inspect.signature(obj)
                    
                    capabilities["tools"][category].append({
                        "name": name,
                        "description": doc.split('\n')[0],
                        "parameters": [
                            {
                                "name": param,
                                "type": str(sig.parameters[param].annotation),
                                "required": sig.parameters[param].default == inspect.Parameter.empty
                            }
                            for param in sig.parameters
                            if param not in ['self', 'cls']
                        ]
                    })
        
        # Анализируем ограничения
        capabilities["limitations"] = [
            "Доступ к файлам ограничен безопасными директориями (/workspace, /app, /sandbox)",
            "Песочница изолирована от основной системы",
            "Нет инструментов для работы с Git",
            "Ограниченное время выполнения команд (30 сек)",
            "Нет персистентного состояния между вызовами"
        ]
        
        # Даем рекомендации
        capabilities["recommendations"] = [
            "Рекомендуется использовать coverage для отслеживания покрытия тестами",
            "Используйте анализ кода для поддержания качества и выявления проблем",
            "Регулярно проверяйте зависимости на уязвимости безопасности"
        ]
        
        return json.dumps(capabilities, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка анализа возможностей: {e}")
        return f"Ошибка анализа: {str(e)}"


@create_openai_tool
async def can_i_do_this(task_description: str) -> str:
    """
    Анализирует, может ли агент выполнить конкретную задачу.
    Возвращает оценку возможности выполнения и что для этого нужно.
    
    Args:
        task_description: Описание задачи, которую нужно выполнить
    """
    # Ключевые слова для определения типа задачи
    task_keywords = {
        "файл": ["читать", "создать", "изменить", "открыть", "сохранить"],
        "код": ["написать", "исправить", "рефакторинг", "анализ", "проверить"],
        "тест": ["запустить", "pytest", "тестировать", "покрытие"],
        "git": ["коммит", "ветка", "push", "pull", "merge"],
        "память": ["запомнить", "найти", "поиск", "сохранить"],
        "обучение": ["научиться", "улучшить", "анализ ошибок"]
    }
    
    task_lower = task_description.lower()
    capabilities_status = {
        "can_do_fully": [],
        "can_do_partially": [],
        "cannot_do": [],
        "need_tools": []
    }
    
    # Анализируем задачу
    for category, keywords in task_keywords.items():
        if any(keyword in task_lower for keyword in keywords):
            if category == "память":
                capabilities_status["can_do_fully"].append(
                    "✅ Могу работать с памятью: сохранять, искать, анализировать"
                )
            elif category == "обучение":
                capabilities_status["can_do_fully"].append(
                    "✅ Могу обучаться на основе опыта через REAP цикл"
                )
            elif category == "файл":
                capabilities_status["can_do_fully"].append(
                    "✅ Могу работать с файлами: читать, писать, искать, удалять"
                )
                capabilities_status["can_do_fully"].append(
                    "✅ Поддерживаю: чтение по строкам, поиск по регулярным выражениям, информация о файлах"
                )
            elif category == "код":
                capabilities_status["can_do_fully"].append(
                    "✅ Могу выполнять код в песочнице и работать с файлами проекта"
                )
                capabilities_status["can_do_fully"].append(
                    "✅ Могу читать, анализировать и находить проблемы в коде Python"
                )
                capabilities_status["can_do_fully"].append(
                    "✅ Могу анализировать импорты, зависимости, сложность и метрики кода"
                )
            elif category == "тест":
                capabilities_status["can_do_fully"].append(
                    "✅ Могу запускать тесты pytest и unittest"
                )
                capabilities_status["can_do_fully"].append(
                    "✅ Могу создавать шаблоны тестов, анализировать покрытие, тестировать отдельные функции"
                )
            elif category == "git":
                capabilities_status["cannot_do"].append(
                    "❌ Не могу работать с Git"
                )
                capabilities_status["need_tools"].append(
                    "Нужны инструменты Git (не планируется в ближайшее время)"
                )
            elif category == "pip" or category == "пакет" or category == "установ" or category == "зависимост":
                capabilities_status["can_do_fully"].append(
                    "✅ Могу управлять Python пакетами через pip"
                )
                capabilities_status["can_do_fully"].append(
                    "✅ Могу анализировать зависимости, проверять безопасность, генерировать requirements"
                )
    
    # Формируем ответ
    response = f"📋 Анализ задачи: {task_description}\n\n"
    
    if capabilities_status["can_do_fully"]:
        response += "✅ **Могу выполнить полностью:**\n"
        response += "\n".join(capabilities_status["can_do_fully"]) + "\n\n"
    
    if capabilities_status["can_do_partially"]:
        response += "⚠️ **Могу выполнить частично:**\n"
        response += "\n".join(capabilities_status["can_do_partially"]) + "\n\n"
    
    if capabilities_status["cannot_do"]:
        response += "❌ **Не могу выполнить:**\n"
        response += "\n".join(capabilities_status["cannot_do"]) + "\n\n"
    
    if capabilities_status["need_tools"]:
        response += "🔧 **Что нужно для выполнения:**\n"
        response += "\n".join(capabilities_status["need_tools"]) + "\n\n"
    
    # Общая оценка
    if capabilities_status["can_do_fully"] and not capabilities_status["cannot_do"]:
        response += "✅ **Вывод:** Могу выполнить эту задачу!"
    elif capabilities_status["can_do_partially"] or (capabilities_status["can_do_fully"] and capabilities_status["cannot_do"]):
        response += "⚠️ **Вывод:** Могу выполнить задачу частично. Для полного выполнения нужны дополнительные инструменты."
    else:
        response += "❌ **Вывод:** Пока не могу выполнить эту задачу. Нужны новые инструменты."
    
    return response


@create_openai_tool  
async def analyze_my_structure() -> str:
    """
    Анализирует внутреннюю структуру агента: модули, файлы, зависимости.
    Возвращает детальную карту архитектуры системы.
    """
    try:
        project_root = Path("/workspace")
        structure = {
            "core_modules": {},
            "agent_tools": {},
            "services": {},
            "configuration": {},
            "dependencies": []
        }
        
        # Анализируем структуру app/agents
        agents_dir = project_root / "app" / "agents"
        if agents_dir.exists():
            structure["agent_tools"] = {
                "files": [],
                "total_functions": 0,
                "categories": {}
            }
            
            for file in agents_dir.glob("*.py"):
                if file.name == "__init__.py":
                    continue
                    
                file_info = {
                    "name": file.name,
                    "size": file.stat().st_size,
                    "functions": []
                }
                
                # Парсим AST для поиска функций
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        tree = ast.parse(f.read())
                        
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            file_info["functions"].append(node.name)
                            structure["agent_tools"]["total_functions"] += 1
                            
                except Exception as e:
                    logger.error(f"Ошибка парсинга {file}: {e}")
                
                structure["agent_tools"]["files"].append(file_info)
                
                # Категоризация
                category = file.stem.replace("_tools", "")
                structure["agent_tools"]["categories"][category] = len(file_info["functions"])
        
        # Анализируем core модули
        core_dirs = ["memory", "learning", "sandbox", "utils"]
        for dir_name in core_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                structure["core_modules"][dir_name] = {
                    "files": len(list(dir_path.glob("*.py"))),
                    "has_tests": (project_root / "tests" / dir_name).exists()
                }
        
        # Анализируем сервисы
        services = {
            "FastAPI": "main.py",
            "Telegram Bot": "telegram_bot/",
            "Graphiti": "graphiti_service/",
            "Neo4j": "docker-compose.yml"
        }
        
        for service, path in services.items():
            full_path = project_root / path
            structure["services"][service] = {
                "exists": full_path.exists(),
                "type": "file" if path.endswith(".py") else "directory"
            }
        
        # Конфигурация
        config_files = [".env", "docker-compose.yml", "requirements.txt", "pyproject.toml"]
        for config in config_files:
            path = project_root / config
            structure["configuration"][config] = path.exists()
        
        # Зависимости из requirements.txt
        req_file = project_root / "requirements.txt"
        if req_file.exists():
            with open(req_file, 'r') as f:
                deps = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                structure["dependencies"] = deps[:10]  # Топ 10
        
        return json.dumps(structure, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка анализа структуры: {e}")
        return f"Ошибка анализа: {str(e)}"


@create_openai_tool
async def what_am_i_learning() -> str:
    """
    Показывает текущий прогресс обучения и что агент узнал нового.
    Анализирует память и историю обучения.
    """
    try:
        from ..learning.reap_cycle import REAPCycle
        from ..memory.advanced_memory_adapter import AdvancedMemoryAdapter
        
        # Инициализируем компоненты
        memory = AdvancedMemoryAdapter()
        reap = REAPCycle(memory)
        
        learning_status = {
            "recent_lessons": [],
            "skills_developed": [],
            "error_patterns": [],
            "success_patterns": [],
            "memory_stats": {}
        }
        
        # Получаем статистику памяти
        stats = await memory.get_memory_stats()
        learning_status["memory_stats"] = {
            "total_facts": stats.get("facts", 0),
            "total_episodes": stats.get("episodes", 0),
            "total_skills": stats.get("skills", 0),
            "connections": stats.get("total_edges", 0)
        }
        
        # Анализируем недавние эпизоды обучения
        recent_episodes = await memory.search(
            "обучение OR улучшение OR ошибка OR успех",
            limit=10,
            episode_types=["learning", "error", "success"]
        )
        
        for episode in recent_episodes.get("results", []):
            learning_status["recent_lessons"].append({
                "type": episode.get("metadata", {}).get("type", "unknown"),
                "lesson": episode.get("text", "")[:100] + "...",
                "timestamp": episode.get("metadata", {}).get("timestamp", "unknown")
            })
        
        # Поиск навыков
        skills = await memory.search(
            "навык OR умение OR способность",
            limit=5,
            node_types=["skill"]
        )
        
        for skill in skills.get("results", []):
            learning_status["skills_developed"].append(
                skill.get("text", "Неизвестный навык")[:100]
            )
        
        return json.dumps(learning_status, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка анализа обучения: {e}")
        return f"Ошибка анализа: {str(e)}"


# Экспортируем инструменты
INTROSPECTION_TOOLS = [
    analyze_my_capabilities,
    can_i_do_this,
    analyze_my_structure,
    what_am_i_learning
]