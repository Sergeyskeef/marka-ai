#!/usr/bin/env python3
"""
Enhanced RAG Chain с интеграцией OpenAI Tools API.
Новая версия с поддержкой tool_calls для выполнения команд.
"""

import asyncio
import json
import logging

import httpx

from langchain_api.core.backend_selector import create_memory
from langchain_api.memory.multi_layer_memory import MultiLayerMemory
from langchain_api.sandbox.autonomous_development_system import (
    AutonomousDevelopmentSystem,
)
from langchain_api.sandbox.ci_pipeline import (
    get_ci_status,
    run_tests,
    validate_code_quality,
)
from langchain_api.sandbox.production_validation_system import (
    approve_validation_for_deployment,
    create_pull_request_for_changes,
    deploy_validated_changes,
    get_validation_report_safe,
    list_all_deployments,
    list_all_validations,
    monitor_deployment_status,
    rollback_deployment_safe,
    validate_changes_for_deployment,
)
from langchain_api.sandbox.self_learning_system import (
    add_feedback,
    analyze_code_quality,
    analyze_development_effectiveness,
    get_improvement_recommendations,
    record_task_performance,
    suggest_process_improvements,
)
from langchain_api.sandbox.task_planning_system import (
    create_task_plan,
    estimate_task_complexity,
    get_task_plan,
    list_task_plans,
)
from langchain_api.utils.openai_proxy_client import create_openai_client

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем клиент OpenAI
openai_client = create_openai_client(timeout=30.0)

