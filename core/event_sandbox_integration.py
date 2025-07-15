#!/usr/bin/env python3
"""
Интеграция Event Bus с SandboxManager для автоматических событий.
Обеспечивает публикацию событий при выполнении команд в песочнице.
"""

import logging
from datetime import datetime
from typing import Any

from langchain_api.core.event_bus import (
    ErrorEvent,
    EventType,
    SuccessEvent,
    SystemEvent,
    get_event_bus,
    publish_event,
)
from langchain_api.sandbox.sandbox_manager import CommandResult, Sandbox, SandboxManager


class EventSandboxIntegration:
    """Интеграция Event Bus с SandboxManager"""

    def __init__(self, sandbox_manager: SandboxManager):
        self.event_bus = get_event_bus()
        self.sandbox_manager = sandbox_manager
        self._setup_sandbox_hooks()

    def _setup_sandbox_hooks(self):
        """Настраивает хуки для автоматической публикации событий песочницы"""
        # Сохраняем оригинальные методы
        original_create_sandbox = self.sandbox_manager.create_sandbox
        original_execute_command = self.sandbox_manager.execute_command
        original_cleanup = self.sandbox_manager.cleanup

        # Перехватываем создание песочницы
        def enhanced_create_sandbox(*args, **kwargs):
            sandbox = original_create_sandbox(*args, **kwargs)
            self._publish_sandbox_created_event(sandbox)
            return sandbox

        # Перехватываем выполнение команды
        def enhanced_execute_command(*args, **kwargs):
            result = original_execute_command(*args, **kwargs)
            self._publish_command_executed_event(result)
            return result

        # Перехватываем очистку песочницы
        def enhanced_cleanup(*args, **kwargs):
            result = original_cleanup(*args, **kwargs)
            self._publish_sandbox_cleanup_event(args[0])  # sandbox_id
            return result

        # Заменяем методы
        self.sandbox_manager.create_sandbox = enhanced_create_sandbox
        self.sandbox_manager.execute_command = enhanced_execute_command
        self.sandbox_manager.cleanup = enhanced_cleanup

        logging.info("Event Sandbox Integration настроена")

    def _publish_sandbox_created_event(self, sandbox: Sandbox) -> None:
        """Публикует событие создания песочницы"""
        try:
            event = SystemEvent(
                event_type=EventType.SYSTEM,
                timestamp=datetime.now(),
                source="SandboxManager",
                data={
                    "sandbox_id": sandbox.id,
                    "sandbox_path": str(sandbox.path),
                    "is_active": sandbox.is_active,
                    "operation": "sandbox_creation"
                },
                system_component="SandboxManager",
                action="create_sandbox",
                details=f"Created sandbox {sandbox.id} at {sandbox.path}"
            )

            publish_event(event)
            logging.info(f"Опубликовано событие создания песочницы: {sandbox.id}")

        except Exception as e:
            logging.error(f"Ошибка при публикации события создания песочницы: {e}")

    def _publish_command_executed_event(self, result: CommandResult) -> None:
        """Публикует событие выполнения команды"""
        try:
            if result.status == "completed":
                # Событие успеха
                success_event = SuccessEvent(
                    event_type=EventType.SUCCESS,
                    timestamp=datetime.now(),
                    source="SandboxManager",
                    data={
                        "task_id": result.task_id,
                        "status": result.status,
                        "execution_time": result.execution_time,
                        "success_rate": result.success_rate,
                        "output_length": len(result.output) if result.output else 0
                    },
                    operation="command_execution",
                    result=f"Command executed successfully in {result.execution_time:.2f}s"
                )
                publish_event(success_event)

            else:
                # Событие ошибки
                error_event = ErrorEvent(
                    event_type=EventType.ERROR,
                    timestamp=datetime.now(),
                    source="SandboxManager",
                    data={
                        "task_id": result.task_id,
                        "status": result.status,
                        "execution_time": result.execution_time,
                        "error": result.error,
                        "error_messages": result.error_messages
                    },
                    error_type="command_execution_error",
                    error_message=result.error or "Command execution failed",
                    stack_trace="\n".join(result.error_messages) if result.error_messages else None
                )
                publish_event(error_event)

            # Системное событие о выполнении команды с деталями
            system_event = SystemEvent(
                event_type=EventType.SYSTEM,
                timestamp=datetime.now(),
                source="SandboxManager",
                data={
                    "task_id": result.task_id,
                    "status": result.status,
                    "execution_time": result.execution_time,
                    "performance_metrics": result.performance_metrics,
                    "command_output": result.output,  # Добавляем вывод команды
                    "command_error": result.error     # Добавляем ошибку если есть
                },
                system_component="SandboxManager",
                action="execute_command",
                details=f"Command executed with status: {result.status}. Output: {result.output[:100]}..."  # Добавляем детали
            )
            publish_event(system_event)

            logging.info(f"Опубликованы события выполнения команды: {result.task_id}")

        except Exception as e:
            logging.error(f"Ошибка при публикации событий выполнения команды: {e}")

    def _publish_sandbox_cleanup_event(self, sandbox_id: str) -> None:
        """Публикует событие очистки песочницы"""
        try:
            event = SystemEvent(
                event_type=EventType.SYSTEM,
                timestamp=datetime.now(),
                source="SandboxManager",
                data={
                    "sandbox_id": sandbox_id,
                    "operation": "sandbox_cleanup"
                },
                system_component="SandboxManager",
                action="cleanup_sandbox",
                details=f"Cleaned up sandbox {sandbox_id}"
            )

            publish_event(event)
            logging.info(f"Опубликовано событие очистки песочницы: {sandbox_id}")

        except Exception as e:
            logging.error(f"Ошибка при публикации события очистки песочницы: {e}")

    def get_sandbox_statistics(self) -> dict[str, Any]:
        """Получает статистику по песочницам"""
        try:
            active_sandboxes = self.sandbox_manager.active_sandboxes
            stats = {
                "total_sandboxes": len(active_sandboxes),
                "active_sandboxes": len([s for s in active_sandboxes.values() if s.is_active]),
                "sandbox_details": []
            }

            for sandbox_id, sandbox in active_sandboxes.items():
                stats["sandbox_details"].append({
                    "id": sandbox_id,
                    "path": str(sandbox.path),
                    "is_active": sandbox.is_active
                })

            return stats

        except Exception as e:
            logging.error(f"Ошибка при получении статистики песочниц: {e}")
            return {}


def get_event_sandbox_integration(sandbox_manager: SandboxManager) -> EventSandboxIntegration:
    """Получает экземпляр интеграции Event Bus с SandboxManager"""
    return EventSandboxIntegration(sandbox_manager)
