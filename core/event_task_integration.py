#!/usr/bin/env python3
"""
Интеграция Event Bus с TaskExecutor для автоматических событий.
Обеспечивает публикацию событий при создании, выполнении и завершении задач.
"""

import logging
from typing import Any

from langchain_api.core.event_bus import (
    ErrorEvent,
    EventType,
    SuccessEvent,
    TaskEvent,
    get_event_bus,
    publish_event,
)
from langchain_api.services.task_executor import Task, TaskExecutor


class EventTaskIntegration:
    """Интеграция Event Bus с TaskExecutor"""

    def __init__(self, task_executor: TaskExecutor):
        self.event_bus = get_event_bus()
        self.task_executor = task_executor
        self._setup_task_hooks()

    def _setup_task_hooks(self):
        """Настраивает хуки для автоматической публикации событий задач"""
        # Сохраняем оригинальные методы
        original_create_task = self.task_executor.create_task
        original_update_task_status = self.task_executor.update_task_status
        original_complete_task = self.task_executor.complete_task
        original_fail_task = self.task_executor.fail_task

        # Перехватываем создание задачи
        def enhanced_create_task(*args, **kwargs):
            task = original_create_task(*args, **kwargs)
            self._publish_task_created_event(task)
            return task

        # Перехватываем обновление статуса
        def enhanced_update_task_status(*args, **kwargs):
            task = original_update_task_status(*args, **kwargs)
            if task:
                self._publish_task_status_changed_event(task)
            return task

        # Перехватываем завершение задачи
        def enhanced_complete_task(*args, **kwargs):
            task = original_complete_task(*args, **kwargs)
            if task:
                self._publish_task_completed_event(task)
            return task

        # Перехватываем ошибку задачи
        def enhanced_fail_task(*args, **kwargs):
            task = original_fail_task(*args, **kwargs)
            if task:
                self._publish_task_failed_event(task)
            return task

        # Заменяем методы
        self.task_executor.create_task = enhanced_create_task
        self.task_executor.update_task_status = enhanced_update_task_status
        self.task_executor.complete_task = enhanced_complete_task
        self.task_executor.fail_task = enhanced_fail_task

        logging.info("Event Task Integration настроена")

    def _publish_task_created_event(self, task: Task) -> None:
        """Публикует событие создания задачи"""
        try:
            event = TaskEvent(
                event_type=EventType.TASK,
                timestamp=task.created_at,
                source="TaskExecutor",
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "description": task.description,
                    "priority": task.priority.name,
                    "category": task.category.name if task.category else "unknown",
                    "access_level": task.access_level.name if task.access_level else "unknown",
                    "parameters": task.parameters
                },
                task_id=task.id,
                task_type="task_creation",
                status="created"
            )

            publish_event(event)
            logging.info(f"Опубликовано событие создания задачи: {task.id}")

        except Exception as e:
            logging.error(f"Ошибка при публикации события создания задачи: {e}")

    def _publish_task_status_changed_event(self, task: Task) -> None:
        """Публикует событие изменения статуса задачи"""
        try:
            event = TaskEvent(
                event_type=EventType.TASK,
                timestamp=task.updated_at,
                source="TaskExecutor",
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "status": task.status.name,
                    "previous_status": "unknown",  # TODO: Добавить отслеживание предыдущего статуса
                    "result": str(task.result) if task.result else None,
                    "error": task.error
                },
                task_id=task.id,
                task_type="task_status_change",
                status=task.status.name
            )

            publish_event(event)
            logging.info(f"Опубликовано событие изменения статуса задачи: {task.id} -> {task.status.name}")

        except Exception as e:
            logging.error(f"Ошибка при публикации события изменения статуса задачи: {e}")

    def _publish_task_completed_event(self, task: Task) -> None:
        """Публикует событие успешного завершения задачи"""
        try:
            # Событие задачи
            task_event = TaskEvent(
                event_type=EventType.TASK,
                timestamp=task.updated_at,
                source="TaskExecutor",
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "result": str(task.result) if task.result else "completed",
                    "execution_time": (task.updated_at - task.created_at).total_seconds()
                },
                task_id=task.id,
                task_type="task_completion",
                status="completed"
            )

            # Событие успеха
            success_event = SuccessEvent(
                event_type=EventType.SUCCESS,
                timestamp=task.updated_at,
                source="TaskExecutor",
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "operation": "task_execution",
                    "result": "Task completed successfully"
                },
                operation="task_execution",
                result="Task completed successfully"
            )

            publish_event(task_event)
            publish_event(success_event)
            logging.info(f"Опубликованы события завершения задачи: {task.id}")

        except Exception as e:
            logging.error(f"Ошибка при публикации событий завершения задачи: {e}")

    def _publish_task_failed_event(self, task: Task) -> None:
        """Публикует событие ошибки задачи"""
        try:
            # Событие задачи
            task_event = TaskEvent(
                event_type=EventType.TASK,
                timestamp=task.updated_at,
                source="TaskExecutor",
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "error": task.error,
                    "execution_time": (task.updated_at - task.created_at).total_seconds()
                },
                task_id=task.id,
                task_type="task_failure",
                status="failed"
            )

            # Событие ошибки
            error_event = ErrorEvent(
                event_type=EventType.ERROR,
                timestamp=task.updated_at,
                source="TaskExecutor",
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "error_type": "task_execution_error",
                    "error_message": task.error or "Task execution failed"
                },
                error_type="task_execution_error",
                error_message=task.error or "Task execution failed"
            )

            publish_event(task_event)
            publish_event(error_event)
            logging.info(f"Опубликованы события ошибки задачи: {task.id}")

        except Exception as e:
            logging.error(f"Ошибка при публикации событий ошибки задачи: {e}")

    def get_task_statistics(self) -> dict[str, Any]:
        """Получает статистику по задачам"""
        try:
            tasks = self.task_executor.get_task_list()
            stats = {
                "total_tasks": len(tasks),
                "by_status": {},
                "by_priority": {},
                "by_category": {},
                "recent_tasks": []
            }

            for task in tasks:
                # Статистика по статусам
                status = task.status.name
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

                # Статистика по приоритетам
                priority = task.priority.name
                stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

                # Статистика по категориям
                category = task.category.name if task.category else "unknown"
                stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

                # Недавние задачи (последние 10)
                if len(stats["recent_tasks"]) < 10:
                    stats["recent_tasks"].append({
                        "id": task.id,
                        "name": task.name,
                        "status": status,
                        "created_at": task.created_at.isoformat()
                    })

            return stats

        except Exception as e:
            logging.error(f"Ошибка при получении статистики задач: {e}")
            return {}


def get_event_task_integration(task_executor: TaskExecutor) -> EventTaskIntegration:
    """Получает экземпляр интеграции Event Bus с TaskExecutor"""
    return EventTaskIntegration(task_executor)