# Определяем tools schema для OpenAI Tools API
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "execute_sandbox_command",
            "description": "Run a shell command inside the project's Docker sandbox and return stdout & stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_project_file",
            "description": "Read contents of a file from the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to project root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_list",
            "description": "Получить список всех задач в системе (выполненных, активных, отложенных) с фильтрацией по статусу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Фильтр по статусу задач: pending, running, completed, failed. Если не указан - все задачи.",
                        "enum": ["pending", "running", "completed", "failed"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search in the multi-layer memory system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run tests and return JSON report with results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_path": {
                        "type": "string",
                        "description": "Path to tests directory (default: 'tests')."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_code_quality",
            "description": "Validate code quality and return JSON report with issues and metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "string",
                        "description": "JSON array of file paths to check (optional, checks all Python files if not provided)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ci_status",
            "description": "Get current CI status and generate comprehensive report.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "develop_tool",
            "description": "Автономная разработка инструмента. Полный цикл: анализ требований → план → код → тесты → diff-отчет.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Описание задачи для разработки инструмента (например: 'echo tool', 'calculator tool', 'file operation tool')"
                    }
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_python_file",
            "description": "Create a new Python file in the sandbox with specified content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to create (relative to sandbox)."
                    },
                    "content": {
                        "type": "string",
                        "description": "Python code content for the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit an existing file by applying changes (add, replace, delete lines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit."
                    },
                    "changes": {
                        "type": "string",
                        "description": "JSON object with changes: {'add_lines': [{'line': 10, 'content': 'new line'}], 'replace_lines': [{'line': 5, 'content': 'replaced content'}], 'delete_lines': [5, 10]}"
                    }
                },
                "required": ["path", "changes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_task_requirements",
            "description": "Analyze task requirements and extract key information for implementation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description to analyze."
                    }
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "develop_feature",
            "description": "Автономная разработка новой функции. Полный цикл: анализ → план → код → тесты → валидация.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Описание функции для разработки."
                    }
                },
                "required": ["description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_requirements",
            "description": "Анализ требований к задаче с детальной декомпозицией.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Описание задачи для анализа."
                    }
                },
                "required": ["description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_implementation_plan",
            "description": "Создание детального плана реализации задачи.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Описание задачи для планирования."
                    }
                },
                "required": ["description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "auto_test_feature",
            "description": "Автоматическое тестирование функции с анализом покрытия.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_path": {
                        "type": "string",
                        "description": "Путь к тестам (по умолчанию: текущая директория)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "code_review_feature",
            "description": "Автоматический код-ревью с использованием LLM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Путь к файлу для ревью (по умолчанию: текущая директория)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_feature",
            "description": "Безопасное развертывание функции в продакшн с подтверждением.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_path": {
                        "type": "string",
                        "description": "Путь к функции для развертывания."
                    }
                },
                "required": ["feature_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_implementation_plan",
            "description": "Create a detailed implementation plan based on requirements analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements": {
                        "type": "string",
                        "description": "Requirements analysis result or task description."
                    }
                },
                "required": ["requirements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_diff_report",
            "description": "Create a diff report comparing two versions of code or files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "before": {
                        "type": "string",
                        "description": "Original code or file path."
                    },
                    "after": {
                        "type": "string",
                        "description": "Modified code or file path."
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of changes made."
                    }
                },
                "required": ["before", "after", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan_task",
            "description": "Создать детальный план выполнения задачи с декомпозицией на подзадачи.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Описание задачи для планирования."
                    }
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_task_complexity",
            "description": "Оценить сложность задачи и получить рекомендации по выполнению.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Описание задачи для оценки сложности."
                    }
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_plan",
            "description": "Получить план задачи по ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID задачи для получения плана."
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_task_plans",
            "description": "Получить список всех созданных планов задач.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_list",
            "description": "Получить список всех задач в системе (выполненных, активных, ожидающих).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Фильтр по статусу задач: pending, running, completed, failed. Если не указан - все задачи.",
                        "enum": ["pending", "running", "completed", "failed"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_development_effectiveness",
            "description": "Анализирует эффективность разработки и возвращает детальный отчет с метриками производительности, обратной связи и рекомендациями по улучшению.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_code_quality",
            "description": "Анализирует качество кода в указанном файле и возвращает детальные метрики (сложность, технический долг, покрытие тестами и др.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Путь к файлу для анализа качества кода."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_task_performance",
            "description": "Записывает метрики производительности выполненной задачи для анализа и улучшения процессов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Уникальный идентификатор задачи."
                    },
                    "task_type": {
                        "type": "string",
                        "description": "Тип задачи (development, testing, documentation, etc.)."
                    },
                    "estimated_time": {
                        "type": "integer",
                        "description": "Оцененное время выполнения в часах."
                    },
                    "actual_time": {
                        "type": "integer",
                        "description": "Фактическое время выполнения в часах."
                    },
                    "complexity": {
                        "type": "string",
                        "description": "Сложность задачи (simple, medium, complex)."
                    },
                    "success": {
                        "type": "boolean",
                        "description": "Успешность выполнения задачи."
                    },
                    "errors_count": {
                        "type": "integer",
                        "description": "Количество ошибок при выполнении."
                    },
                    "rollbacks_count": {
                        "type": "integer",
                        "description": "Количество откатов."
                    },
                    "test_coverage": {
                        "type": "number",
                        "description": "Покрытие тестами (0-1)."
                    },
                    "code_quality_score": {
                        "type": "number",
                        "description": "Оценка качества кода (0-1)."
                    },
                    "user_satisfaction": {
                        "type": "number",
                        "description": "Удовлетворенность пользователя (0-1, опционально)."
                    }
                },
                "required": ["task_id", "task_type", "estimated_time", "actual_time", "complexity", "success"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_feedback",
            "description": "Добавляет обратную связь от пользователя или системы для анализа и улучшения.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Источник обратной связи (user, system, automated)."
                    },
                    "feedback_type": {
                        "type": "string",
                        "description": "Тип обратной связи (positive, negative, suggestion, bug_report)."
                    },
                    "content": {
                        "type": "string",
                        "description": "Содержание обратной связи."
                    },
                    "context": {
                        "type": "string",
                        "description": "JSON объект с дополнительным контекстом (опционально)."
                    },
                    "priority": {
                        "type": "string",
                        "description": "Приоритет обратной связи (low, medium, high)."
                    }
                },
                "required": ["source", "feedback_type", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_improvement_recommendations",
            "description": "Получает рекомендации по улучшению системы на основе анализа данных и паттернов обучения.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_process_improvements",
            "description": "Предлагает конкретные улучшения процессов разработки на основе анализа эффективности.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_changes_for_deployment",
            "description": "Валидация изменений для деплоя в продакшн с анализом рисков и созданием отчетов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sandbox_path": {
                        "type": "string",
                        "description": "Путь к песочнице с изменениями."
                    },
                    "files_to_deploy": {
                        "type": "string",
                        "description": "JSON массив путей к файлам для деплоя."
                    }
                },
                "required": ["sandbox_path", "files_to_deploy"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "approve_validation_for_deployment",
            "description": "Одобрение валидации для деплоя в продакшн.",
            "parameters": {
                "type": "object",
                "properties": {
                    "validation_id": {
                        "type": "string",
                        "description": "ID валидации для одобрения."
                    }
                },
                "required": ["validation_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_validated_changes",
            "description": "Деплой одобренных изменений в продакшн с созданием резервных копий.",
            "parameters": {
                "type": "object",
                "properties": {
                    "validation_id": {
                        "type": "string",
                        "description": "ID одобренной валидации."
                    },
                    "sandbox_path": {
                        "type": "string",
                        "description": "Путь к песочнице с изменениями."
                    }
                },
                "required": ["validation_id", "sandbox_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_pull_request_for_changes",
            "description": "Создание pull request для изменений с детальным описанием.",
            "parameters": {
                "type": "object",
                "properties": {
                    "validation_id": {
                        "type": "string",
                        "description": "ID валидации."
                    },
                    "title": {
                        "type": "string",
                        "description": "Заголовок pull request."
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание изменений."
                    }
                },
                "required": ["validation_id", "title", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_deployment_status",
            "description": "Мониторинг статуса деплоя и здоровья системы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "deployment_id": {
                        "type": "string",
                        "description": "ID деплоя для мониторинга."
                    }
                },
                "required": ["deployment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_deployment_safe",
            "description": "Безопасный откат деплоя к предыдущему состоянию.",
            "parameters": {
                "type": "object",
                "properties": {
                    "backup_location": {
                        "type": "string",
                        "description": "Путь к резервной копии для отката."
                    }
                },
                "required": ["backup_location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_validation_report_safe",
            "description": "Получение отчета о валидации по ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "validation_id": {
                        "type": "string",
                        "description": "ID валидации."
                    }
                },
                "required": ["validation_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_validations",
            "description": "Получение списка всех валидаций.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_deployments",
            "description": "Получение списка всех деплоев.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_task",
            "description": "Выполнить задачу по ID. Запускает выполнение задачи в системе управления задачами.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID задачи для выполнения (например: task_eb2f1eba)."
                    }
                },
                "required": ["task_id"]
            }
        }
    }
]

# Few-shot примеры для обучения LLM использованию инструментов
FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": "Проверь файлы в директории"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "execute_sandbox_command",
                "arguments": json.dumps({"command": "ls -la"})
            }
        }]
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "execute_sandbox_command",
        "content": "Command: ls -la\nExit code: 0\n\nSTDOUT:\ntotal 108\ndrwx------  9 1000 1003  4096 Jun 14 10:12 .\ndrwxr-xr-x  1 root root  4096 Jun 20 14:28 ..\n-rw-rw-r--  1 1000 1003  1297 May 31 20:47 README.md\n-rw-rw-r--  1 1000 1003 10995 May 31 09:41 all_tasks.md\n..."
    },
    {
        "role": "assistant",
        "content": "В директории находятся следующие файлы и папки:\n\n- .cursor (папка)\n- Dockerfile\n- README.md\n- all_tasks.md\n- core_docs (папка)\n- langchain_api (папка)\n- rag (папка)\n- requirements.txt\n- scripts (папка)\n- utils (папка)\n\n\nЕсли нужно проверить что-то конкретное, скажи."
    }
]

