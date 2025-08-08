import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langchain_api.services.security import AccessLevel, TaskCategory
from langchain_api.services.task_executor import Task, TaskPriority, TaskStatus
from langchain_api.telegram_bot.handlers.task_commands import (
    task_analyze,
    task_cancel,
    task_create,
    task_list,
    task_status,
)


@pytest.mark.asyncio
class TestTaskCommands:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.update = MagicMock()
        self.update.message = MagicMock()
        self.update.message.reply_text = AsyncMock()
        self.context = MagicMock()
        self.context.args = []

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_list_empty(self, mock_executor):
        mock_executor.get_active_tasks = AsyncMock(return_value=[])
        await task_list(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("📋 Нет активных задач")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_list_with_tasks(self, mock_executor):
        tasks = [
            Task(
                id="task1",
                name="Test task 1",
                description="Test task 1",
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM,
                parameters={},
                category=TaskCategory.CUSTOM,
                access_level=AccessLevel.READ
            ),
            Task(
                id="task2",
                name="Test task 2",
                description="Test task 2",
                status=TaskStatus.RUNNING,
                priority=TaskPriority.HIGH,
                parameters={},
                category=TaskCategory.CUSTOM,
                access_level=AccessLevel.READ
            )
        ]
        mock_executor.get_active_tasks = AsyncMock(return_value=tasks)
        await task_list(self.update, self.context)
        self.update.message.reply_text.assert_called_once()

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_status_no_args(self, mock_executor):
        await task_status(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Укажите ID задачи")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_status_not_found(self, mock_executor):
        self.context.args = ["nonexistent"]
        mock_executor.get_task = AsyncMock(return_value=None)
        await task_status(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Задача nonexistent не найдена")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_status_found(self, mock_executor):
        self.context.args = ["task1"]
        task = Task(
            id="task1",
            name="Test task",
            description="Test task",
            status=TaskStatus.RUNNING,
            priority=TaskPriority.MEDIUM,
            parameters={},
            category=TaskCategory.CUSTOM,
            access_level=AccessLevel.READ
        )
        mock_executor.get_task = AsyncMock(return_value=task)
        await task_status(self.update, self.context)
        self.update.message.reply_text.assert_called_once()

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_analyze_no_args(self, mock_executor):
        await task_analyze(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Укажите ID задачи")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    @patch('langchain_api.telegram_bot.handlers.task_commands.self_awareness')
    async def test_task_analyze_found(self, mock_awareness, mock_executor):
        self.context.args = ["task1"]
        task = Task(
            id="task1",
            name="Test task",
            description="Test task",
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.MEDIUM,
            parameters={},
            category=TaskCategory.CUSTOM,
            access_level=AccessLevel.READ
        )
        mock_executor.get_task = AsyncMock(return_value=task)
        mock_awareness.analyze_task = AsyncMock(return_value="Test analysis")
        await task_analyze(self.update, self.context)
        self.update.message.reply_text.assert_called_once()

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_create_no_args(self, mock_executor):
        await task_create(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Укажите описание задачи")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_create_invalid_priority(self, mock_executor):
        self.context.args = ["Test task", "invalid"]
        await task_create(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Неверный приоритет. Используйте: low, medium, high")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_create_success(self, mock_executor):
        self.context.args = ["Test task", "high"]
        task = Task(
            id="task1",
            name="Test task",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            parameters={},
            category=TaskCategory.CUSTOM,
            access_level=AccessLevel.READ
        )
        mock_executor.create_task = AsyncMock(return_value=task)
        await task_create(self.update, self.context)
        self.update.message.reply_text.assert_called_once()

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_cancel_no_args(self, mock_executor):
        await task_cancel(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Укажите ID задачи")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_cancel_success(self, mock_executor):
        self.context.args = ["task1"]
        mock_executor.cancel_task = AsyncMock(return_value=True)
        await task_cancel(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("✅ Задача task1 отменена")

    @patch('langchain_api.telegram_bot.handlers.task_commands.task_executor')
    async def test_task_cancel_failure(self, mock_executor):
        self.context.args = ["task1"]
        mock_executor.cancel_task = AsyncMock(return_value=False)
        await task_cancel(self.update, self.context)
        self.update.message.reply_text.assert_called_once_with("❌ Не удалось отменить задачу task1")

if __name__ == '__main__':
    unittest.main()
