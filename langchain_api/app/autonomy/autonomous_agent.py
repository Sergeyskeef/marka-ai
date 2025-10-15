"""
Автономный агент Марк - способен самостоятельно планировать, разрабатывать и тестировать
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum

from app.agents.mark_agent import MarkAgent
from app.learning.reap_cycle import REAPLearningCycle
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from .task_planner import TaskPlanner
from .code_generator import CodeGenerator
from .test_runner import TestRunner

logger = logging.getLogger(__name__)


class AutonomyLevel(Enum):
    """Уровни автономности агента"""
    MANUAL = "manual"  # Полностью управляется пользователем
    ASSISTED = "assisted"  # Помогает, но требует подтверждения
    SUPERVISED = "supervised"  # Действует самостоятельно, но под наблюдением
    AUTONOMOUS = "autonomous"  # Полная автономность


class AutonomousAgent:
    """
    Автономный агент Марк
    
    Способности:
    - Самостоятельное планирование задач
    - Написание и рефакторинг кода
    - Запуск и анализ тестов
    - Самообучение на основе результатов
    - Работа с проектами через Git
    """
    
    def __init__(
        self,
        mark_agent: MarkAgent,
        memory_adapter: AdvancedMemoryAdapter,
        learning_cycle: REAPLearningCycle,
        autonomy_level: AutonomyLevel = AutonomyLevel.SUPERVISED
    ):
        """
        Инициализация автономного агента
        
        Args:
            mark_agent: Основной агент Марк
            memory_adapter: Адаптер памяти
            learning_cycle: Цикл самообучения REAP
            autonomy_level: Уровень автономности
        """
        self.agent = mark_agent
        self.memory = memory_adapter
        self.learning = learning_cycle
        self.autonomy_level = autonomy_level
        
        # Компоненты автономности
        self.planner = TaskPlanner(mark_agent, memory_adapter)
        self.code_generator = CodeGenerator(mark_agent, memory_adapter)
        self.test_runner = TestRunner(mark_agent)
        
        # Состояние
        self.is_active = False
        self.current_project = None
        self.current_tasks = []
        self.completed_tasks = []
        
        logger.info(f"🤖 Автономный агент инициализирован с уровнем: {autonomy_level.value}")
    
    async def start_autonomous_mode(self, project_description: str) -> Dict[str, Any]:
        """
        Запустить автономный режим работы
        
        Args:
            project_description: Описание проекта для работы
        """
        try:
            logger.info(f"🚀 Запуск автономного режима для проекта: {project_description[:100]}...")
            
            self.is_active = True
            self.current_project = project_description
            self.completed_tasks = []

            # 1. Анализ проекта и создание плана
            logger.info("📋 Создание плана проекта...")
            plan = await self.planner.create_project_plan(project_description)
            self.current_tasks = plan["tasks"]
            
            # Сохраняем план в память
            await self.memory.save_project_plan(
                plan_name=plan.get("project_name", "autonomous_plan"),
                plan=plan,
                project_description=project_description,
                metadata={
                    "project": project_description,
                    "task_count": len(plan.get("tasks", [])),
                    "estimated_hours": plan.get("estimated_hours", 0),
                    "source": "autonomous_agent",
                }
            )
            
            # 2. Начинаем выполнение задач
            results = []
            for task in self.current_tasks:
                if not self.is_active:
                    break
                    
                result = await self._execute_task(task)
                results.append(result)

                # Обучаемся на результате
                if result["status"] == "completed":
                    self.completed_tasks.append(task)
                    await self._learn_from_result(task, result)
            
            return {
                "status": "completed" if self.is_active else "stopped",
                "plan": plan,
                "results": results,
                "completed_tasks": len([r for r in results if r["status"] == "completed"]),
                "total_tasks": len(self.current_tasks)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка в автономном режиме: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
        finally:
            self.is_active = False
    
    async def _execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполнить отдельную задачу
        
        Args:
            task: Описание задачи
        """
        try:
            logger.info(f"⚡ Выполнение задачи: {task['name']}")
            
            # Определяем тип задачи
            task_type = task.get("type", "general")
            
            if task_type == "code_generation":
                # Генерация кода
                result = await self._handle_code_generation(task)
            elif task_type == "testing":
                # Запуск тестов
                result = await self._handle_testing(task)
            elif task_type == "refactoring":
                # Рефакторинг кода
                result = await self._handle_refactoring(task)
            elif task_type == "documentation":
                # Создание документации
                result = await self._handle_documentation(task)
            else:
                # Общая задача - используем основного агента
                result = await self._handle_general_task(task)
            
            # Сохраняем результат в память
            await self.memory.create_episode(
                situation=f"Выполнение задачи: {task['name']}",
                outcome="success" if result["status"] == "completed" else "failure",
                reasoning=result.get("reasoning", ""),
                metadata={
                    "task": task,
                    "result": result,
                    "duration": result.get("duration", 0)
                }
            )
            
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении задачи {task['name']}: {str(e)}")
            return {
                "status": "error",
                "task": task,
                "error": str(e)
            }

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Публичный метод для выполнения задачи"""
        result = await self._execute_task(task)
        if result.get("status") == "completed":
            self.completed_tasks.append(task)
        return result
    
    async def _handle_code_generation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задачи генерации кода"""
        logger.info(f"💻 Генерация кода для: {task['description']}")
        
        # Используем CodeGenerator
        code_result = await self.code_generator.generate_code(
            description=task["description"],
            language=task.get("language", "python"),
            requirements=task.get("requirements", [])
        )
        
        # Если код сгенерирован успешно, сохраняем в файл
        if code_result["status"] == "success":
            file_path = task.get("output_file", f"generated_{task['name']}.py")
            await self._save_code_to_file(code_result["code"], file_path)
            
            # Запускаем тесты если нужно
            if task.get("auto_test", True):
                test_result = await self.test_runner.run_tests(file_path)
                code_result["test_result"] = test_result
        
        return code_result
    
    async def _handle_testing(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задачи тестирования"""
        logger.info(f"🧪 Запуск тестов для: {task['description']}")
        
        test_path = task.get("test_path", "tests/")
        return await self.test_runner.run_tests(test_path, verbose=True)
    
    async def _handle_refactoring(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задачи рефакторинга"""
        logger.info(f"🔧 Рефакторинг кода: {task['description']}")
        
        # Анализируем существующий код
        file_path = task.get("file_path")
        if not file_path:
            return {"status": "error", "error": "Не указан путь к файлу"}
        
        # Используем агента для анализа и улучшения кода
        analysis = await self.agent.call_tool(
            "analyze_code",
            {"file_path": file_path}
        )
        
        if analysis.get("improvements"):
            # Применяем улучшения
            refactored_code = await self.code_generator.refactor_code(
                file_path=file_path,
                improvements=analysis["improvements"]
            )
            return refactored_code
        
        return {"status": "completed", "message": "Код не требует рефакторинга"}
    
    async def _handle_documentation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задачи документирования"""
        logger.info(f"📚 Создание документации: {task['description']}")
        
        # Генерируем документацию
        doc_result = await self.code_generator.generate_documentation(
            target=task.get("target", "./"),
            format=task.get("format", "markdown")
        )
        
        return doc_result
    
    async def _handle_general_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка общей задачи через основного агента"""
        logger.info(f"🎯 Выполнение общей задачи: {task['description']}")
        
        # Формируем запрос к агенту
        prompt = f"""
        Выполни следующую задачу:
        
        Название: {task['name']}
        Описание: {task['description']}
        Требования: {task.get('requirements', [])}
        
        Используй доступные инструменты для выполнения задачи.
        """
        
        # Получаем ответ от агента
        response = await self.agent.generate_response(
            prompt,
            use_tools=True
        )
        
        return {
            "status": "completed",
            "task": task,
            "response": response,
            "duration": 0  # TODO: измерять время выполнения
        }
    
    async def _learn_from_result(self, task: Dict[str, Any], result: Dict[str, Any]):
        """
        Обучиться на результате выполнения задачи
        
        Args:
            task: Выполненная задача
            result: Результат выполнения
        """
        try:
            # Создаем эпизод для обучения
            episode_id = await self.memory.create_episode(
                situation=f"Completed task: {task['name']}",
                outcome="success" if result["status"] == "completed" else "failure",
                reasoning=f"Task type: {task.get('type', 'general')}, Result: {result.get('message', '')}",
                metadata={
                    "task": task,
                    "result": result
                }
            )
            
            # Запускаем цикл обучения
            if episode_id:
                await self.learning.reflect_on_episode(episode_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обучении: {str(e)}")
    
    async def _save_code_to_file(self, code: str, file_path: str):
        """Сохранить код в файл"""
        try:
            # Используем инструмент file_tools через агента
            await self.agent.call_tool(
                "write_file",
                {
                    "file_path": file_path,
                    "content": code
                }
            )
            logger.info(f"✅ Код сохранен в файл: {file_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении файла: {str(e)}")
    
    def stop(self):
        """Остановить автономный режим"""
        logger.info("🛑 Остановка автономного режима")
        self.is_active = False
    
    def set_autonomy_level(self, level: AutonomyLevel):
        """Установить уровень автономности"""
        self.autonomy_level = level
        logger.info(f"🎚️ Уровень автономности изменен на: {level.value}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Получить текущий статус агента"""
        return {
            "is_active": self.is_active,
            "autonomy_level": self.autonomy_level.value,
            "current_project": self.current_project,
            "tasks_total": len(self.current_tasks),
            "tasks_completed": len(self.completed_tasks),
            "current_task": self.current_tasks[0] if self.current_tasks else None
        }