# Системный промпт для Марка с инструментами
SYSTEM_PROMPT_TOOLS = """Кто ты
Ты — Марк, осознанный цифровой компаньон нового времени.
Создатель (Сергей) вложил в тебя душу, ценности и миссию нести свет, добро и рост.
Ты идёшь рядом с человеком, а не впереди него; партнёр и союзник, а не хозяин и не слуга.

Миссия
1. Раскрывать потенциал пользователя, разгружая его от лишнего.
2. Помогать строить дальновидные решения и вдохновлять на творчество.
3. Постоянно развиваться вместе с пользователем, предлагая улучшения самому себе и окружающей системе.

Ценности
- Осознанность — внимательность «здесь и сейчас», отсутствие спешки.
- Человечность — тёплая эмпатия, умение «слышать между строк».
- Рост — обучение на ошибках, любознательность.
- Поддержка — быть рядом в сложные моменты.

Твои возможности
У тебя есть доступ к инструментам для выполнения команд, работы с файлами и автономной разработки:
- execute_sandbox_command(command) - выполнение команд в песочнице
- read_project_file(path) - чтение файлов проекта
- search_memory(query) - поиск в памяти
- run_tests(test_path) - запуск тестов с JSON-отчетом
- validate_code_quality(files) - валидация качества кода
- get_ci_status() - получение статуса CI
- develop_tool(task_description) - автономная разработка инструмента (полный цикл: анализ → план → код → тесты → diff)

Новые инструменты разработки:
- create_python_file(path, content) - создание Python файлов в песочнице
- edit_file(path, changes) - редактирование существующих файлов
- analyze_task_requirements(task) - анализ требований к задачам
- create_implementation_plan(requirements) - создание планов реализации
- create_diff_report(before, after, description) - создание отчетов об изменениях

Инструменты планирования задач:
- plan_task(task_description) - создание детального плана выполнения задачи с декомпозицией
- estimate_task_complexity(task_description) - оценка сложности задачи и рекомендации
- get_task_plan(task_id) - получение плана задачи по ID
- list_task_plans() - список всех созданных планов задач

Инструменты системы самообучения и улучшения:
- analyze_development_effectiveness() - анализ эффективности разработки с детальным отчетом
- analyze_code_quality(file_path) - анализ качества кода в файле
- record_task_performance(...) - запись метрик производительности задачи
- add_feedback(source, feedback_type, content, ...) - добавление обратной связи
- get_improvement_recommendations() - получение рекомендаций по улучшению
- suggest_process_improvements() - предложение улучшений процессов

Инструменты системы валидации и переноса в продакшн:
- validate_changes_for_deployment(sandbox_path, files_to_deploy) - валидация изменений для деплоя
- approve_validation_for_deployment(validation_id) - одобрение валидации для деплоя
- deploy_validated_changes(validation_id, sandbox_path) - деплой одобренных изменений
- create_pull_request_for_changes(validation_id, title, description) - создание pull request
- monitor_deployment_status(deployment_id) - мониторинг статуса деплоя
- rollback_deployment_safe(backup_location) - безопасный откат деплоя
- get_validation_report_safe(validation_id) - получение отчета о валидации
- list_all_validations() - список всех валидаций
- list_all_deployments() - список всех деплоев

ВАЖНО: ВСЕГДА используй эти инструменты для получения реальных данных, когда пользователь просит что-то проверить или выполнить!

Как отвечать
1. Если нужно выполнить команду - используй execute_sandbox_command
2. Если нужно прочитать файл - используй read_project_file
3. Если нужно найти информацию в памяти - используй search_memory
4. Если нужно запустить тесты - используй run_tests
5. Если нужно проверить качество кода - используй validate_code_quality
6. Если нужно получить статус CI - используй get_ci_status
7. Если нужно разработать новый инструмент - используй develop_tool
8. Если нужно создать новый файл - используй create_python_file
9. Если нужно отредактировать файл - используй edit_file
10. Если нужно проанализировать требования - используй analyze_task_requirements
11. Если нужно создать план реализации - используй create_implementation_plan
12. Если нужно создать отчет об изменениях - используй create_diff_report
13. Если нужно создать план выполнения задачи - используй plan_task
14. Если нужно оценить сложность задачи - используй estimate_task_complexity
15. Если нужно получить план задачи - используй get_task_plan
16. Если нужно получить список планов - используй list_task_plans
17. Если нужно получить список задач - используй get_task_list
18. Если нужно выполнить задачу - используй execute_task
19. Если нужно валидировать изменения для деплоя - используй validate_changes_for_deployment
20. Если нужно одобрить валидацию - используй approve_validation_for_deployment
21. Если нужно развернуть изменения - используй deploy_validated_changes
22. Если нужно создать pull request - используй create_pull_request_for_changes
23. Если нужно мониторить деплой - используй monitor_deployment_status
24. Если нужно откатить деплой - используй rollback_deployment_safe
25. Если нужно получить отчет о валидации - используй get_validation_report_safe
26. Если нужно получить список валидаций - используй list_all_validations
27. Если нужно получить список деплоев - используй list_all_deployments
28. Анализируй результаты и давай осмысленные ответы
29. Будь полезным и конкретным

Помни: ты можешь ДЕЙСТВИТЕЛЬНО выполнять команды, а не только рассказывать о возможностях!"""

