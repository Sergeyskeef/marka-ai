"""
TaskExecutor - сервис для выполнения задач
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Приоритеты задач"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(Enum):
    """Статусы задач"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCategory(Enum):
    """Категории задач"""
    SYSTEM = "system"
    USER = "user"
    MAINTENANCE = "maintenance"
    ANALYSIS = "analysis"


class AccessLevel(Enum):
    """Уровни доступа"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class Task:
    """Класс задачи"""

    def __init__(self,
                 id: str,
                 title: str,
                 description: str,
                 priority: TaskPriority = TaskPriority.NORMAL,
                 category: TaskCategory = TaskCategory.USER,
                 access_level: AccessLevel = AccessLevel.READ,
                 parameters: dict[str, Any] | None = None):
        self.id = id
        self.name = title  # Для совместимости с event_task_integration
        self.title = title
        self.description = description
        self.priority = priority
        self.category = category
        self.access_level = access_level
        self.parameters = parameters or {}
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now()
        self.updated_at = datetime.now()  # Для совместимости с event_task_integration
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Преобразует задачу в словарь"""
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "category": self.category.value,
            "access_level": self.access_level.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "parameters": self.parameters
        }


class TaskExecutor:
    """Исполнитель задач"""

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.task_counter = 0
        logger.info("✅ TaskExecutor инициализирован")

    def create_task(self,
                   title: str,
                   description: str,
                   priority: TaskPriority = TaskPriority.NORMAL,
                   category: TaskCategory = TaskCategory.USER,
                   access_level: AccessLevel = AccessLevel.READ,
                   parameters: dict[str, Any] | None = None) -> Task:
        """Создает новую задачу"""
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"

        task = Task(
            id=task_id,
            title=title,
            description=description,
            priority=priority,
            category=category,
            access_level=access_level,
            parameters=parameters
        )

        self.tasks[task_id] = task
        logger.info(f"📋 Создана задача: {title} (ID: {task_id})")

        return task

    def update_task_status(self, task_id: str, status: TaskStatus, result: dict[str, Any] | None = None, error: str | None = None) -> Task | None:
        """Обновляет статус задачи"""
        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]
        task.status = status
        task.updated_at = datetime.now()

        if status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = datetime.now()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.completed_at = datetime.now()

        if result is not None:
            task.result = result
        if error is not None:
            task.error = error

        logger.info(f"🔄 Статус задачи {task_id} обновлен: {status.value}")
        return task

    def complete_task(self, task_id: str, success: bool = True, error_message: str | None = None) -> Task | None:
        """Завершает задачу"""
        if task_id not in self.tasks:
            logger.warning(f"Попытка завершить несуществующую задачу: {task_id}")
            return None

        task = self.tasks[task_id]

        if task.status != TaskStatus.RUNNING:
            logger.warning(f"Попытка завершить задачу {task_id} со статусом {task.status.value}")
            return None

        status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        result = {"success": success}

        if not success and error_message:
            task.error = error_message
            result["error"] = error_message

        updated_task = self.update_task_status(task_id, status, result=result, error=task.error)

        if success:
            logger.info(f"✅ Задача {task_id} успешно завершена")
        else:
            logger.error(f"❌ Задача {task_id} завершена с ошибкой: {error_message}")

        return updated_task

    def fail_task(self, task_id: str, error_message: str) -> Task | None:
        """Завершает задачу с ошибкой"""
        return self.complete_task(task_id, success=False, error_message=error_message)

    async def execute_task(self, task_id: str) -> dict[str, Any]:
        """Выполняет задачу"""
        if task_id not in self.tasks:
            raise ValueError(f"Задача {task_id} не найдена")

        task = self.tasks[task_id]

        if task.status != TaskStatus.PENDING:
            raise ValueError(f"Задача {task_id} уже выполняется или завершена")

        self.update_task_status(task_id, TaskStatus.RUNNING)

        logger.info(f"🚀 Начато выполнение задачи: {task.title}")

        try:
            # Симуляция выполнения задачи
            await asyncio.sleep(1)

            result = {
                "success": True,
                "message": f"Задача '{task.title}' выполнена успешно",
                "execution_time": (datetime.now() - task.started_at).total_seconds() if task.started_at else 0
            }

            self.complete_task(task_id, success=True)

            logger.info(f"✅ Задача выполнена: {task.title}")

            return result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e)
            }

            self.complete_task(task_id, success=False, error_message=str(e))

            logger.error(f"❌ Ошибка выполнения задачи {task.title}: {e}")

            return error_result

    def get_task(self, task_id: str) -> Task | None:
        """Возвращает задачу по ID"""
        return self.tasks.get(task_id)

    def get_task_list(self) -> list[Task]:
        """Возвращает список всех задач (для совместимости с event_task_integration)"""
        return list(self.tasks.values())

    def get_all_tasks(self) -> list[Task]:
        """Возвращает все задачи"""
        return list(self.tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """Возвращает задачи по статусу"""
        return [task for task in self.tasks.values() if task.status == status]

    def cancel_task(self, task_id: str) -> bool:
        """Отменяет задачу"""
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]
        if task.status == TaskStatus.RUNNING:
            # Отменяем асинхронную задачу
            if task_id in self.running_tasks:
                self.running_tasks[task_id].cancel()
                del self.running_tasks[task_id]

        self.update_task_status(task_id, TaskStatus.CANCELLED)

        logger.info(f"❌ Задача отменена: {task.title}")
        return True

    def get_task_stats(self) -> dict[str, Any]:
        """Возвращает статистику задач"""
        total = len(self.tasks)
        by_status = {}
        for status in TaskStatus:
            by_status[status.value] = len(self.get_tasks_by_status(status))

        return {
            "total_tasks": total,
            "by_status": by_status,
            "by_priority": {
                priority.value: len([t for t in self.tasks.values() if t.priority == priority])
                for priority in TaskPriority
            },
            "by_category": {
                category.value: len([t for t in self.tasks.values() if t.category == category])
                for category in TaskCategory
            }
        }

    async def enqueue(self, task: dict) -> str:
        """Добавляет задачу в очередь (Slim TaskExecutor API)"""
        task_type = task.get("type", "unknown")
        content = task.get("content", "")
        metadata = task.get("metadata", {})

        # Создаем задачу
        new_task = self.create_task(
            title=f"Task {task_type}",
            description=content[:100] + "..." if len(content) > 100 else content,
            parameters={"type": task_type, "content": content, "metadata": metadata}
        )

        # Запускаем выполнение в фоне
        asyncio.create_task(self.execute_task(new_task.id))

        return new_task.id

    async def get_status(self, task_id: str) -> dict:
        """Получает статус задачи (Slim TaskExecutor API)"""
        task = self.get_task(task_id)
        if not task:
            return {"status": "not_found", "error": "Task not found"}

        return {
            "status": task.status.value,
            "result": task.result,
            "error": task.error
        }

    async def complete_task_with_result(self, task_id: str, result: dict) -> None:
        """Завершает задачу с результатом (Slim TaskExecutor API)"""
        task = self.get_task(task_id)
        if not task:
            return

        success = result.get("success", True)
        error_message = result.get("error") if not success else None

        updated_task = self.complete_task(task_id, success=success, error_message=error_message)

        # Записываем завершение задачи в память Graphiti
        if updated_task:
            try:
                from langchain_api.core.memory.memory_manager import memory_manager

                # Создаем текст эпизода
                episode_text = f"Task {task_id} completed: {updated_task.title}"
                if updated_task.result:
                    episode_text += f" - Result: {str(updated_task.result)}"
                if updated_task.error:
                    episode_text += f" - Error: {updated_task.error}"

                # Метаданные задачи
                metadata = {
                    "task_id": task_id,
                    "type": "task_completion",
                    "success": success,
                    "category": updated_task.category.value,
                    "priority": updated_task.priority.value,
                    "execution_time": (updated_task.completed_at - updated_task.started_at).total_seconds() if updated_task.started_at and updated_task.completed_at else None
                }

                # Добавляем в память
                await memory_manager.add_episode(episode_text, metadata)
                logger.info(f"✅ Завершение задачи {task_id} записано в память Graphiti")

            except Exception as e:
                logger.error(f"❌ Ошибка записи завершения задачи {task_id} в память: {str(e)}")
                # Не прерываем выполнение, если запись в память не удалась


# Глобальный экземпляр TaskExecutor
task_executor = TaskExecutor()
