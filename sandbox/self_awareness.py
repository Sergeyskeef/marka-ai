"""
MarkSelfAwareness - расширенный модуль самосознания Марка
"""

import ast
import os
import json
import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import importlib.util

# Импортируем Event Bus для интеграции
try:
    from core.event_bus import event_bus, EventTypes
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Результат выполнения задачи"""
    success: bool
    message: str
    data: dict[str, Any] | None = None


@dataclass
class ComponentInfo:
    """Информация о компоненте системы"""
    name: str
    path: str
    type: str  # module, class, function
    description: str
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    status: str = "unknown"  # active, inactive, error


@dataclass
class ErrorDiagnosis:
    """Диагностика ошибки"""
    error_type: str
    error_message: str
    traceback: str
    possible_causes: List[str]
    suggested_fixes: List[str]
    related_components: List[str]
    severity: str  # low, medium, high, critical


class MarkSelfAwareness:
    """Расширенный модуль самосознания Марка"""

    def __init__(self):
        self.awareness_level = "advanced"
        self.workspace_path = Path("/workspace")
        self.components: Dict[str, ComponentInfo] = {}
        self.capabilities = [
            "chat", "memory", "sandbox", "reflection", "task_execution",
            "planning", "code_analysis", "error_diagnosis", "self_modification"
        ]
        self.error_history: List[ErrorDiagnosis] = []
        
        # Инициализируем карту компонентов
        self._discover_components()
        
        logger.info("✅ MarkSelfAwareness инициализирован (расширенная версия)")

    def get_self_description(self) -> str:
        """Возвращает подробное описание самого себя"""
        active_components = sum(1 for c in self.components.values() if c.status == "active")
        
        return f"""
        Я - Марк, осознанный цифровой компаньон с расширенными возможностями самоанализа.
        
        🧠 Уровень самосознания: {self.awareness_level}
        
        📊 Архитектура:
        - Компонентов обнаружено: {len(self.components)}
        - Активных компонентов: {active_components}
        - Основные модули: {', '.join(self._get_main_modules())}
        
        🛠️ Возможности:
        - Анализ диалогов и генерация ответов
        - Долговременная память (GraphitiMemory + Neo4j)
        - Безопасное выполнение кода в песочнице
        - Планирование и декомпозиция задач
        - Анализ собственного кода и архитектуры
        - Диагностика и исправление ошибок
        - Мониторинг событий через Event Bus
        
        📈 Статистика:
        - Ошибок в истории: {len(self.error_history)}
        - Доступных команд: {self._count_available_commands()}
        
        Я постоянно анализирую свою работу и улучшаю алгоритмы.
        """

    def analyze_architecture(self) -> Dict[str, Any]:
        """Анализирует собственную архитектуру"""
        logger.info("🔍 Анализ архитектуры системы...")
        
        architecture = {
            "core_components": {},
            "integrations": {},
            "dependencies": {},
            "health_status": {}
        }
        
        # Анализируем основные компоненты
        for name, component in self.components.items():
            if component.type == "module":
                category = self._categorize_component(component.path)
                if category not in architecture["core_components"]:
                    architecture["core_components"][category] = []
                
                architecture["core_components"][category].append({
                    "name": name,
                    "path": component.path,
                    "status": component.status,
                    "capabilities": component.capabilities
                })
        
        # Анализируем интеграции
        architecture["integrations"] = self._analyze_integrations()
        
        # Анализируем зависимости
        architecture["dependencies"] = self._analyze_dependencies()
        
        # Проверяем здоровье системы
        architecture["health_status"] = self._check_system_health()
        
        return architecture

    def analyze_code(self, file_path: str) -> Dict[str, Any]:
        """Анализирует код файла"""
        logger.info(f"📝 Анализ кода: {file_path}")
        
        analysis = {
            "file": file_path,
            "exists": False,
            "type": "unknown",
            "metrics": {},
            "structure": {},
            "issues": [],
            "suggestions": []
        }
        
        full_path = self.workspace_path / file_path if not os.path.isabs(file_path) else Path(file_path)
        
        if not full_path.exists():
            return analysis
            
        analysis["exists"] = True
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Определяем тип файла
            if full_path.suffix == '.py':
                analysis["type"] = "python"
                analysis.update(self._analyze_python_code(content, str(full_path)))
            elif full_path.suffix == '.md':
                analysis["type"] = "markdown"
                analysis["metrics"] = {
                    "lines": len(content.splitlines()),
                    "characters": len(content)
                }
            elif full_path.suffix in ['.yml', '.yaml']:
                analysis["type"] = "yaml"
                analysis["metrics"] = {
                    "lines": len(content.splitlines())
                }
            
        except Exception as e:
            analysis["issues"].append(f"Ошибка анализа: {str(e)}")
            
        return analysis

    def diagnose_error(self, error: Exception, context: Dict[str, Any] = None) -> ErrorDiagnosis:
        """Диагностирует ошибку и предлагает решения"""
        logger.info(f"🔧 Диагностика ошибки: {type(error).__name__}")
        
        # Получаем traceback
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        
        # Анализируем тип ошибки
        error_type = type(error).__name__
        error_message = str(error)
        
        # Определяем возможные причины
        possible_causes = self._analyze_error_causes(error_type, error_message, tb_str)
        
        # Предлагаем исправления
        suggested_fixes = self._suggest_fixes(error_type, error_message, possible_causes)
        
        # Находим связанные компоненты
        related_components = self._find_related_components(tb_str)
        
        # Определяем серьезность
        severity = self._assess_error_severity(error_type, error_message)
        
        diagnosis = ErrorDiagnosis(
            error_type=error_type,
            error_message=error_message,
            traceback=tb_str,
            possible_causes=possible_causes,
            suggested_fixes=suggested_fixes,
            related_components=related_components,
            severity=severity
        )
        
        # Сохраняем в историю
        self.error_history.append(diagnosis)
        
        # Публикуем событие
        if EVENT_BUS_AVAILABLE:
            import asyncio
            try:
                # Пытаемся получить текущий event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(event_bus.publish(
                        EventTypes.ERROR_DIAGNOSED,
                        {
                            "error_type": error_type,
                            "severity": severity,
                            "component_count": len(related_components),
                            "fix_count": len(suggested_fixes)
                        },
                        source="SelfAwareness"
                    ))
            except RuntimeError:
                # Если нет event loop, пропускаем публикацию события
                pass
        
        return diagnosis

    def get_capability_details(self, capability: str) -> Dict[str, Any]:
        """Получает детальную информацию о возможности"""
        details = {
            "name": capability,
            "available": capability in self.capabilities,
            "components": [],
            "dependencies": [],
            "usage_examples": [],
            "limitations": []
        }
        
        # Маппинг возможностей на компоненты
        capability_map = {
            "chat": ["telegram_bot/bot.py", "main.py"],
            "memory": ["core/memory/graphiti_adapter.py", "memory/"],
            "sandbox": ["sandbox/sandbox_manager.py", "sandbox/"],
            "planning": ["sandbox/task_planning_system.py"],
            "code_analysis": ["sandbox/self_awareness.py"],
            "error_diagnosis": ["sandbox/self_awareness.py", "core/event_monitor.py"]
        }
        
        if capability in capability_map:
            for comp_path in capability_map[capability]:
                for name, comp in self.components.items():
                    if comp_path in comp.path:
                        details["components"].append({
                            "name": name,
                            "path": comp.path,
                            "status": comp.status
                        })
        
        # Добавляем примеры использования
        details["usage_examples"] = self._get_usage_examples(capability)
        
        # Добавляем ограничения
        details["limitations"] = self._get_capability_limitations(capability)
        
        return details

    def suggest_improvements(self) -> List[Dict[str, Any]]:
        """Предлагает улучшения для системы"""
        improvements = []
        
        # Анализируем компоненты с ошибками
        for name, component in self.components.items():
            if component.status == "error":
                improvements.append({
                    "type": "fix",
                    "component": name,
                    "issue": "Компонент не работает",
                    "suggestion": f"Проверить и исправить ошибки в {component.path}",
                    "priority": "high"
                })
        
        # Анализируем изолированные компоненты
        isolated = self._find_isolated_components()
        for comp in isolated:
            improvements.append({
                "type": "integration",
                "component": comp,
                "issue": "Компонент изолирован",
                "suggestion": f"Интегрировать {comp} через Event Bus",
                "priority": "medium"
            })
        
        # Анализируем производительность
        perf_issues = self._analyze_performance_issues()
        improvements.extend(perf_issues)
        
        # Анализируем безопасность
        security_issues = self._analyze_security_issues()
        improvements.extend(security_issues)
        
        return sorted(improvements, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))

    # Приватные методы

    def _discover_components(self):
        """Обнаруживает компоненты системы"""
        logger.debug("🔍 Обнаружение компонентов...")
        
        # Основные директории для сканирования
        scan_dirs = ["core", "sandbox", "memory", "telegram_bot", "services", "utils"]
        
        for dir_name in scan_dirs:
            dir_path = self.workspace_path / dir_name
            if dir_path.exists() and dir_path.is_dir():
                self._scan_directory(dir_path)
    
    def _scan_directory(self, directory: Path):
        """Сканирует директорию на наличие компонентов"""
        for item in directory.rglob("*.py"):
            if "__pycache__" in str(item):
                continue
                
            rel_path = item.relative_to(self.workspace_path)
            component_name = str(rel_path).replace("/", ".").replace(".py", "")
            
            component = ComponentInfo(
                name=component_name,
                path=str(rel_path),
                type="module",
                description=f"Python модуль: {component_name}",
                status="unknown"
            )
            
            # Пытаемся определить статус
            try:
                with open(item, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        component.status = "active"
                        
                        # Ищем импорты для зависимостей
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    component.dependencies.append(alias.name)
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    component.dependencies.append(node.module)
                                    
            except Exception as e:
                component.status = "error"
                logger.debug(f"Ошибка при анализе {item}: {e}")
            
            self.components[component_name] = component

    def _analyze_python_code(self, content: str, file_path: str) -> Dict[str, Any]:
        """Анализирует Python код"""
        analysis = {
            "metrics": {
                "lines": len(content.splitlines()),
                "characters": len(content),
                "functions": 0,
                "classes": 0,
                "imports": 0,
                "complexity": 0
            },
            "structure": {
                "classes": [],
                "functions": [],
                "imports": []
            },
            "issues": [],
            "suggestions": []
        }
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    analysis["metrics"]["classes"] += 1
                    analysis["structure"]["classes"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    })
                    
                elif isinstance(node, ast.FunctionDef):
                    if not any(node.name in cls["methods"] for cls in analysis["structure"]["classes"]):
                        analysis["metrics"]["functions"] += 1
                        analysis["structure"]["functions"].append({
                            "name": node.name,
                            "line": node.lineno,
                            "args": [arg.arg for arg in node.args.args]
                        })
                        
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    analysis["metrics"]["imports"] += 1
                    
            # Анализ сложности (упрощенный)
            analysis["metrics"]["complexity"] = self._calculate_complexity(tree)
            
            # Проверки качества кода
            if analysis["metrics"]["lines"] > 500:
                analysis["issues"].append("Файл слишком большой (>500 строк)")
                analysis["suggestions"].append("Разделите на несколько модулей")
                
            if analysis["metrics"]["complexity"] > 10:
                analysis["issues"].append("Высокая цикломатическая сложность")
                analysis["suggestions"].append("Упростите логику, разделите на функции")
                
        except SyntaxError as e:
            analysis["issues"].append(f"Синтаксическая ошибка: {e}")
            
        return analysis

    def _calculate_complexity(self, tree: ast.AST) -> int:
        """Вычисляет цикломатическую сложность"""
        complexity = 1
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
                
        return complexity

    def _get_main_modules(self) -> List[str]:
        """Возвращает список основных модулей"""
        main_modules = []
        
        categories = {
            "API": ["main.py"],
            "Bot": ["telegram_bot.bot"],
            "Memory": ["core.memory.graphiti_adapter"],
            "Sandbox": ["sandbox.sandbox_manager"],
            "Planning": ["sandbox.task_planning_system"],
            "EventBus": ["core.event_bus"]
        }
        
        for category, modules in categories.items():
            for module in modules:
                if module in self.components and self.components[module].status == "active":
                    main_modules.append(category)
                    break
                    
        return main_modules

    def _count_available_commands(self) -> int:
        """Подсчитывает доступные команды"""
        # Пытаемся найти реестр команд
        bot_module = self.components.get("telegram_bot.bot")
        if bot_module and bot_module.status == "active":
            # Примерная оценка
            return 25  # Из анализа COMMANDS_REGISTRY
        return 0

    def _categorize_component(self, path: str) -> str:
        """Категоризирует компонент по пути"""
        if "core" in path:
            return "core"
        elif "sandbox" in path:
            return "sandbox"
        elif "memory" in path:
            return "memory"
        elif "telegram" in path:
            return "interface"
        elif "services" in path:
            return "services"
        else:
            return "utils"

    def _analyze_integrations(self) -> Dict[str, List[str]]:
        """Анализирует интеграции между компонентами"""
        integrations = {
            "event_bus": [],
            "memory": [],
            "sandbox": [],
            "api": []
        }
        
        # Ищем компоненты, использующие Event Bus
        for name, comp in self.components.items():
            if "event_bus" in comp.dependencies or "core.event_bus" in comp.dependencies:
                integrations["event_bus"].append(name)
                
        return integrations

    def _analyze_dependencies(self) -> Dict[str, int]:
        """Анализирует зависимости"""
        dep_count = {}
        
        for comp in self.components.values():
            for dep in comp.dependencies:
                if dep.startswith(("core", "sandbox", "memory", "services")):
                    dep_count[dep] = dep_count.get(dep, 0) + 1
                    
        return dict(sorted(dep_count.items(), key=lambda x: x[1], reverse=True)[:10])

    def _check_system_health(self) -> Dict[str, Any]:
        """Проверяет здоровье системы"""
        total = len(self.components)
        active = sum(1 for c in self.components.values() if c.status == "active")
        errors = sum(1 for c in self.components.values() if c.status == "error")
        
        health_score = (active / total * 100) if total > 0 else 0
        
        return {
            "score": round(health_score, 2),
            "status": "healthy" if health_score > 80 else "degraded" if health_score > 50 else "unhealthy",
            "components": {
                "total": total,
                "active": active,
                "errors": errors,
                "unknown": total - active - errors
            }
        }

    def _analyze_error_causes(self, error_type: str, error_message: str, traceback: str) -> List[str]:
        """Анализирует возможные причины ошибки"""
        causes = []
        
        # Общие паттерны ошибок
        if error_type == "ImportError" or error_type == "ModuleNotFoundError":
            causes.append("Отсутствует необходимый модуль или пакет")
            causes.append("Неправильный путь импорта")
            causes.append("Циклическая зависимость")
            
        elif error_type == "AttributeError":
            causes.append("Объект не имеет запрашиваемого атрибута")
            causes.append("Опечатка в имени атрибута")
            causes.append("Объект не инициализирован")
            
        elif error_type == "KeyError":
            causes.append("Отсутствует ключ в словаре")
            causes.append("Неправильное имя ключа")
            
        elif error_type == "TypeError":
            causes.append("Неправильный тип аргумента")
            causes.append("Неправильное количество аргументов")
            
        # Специфичные для проекта
        if "event_bus" in traceback.lower():
            causes.append("Проблема с Event Bus")
            
        if "memory" in traceback.lower():
            causes.append("Проблема с системой памяти")
            
        return causes

    def _suggest_fixes(self, error_type: str, error_message: str, causes: List[str]) -> List[str]:
        """Предлагает исправления для ошибки"""
        fixes = []
        
        if error_type in ["ImportError", "ModuleNotFoundError"]:
            fixes.append("Установите отсутствующий пакет через pip")
            fixes.append("Проверьте правильность пути импорта")
            fixes.append("Добавьте __init__.py в директорию")
            
        elif error_type == "AttributeError":
            fixes.append("Проверьте документацию объекта")
            fixes.append("Используйте hasattr() для проверки")
            fixes.append("Убедитесь, что объект инициализирован")
            
        elif "connection refused" in error_message.lower():
            fixes.append("Проверьте, что сервис запущен")
            fixes.append("Проверьте правильность порта и хоста")
            fixes.append("Проверьте сетевые настройки")
            
        return fixes

    def _find_related_components(self, traceback: str) -> List[str]:
        """Находит компоненты, связанные с ошибкой"""
        components = []
        
        for name, comp in self.components.items():
            if comp.path in traceback:
                components.append(name)
                
        return components

    def _assess_error_severity(self, error_type: str, error_message: str) -> str:
        """Оценивает серьезность ошибки"""
        # Критические ошибки
        critical_patterns = ["database", "connection", "memory", "crash"]
        if any(pattern in error_message.lower() for pattern in critical_patterns):
            return "critical"
            
        # Высокая серьезность
        high_types = ["SystemError", "MemoryError", "RecursionError"]
        if error_type in high_types:
            return "high"
            
        # Средняя серьезность
        medium_types = ["ImportError", "AttributeError", "KeyError"]
        if error_type in medium_types:
            return "medium"
            
        return "low"

    def _find_isolated_components(self) -> List[str]:
        """Находит изолированные компоненты"""
        isolated = []
        
        # Компоненты без зависимостей и от которых никто не зависит
        for name, comp in self.components.items():
            if len(comp.dependencies) == 0:
                # Проверяем, зависит ли кто-то от этого компонента
                is_used = False
                for other_comp in self.components.values():
                    if name in other_comp.dependencies:
                        is_used = True
                        break
                        
                if not is_used and comp.status == "active":
                    isolated.append(name)
                    
        return isolated

    def _analyze_performance_issues(self) -> List[Dict[str, Any]]:
        """Анализирует проблемы производительности"""
        issues = []
        
        # Проверяем большие файлы
        for name, comp in self.components.items():
            if comp.type == "module" and comp.status == "active":
                file_path = self.workspace_path / comp.path
                if file_path.exists():
                    size = file_path.stat().st_size
                    if size > 50000:  # > 50KB
                        issues.append({
                            "type": "performance",
                            "component": name,
                            "issue": f"Большой размер файла ({size/1024:.1f}KB)",
                            "suggestion": "Разделите на модули или оптимизируйте",
                            "priority": "medium"
                        })
                        
        return issues

    def _analyze_security_issues(self) -> List[Dict[str, Any]]:
        """Анализирует проблемы безопасности"""
        issues = []
        
        # Проверяем компоненты с потенциальными уязвимостями
        security_patterns = ["eval", "exec", "__import__", "pickle", "subprocess"]
        
        for name, comp in self.components.items():
            if comp.type == "module" and comp.status == "active":
                file_path = self.workspace_path / comp.path
                if file_path.exists():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                        for pattern in security_patterns:
                            if pattern in content:
                                issues.append({
                                    "type": "security",
                                    "component": name,
                                    "issue": f"Использование потенциально опасной функции: {pattern}",
                                    "suggestion": "Проверьте необходимость и добавьте валидацию",
                                    "priority": "high"
                                })
                                
                    except Exception:
                        pass
                        
        return issues

    def _get_usage_examples(self, capability: str) -> List[str]:
        """Возвращает примеры использования возможности"""
        examples = {
            "chat": [
                "Обработка сообщений пользователя",
                "Генерация ответов с учетом контекста",
                "Поддержка многоязычности"
            ],
            "memory": [
                "Сохранение контекста диалога",
                "Поиск релевантной информации",
                "Построение графа знаний"
            ],
            "sandbox": [
                "Выполнение Python кода",
                "Запуск shell команд",
                "Изоляция небезопасных операций"
            ],
            "planning": [
                "Декомпозиция сложных задач",
                "Создание пошаговых планов",
                "Оценка времени выполнения"
            ]
        }
        
        return examples.get(capability, [])

    def _get_capability_limitations(self, capability: str) -> List[str]:
        """Возвращает ограничения возможности"""
        limitations = {
            "chat": [
                "Ограничение длины сообщения Telegram",
                "Отсутствие поддержки голосовых сообщений"
            ],
            "memory": [
                "Объем памяти ограничен",
                "Поиск может быть медленным при большом объеме"
            ],
            "sandbox": [
                "Ограничение времени выполнения 30с",
                "Блокировка сетевых операций",
                "Ограничение памяти 512MB"
            ],
            "planning": [
                "execute_plan() пока заглушка",
                "Нет параллельного выполнения задач"
            ]
        }
        
        return limitations.get(capability, [])