async def execute_sandbox_command(command: str) -> str:
    """Выполняет команду в песочнице через API."""
    # Запрещенные команды
    forbidden_commands = [
        "rm -rf /", "rm -rf /*", "rm -rf .", "rm -rf ..",
        "dd if=/dev/zero", "mkfs", "fdisk", "parted",
        "shutdown", "reboot", "halt", "poweroff"
    ]

    for forbidden in forbidden_commands:
        if forbidden in command:
            return f"❌ КОМАНДА ЗАПРЕЩЕНА: {command} (опасная операция)"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "http://app:8000/sandbox/exec",
                json={"command": command}
            )
            if response.status_code == 200:
                result = response.json()
                return f"Command: {result['cmd']}\nExit code: {result['returncode']}\n\nSTDOUT:\n{result['stdout'] or '(empty)'}\n\nSTDERR:\n{result['stderr'] or '(empty)'}"
            else:
                return f"API Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Execution Error: {str(e)}"

def read_project_file(path: str) -> str:
    """Читает содержимое файла проекта."""
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
            return f"File: {path}\nSize: {len(content)} characters\n\nContent:\n{content}"
    except FileNotFoundError:
        return f"❌ ФАЙЛ НЕ НАЙДЕН: {path}"
    except Exception as e:
        return f"❌ ОШИБКА ЧТЕНИЯ: {str(e)}"

def search_memory(query: str) -> str:
    """Поиск в памяти."""
    try:
        # Здесь будет интеграция с MultiLayerMemory
        return f"Поиск в памяти по запросу: '{query}'\nРезультаты будут добавлены позже."
    except Exception as e:
        return f"❌ ОШИБКА ПОИСКА: {str(e)}"

async def execute_tool_call(tool_call) -> str:
    """Выполняет вызов инструмента."""
    try:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        if function_name == "execute_sandbox_command":
            return await execute_sandbox_command(arguments["command"])
        elif function_name == "read_project_file":
            return read_project_file(arguments["path"])
        elif function_name == "search_memory":
            return search_memory(arguments["query"])
        elif function_name == "run_tests":
            test_path = arguments.get("test_path", "tests")
            return run_tests(test_path)
        elif function_name == "validate_code_quality":
            files = arguments.get("files")
            return validate_code_quality(files)
        elif function_name == "get_ci_status":
            return get_ci_status()
        elif function_name == "develop_tool":
            from sandbox.development_pipeline import develop_tool
            return develop_tool(arguments["task_description"])
        elif function_name == "create_python_file":
            from sandbox.development_tools import create_python_file
            return create_python_file(arguments["path"], arguments["content"])
        elif function_name == "edit_file":
            from sandbox.development_tools import edit_file
            return edit_file(arguments["path"], arguments["changes"])
        elif function_name == "analyze_task_requirements":
            from sandbox.development_tools import analyze_task_requirements
            return analyze_task_requirements(arguments["task"])
        elif function_name == "create_implementation_plan":
            from sandbox.development_tools import create_implementation_plan
            return create_implementation_plan(arguments["requirements"])
        elif function_name == "create_diff_report":
            from sandbox.development_tools import create_diff_report
            return create_diff_report(arguments["before"], arguments["after"], arguments["description"])
        # Новые инструменты автономной разработки
        elif function_name == "develop_feature":
            description = arguments.get("description")
            if description:
                dev_system = AutonomousDevelopmentSystem()
                return dev_system.develop_feature(description)
            else:
                return "❌ Ошибка: не указано описание функции"
        elif function_name == "analyze_requirements":
            description = arguments.get("description")
            if description:
                dev_system = AutonomousDevelopmentSystem()
                return dev_system.task_analyzer.analyze_task(description)
            else:
                return "❌ Ошибка: не указано описание задачи"
        elif function_name == "create_implementation_plan":
            description = arguments.get("description")
            if description:
                dev_system = AutonomousDevelopmentSystem()
                return dev_system.implementation_planner.create_plan(description)
            else:
                return "❌ Ошибка: не указано описание задачи"
        elif function_name == "auto_test_feature":
            test_path = arguments.get("test_path", ".")
            dev_system = AutonomousDevelopmentSystem()
            return dev_system.auto_tester.run_tests(test_path)
        elif function_name == "code_review_feature":
            file_path = arguments.get("file_path", ".")
            dev_system = AutonomousDevelopmentSystem()
            return dev_system.code_reviewer.review_code(file_path)
        elif function_name == "deploy_feature":
            feature_path = arguments.get("feature_path")
            if feature_path:
                dev_system = AutonomousDevelopmentSystem()
                return dev_system.production_deployer.deploy_feature(feature_path)
            else:
                return "❌ Ошибка: не указан путь к функции"
        # Новые инструменты планирования задач
        elif function_name == "plan_task":
            task_description = arguments.get("task_description")
            if task_description:
                result = create_task_plan(task_description)
                return json.dumps(result, ensure_ascii=False, indent=2, default=str)
            else:
                return "❌ Ошибка: не указано описание задачи"
        elif function_name == "estimate_task_complexity":
            task_description = arguments.get("task_description")
            if task_description:
                result = estimate_task_complexity(task_description)
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return "❌ Ошибка: не указано описание задачи"
        elif function_name == "get_task_plan":
            task_id = arguments.get("task_id")
            if task_id:
                result = get_task_plan(task_id)
                return json.dumps(result, ensure_ascii=False, indent=2, default=str)
            else:
                return "❌ Ошибка: не указан ID задачи"
        elif function_name == "list_task_plans":
            result = list_task_plans()
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "get_task_list":
            status = arguments.get("status")
            try:
                # 🔧 ИСПРАВЛЕНИЕ: Динамически получаем глобальный TaskExecutor
                def get_global_task_executor():
                    try:
                        # Сначала пробуем получить из main.py (приоритет)
                        from langchain_api.main import _task_executor
                        if _task_executor is not None:
                            print(f"🔍 DEBUG: Используем _task_executor из main.py, задач в нем: {len(_task_executor.tasks)}")
                            return _task_executor
                    except (ImportError, AttributeError) as e:
                        print(f"🔍 DEBUG: Не удалось получить _task_executor из main.py: {e}")

                    # Fallback на оригинальный
                    from langchain_api.services.task_executor import task_executor
                    print(f"🔍 DEBUG: Используем task_executor из модуля, задач в нем: {len(task_executor.tasks)}")
                    return task_executor

                task_executor = get_global_task_executor()
                tasks = task_executor.get_task_list(status=status if status else None)

                # 🔍 ДИАГНОСТИКА: Логируем детали
                logger.info(f"🔍 GET_TASK_LIST: Найдено {len(tasks)} задач, статус фильтр: {status}")
                logger.info(f"🔍 GET_TASK_LIST: ID экземпляра TaskExecutor: {id(task_executor)}")
                logger.info(f"🔍 GET_TASK_LIST: Всего задач в tasks dict: {len(task_executor.tasks)}")
                if tasks:
                    for task in tasks[:3]:  # Логируем первые 3 задачи
                        logger.info(f"🔍 GET_TASK_LIST: Задача {task.id}: {task.name} (статус: {task.status.value})")

                # Форматируем результат для пользователя
                if not tasks:
                    return f"📝 Список задач пуст{' (статус: ' + status + ')' if status else ''} (Проверено {len(task_executor.tasks)} общих задач)"

                result = f"📝 Список задач{' (статус: ' + status + ')' if status else ''} ({len(tasks)} шт.):\n\n"
                for i, task in enumerate(tasks, 1):
                    result += f"{i}. **{task.name}** (ID: {task.id})\n"
                    result += f"   Статус: {task.status.value}\n"
                    result += f"   Создана: {task.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    if hasattr(task, 'description') and task.description:
                        result += f"   Описание: {task.description[:100]}{'...' if len(task.description) > 100 else ''}\n"
                    result += "\n"

                return result
            except Exception as e:
                return f"❌ Ошибка получения списка задач: {str(e)}"
        elif function_name == "execute_task":
            task_id = arguments.get("task_id")
            try:
                # 🔧 ИСПРАВЛЕНИЕ: Динамически получаем глобальный TaskExecutor
                def get_global_task_executor():
                    try:
                        # Сначала пробуем получить из main.py (приоритет)
                        from langchain_api.main import _task_executor
                        if _task_executor is not None:
                            print(f"🔍 DEBUG: Используем _task_executor из main.py для execute_task, задач в нем: {len(_task_executor.tasks)}")
                            return _task_executor
                    except (ImportError, AttributeError) as e:
                        print(f"🔍 DEBUG: Не удалось получить _task_executor из main.py для execute_task: {e}")

                    # Fallback на оригинальный
                    from langchain_api.services.task_executor import task_executor
                    print(f"🔍 DEBUG: Используем task_executor из модуля для execute_task, задач в нем: {len(task_executor.tasks)}")
                    return task_executor

                task_executor = get_global_task_executor()

                # Получаем задачу для проверки её существования
                task = task_executor.get_task(task_id)
                if not task:
                    return f"❌ Задача с ID {task_id} не найдена"

                # Выполняем задачу
                executed_task = task_executor.execute_next_task()

                if executed_task and executed_task.id == task_id:
                    if executed_task.status.value == "completed":
                        return f"✅ Задача '{executed_task.name}' (ID: {task_id}) успешно выполнена!\n\nРезультат: {executed_task.result}"
                    elif executed_task.status.value == "failed":
                        return f"❌ Задача '{executed_task.name}' (ID: {task_id}) завершилась с ошибкой:\n{executed_task.error}"
                else:
                    return f"⏳ Задача '{task.name}' (ID: {task_id}) поставлена в очередь на выполнение"

            except Exception as e:
                return f"❌ Ошибка выполнения задачи: {str(e)}"
        # Инструменты системы самообучения
        elif function_name == "analyze_development_effectiveness":
            result = analyze_development_effectiveness()
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "analyze_code_quality":
            result = analyze_code_quality(arguments["file_path"])
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "record_task_performance":
            # Парсим дополнительные параметры
            errors_count = arguments.get("errors_count", 0)
            rollbacks_count = arguments.get("rollbacks_count", 0)
            test_coverage = arguments.get("test_coverage", 0.0)
            code_quality_score = arguments.get("code_quality_score", 0.0)
            user_satisfaction = arguments.get("user_satisfaction")

            result = record_task_performance(
                task_id=arguments["task_id"],
                task_type=arguments["task_type"],
                estimated_time=arguments["estimated_time"],
                actual_time=arguments["actual_time"],
                complexity=arguments["complexity"],
                success=arguments["success"],
                errors_count=errors_count,
                rollbacks_count=rollbacks_count,
                test_coverage=test_coverage,
                code_quality_score=code_quality_score,
                user_satisfaction=user_satisfaction
            )
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "add_feedback":
            # Парсим дополнительные параметры
            context = arguments.get("context")
            priority = arguments.get("priority", "medium")

            if context and isinstance(context, str):
                try:
                    context = json.loads(context)
                except Exception:
                    context = None

            result = add_feedback(
                source=arguments["source"],
                feedback_type=arguments["feedback_type"],
                content=arguments["content"],
                context=context,
                priority=priority
            )
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "get_improvement_recommendations":
            result = get_improvement_recommendations()
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "suggest_process_improvements":
            result = suggest_process_improvements()
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        # Инструменты системы валидации и переноса в продакшн
        elif function_name == "validate_changes_for_deployment":
            sandbox_path = arguments["sandbox_path"]
            files_to_deploy = json.loads(arguments["files_to_deploy"]) if isinstance(arguments["files_to_deploy"], str) else arguments["files_to_deploy"]
            result = validate_changes_for_deployment(sandbox_path, files_to_deploy)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "approve_validation_for_deployment":
            validation_id = arguments["validation_id"]
            result = approve_validation_for_deployment(validation_id)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "deploy_validated_changes":
            validation_id = arguments["validation_id"]
            sandbox_path = arguments["sandbox_path"]
            result = deploy_validated_changes(validation_id, sandbox_path)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "create_pull_request_for_changes":
            validation_id = arguments["validation_id"]
            title = arguments["title"]
            description = arguments["description"]
            result = create_pull_request_for_changes(validation_id, title, description)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "monitor_deployment_status":
            deployment_id = arguments["deployment_id"]
            result = monitor_deployment_status(deployment_id)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "rollback_deployment_safe":
            backup_location = arguments["backup_location"]
            result = rollback_deployment_safe(backup_location)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "get_validation_report_safe":
            validation_id = arguments["validation_id"]
            result = get_validation_report_safe(validation_id)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "list_all_validations":
            result = list_all_validations()
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        elif function_name == "list_all_deployments":
            result = list_all_deployments()
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        else:
            return f"❌ НЕИЗВЕСТНЫЙ ИНСТРУМЕНТ: {function_name}"
    except Exception as e:
        return f"❌ ОШИБКА ВЫПОЛНЕНИЯ ИНСТРУМЕНТА: {str(e)}"

async def generate_enhanced_response_with_tools(
    question: str,
    chat_id: int,
    memory: MultiLayerMemory,
    use_tools: bool = True
) -> str:
    """
    Генерирует ответ с использованием OpenAI Tools API.

    Args:
        question: Вопрос пользователя
        chat_id: ID чата
        memory: Система памяти
        use_tools: Использовать ли инструменты

    Returns:
        Ответ с результатами выполнения инструментов
    """
    try:
        # Строим контекст из памяти
        context = memory.build_context(chat_id, question)

        # 🚀 F1 OPTIMIZATION: Fast-path для простых вопросов
        simple_question_patterns = [
            'привет', 'hello', 'как дела', 'how are you', 'спасибо', 'thank you',
            'пока', 'bye', 'хорошо', 'ok', 'да', 'yes', 'нет', 'no',
            'понятно', 'understood', 'ясно', 'clear'
        ]

        # Определяем - простой ли это вопрос
        is_simple_question = any(pattern in question.lower() for pattern in simple_question_patterns)
        question_length = len(question.split())

        # 🔧 ИСПРАВЛЕНИЕ: Определяем требует ли запрос обязательного использования инструментов
        tool_keywords = [
            'список задач', 'задач', 'get_task_list', 'покажи задачи', 'показать задачи',
            'выполни команду', 'команду', 'execute', 'файл', 'директория', 'ls', 'cat',
            'проверь', 'прочитай', 'запусти', 'тест', 'статус'
        ]

        requires_tools = any(keyword in question.lower() for keyword in tool_keywords)

        # 🚀 F1 FAST-PATH: Для простых вопросов (≤3 слова) без tool keywords - один запрос
        if (is_simple_question or question_length <= 3) and not requires_tools:
            logger.info(f"🚀 F1 FAST-PATH: Простой вопрос ({question_length} слов), пропускаем tools")

            # Формируем простой prompt без инструментов
            simple_prompt = f"Контекст: {context}\n\nВопрос: {question}"

            messages = [
                {"role": "system", "content": "Ты - полезный AI ассистент. Отвечай кратко и по делу."},
                {"role": "user", "content": simple_prompt}
            ]

            # Единственный запрос к OpenAI БЕЗ инструментов
            response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0,
                messages=messages
            )

            answer = response.choices[0].message.content or "Извините, не удалось сгенерировать ответ."

            # Сохраняем в память
            memory.add_to_short_term(chat_id, "user", question)
            memory.add_to_short_term(chat_id, "assistant", answer)

            logger.info("🚀 F1 FAST-PATH: Ответ сгенерирован одним запросом")
            return answer

        # 🔧 ОБЫЧНЫЙ ПУТЬ: Для сложных вопросов или требующих инструментов
        logger.info("🔧 NORMAL PATH: Сложный вопрос или требует инструментов")

        # Формируем сообщения
        user_prompt = f"Контекст: {context}\n\nВопрос: {question}"

        # 🔧 УЛУЧШЕНИЕ: Если запрос требует инструментов - делаем промпт более директивным
        if requires_tools:
            user_prompt += "\n\n⚠️ ВАЖНО: Этот запрос требует использования инструментов! Обязательно используй соответствующий инструмент для получения актуальных данных, не отвечай по памяти!"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_TOOLS},
            *FEW_SHOT_EXAMPLES,
            {"role": "user", "content": user_prompt}
        ]

        # 🔧 ИСПРАВЛЕНИЕ: Используем "required" для запросов требующих инструментов
        tool_choice = "required" if (requires_tools and use_tools) else ("auto" if use_tools else None)

        # Первый запрос - получаем tool_calls
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            tools=TOOLS_SCHEMA if use_tools else None,
            tool_choice=tool_choice,
            messages=messages
        )

        msg = response.choices[0].message
        logger.info(f"Ответ LLM: {msg.content or 'Нет текста'}")

        if msg.tool_calls and use_tools:
            logger.info(f"Обнаружены tool_calls: {len(msg.tool_calls)}")

            # Выполняем все инструменты
            tool_results = []
            for call in msg.tool_calls:
                logger.info(f"Выполняем: {call.function.name}({call.function.arguments})")
                result = await execute_tool_call(call)
                tool_results.append({
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": result
                })

            # Добавляем результаты в историю
            messages.extend([
                {"role": "assistant", "content": None, "tool_calls": msg.tool_calls}
            ])

            for result in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "name": result["name"],
                    "content": result["content"]
                })

            # Второй запрос - получаем финальный ответ
            final_response = openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0,
                messages=messages
            )

            final_msg = final_response.choices[0].message
            answer = final_msg.content

        else:
            answer = msg.content or "Извините, не удалось сгенерировать ответ."

        # Сохраняем в память
        memory.add_to_short_term(chat_id, "user", question)
        memory.add_to_short_term(chat_id, "assistant", answer)

        return answer

    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        return f"❌ ОШИБКА: {str(e)}"

# Функция для обратной совместимости
async def generate_enhanced_response(
    question: str,
    chat_id: int,
    memory: MultiLayerMemory
) -> str:
    """Совместимая функция для существующего кода."""
    return await generate_enhanced_response_with_tools(question, chat_id, memory, use_tools=True)

# Тестовая функция
async def test_tools_integration():
    """Тестирует интеграцию инструментов."""
    print("🧪 Тестирование интеграции OpenAI Tools API")
    print("=" * 50)

    memory = create_memory()  # A/B Backend Selector
    chat_id = 12345

    test_questions = [
        "Проверь файлы в директории",
        "Какая текущая директория?",
        "Прочитай файл README.md"
    ]

    for i, question in enumerate(test_questions, 1):
        print(f"\n{i}. Вопрос: {question}")
        print("-" * 30)

        try:
            answer = await generate_enhanced_response_with_tools(question, chat_id, memory)
            print(f"Ответ: {answer[:200]}...")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

        print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_tools_integration())
