import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Message, Update
from telegram.ext import ContextTypes

import telegram_bot.bot as bot_module


@pytest.fixture
def update():
    """Фикстура для Update"""
    message = AsyncMock(spec=Message)
    message.reply_text = AsyncMock()
    update = AsyncMock(spec=Update)
    update.message = message
    return update

@pytest.fixture
def context():
    """Фикстура для Context"""
    context = AsyncMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    return context

@pytest.fixture
def patch_task_executor(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(bot_module, 'task_executor', mock)
    return mock

@pytest.fixture(autouse=True)
def mock_subprocess_run():
    with patch('subprocess.run') as mock_run:
        yield mock_run

@pytest.mark.asyncio
async def test_sandbox_exec_cmd_no_args(update, context):
    """Тест команды /sandbox_exec без аргументов"""
    await bot_module.sandbox_exec_cmd(update, context)
    update.message.reply_text.assert_called_once_with("❌ Укажите команду для выполнения в песочнице")

@pytest.mark.asyncio
async def test_sandbox_exec_cmd_success(update, context, patch_task_executor):
    """Тест успешного выполнения команды /sandbox_exec"""
    context.args = ["echo", "test"]
    patch_task_executor.execute_sandbox_command.return_value = (True, "test output")

    await bot_module.sandbox_exec_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("✅ Команда выполнена успешно:\n\ntest output")

@pytest.mark.asyncio
async def test_sandbox_exec_cmd_failure(update, context, patch_task_executor):
    """Тест ошибки выполнения команды /sandbox_exec"""
    context.args = ["invalid_command"]
    patch_task_executor.execute_sandbox_command.return_value = (False, "command not found")

    await bot_module.sandbox_exec_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("❌ Ошибка выполнения команды:\n\ncommand not found")

@pytest.mark.asyncio
async def test_sandbox_diff_cmd_success(update, context, patch_task_executor):
    """Тест успешного получения диффа через /sandbox_diff"""
    patch_task_executor.create_sandbox_diff.return_value = (True, "diff output")

    await bot_module.sandbox_diff_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("📝 Изменения в песочнице:\n\n```\ndiff output\n```")

@pytest.mark.asyncio
async def test_sandbox_diff_cmd_no_changes(update, context, patch_task_executor):
    """Тест получения пустого диффа через /sandbox_diff"""
    patch_task_executor.create_sandbox_diff.return_value = (True, "")

    await bot_module.sandbox_diff_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("ℹ️ Нет изменений в песочнице")

@pytest.mark.asyncio
async def test_sandbox_diff_cmd_failure(update, context, patch_task_executor):
    """Тест ошибки получения диффа через /sandbox_diff"""
    patch_task_executor.create_sandbox_diff.return_value = (False, "error getting diff")

    await bot_module.sandbox_diff_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("❌ Ошибка получения изменений:\n\nerror getting diff")

@pytest.mark.asyncio
async def test_sandbox_apply_cmd_success(update, context, patch_task_executor):
    """Тест успешного применения изменений через /sandbox_apply"""
    patch_task_executor.apply_sandbox_changes.return_value = (True, "success")

    await bot_module.sandbox_apply_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("✅ Изменения успешно применены")

@pytest.mark.asyncio
async def test_sandbox_apply_cmd_failure(update, context, patch_task_executor):
    """Тест ошибки применения изменений через /sandbox_apply"""
    patch_task_executor.apply_sandbox_changes.return_value = (False, "error applying changes")

    await bot_module.sandbox_apply_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("❌ Ошибка применения изменений:\n\nerror applying changes")

@pytest.mark.asyncio
async def test_sandbox_validate_cmd_success(update, context, patch_task_executor):
    """Тест успешной валидации изменений через /sandbox_validate"""
    patch_task_executor.validate_sandbox_changes.return_value = (True, "success")

    await bot_module.sandbox_validate_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("✅ Изменения прошли валидацию")

@pytest.mark.asyncio
async def test_sandbox_validate_cmd_failure(update, context, patch_task_executor):
    """Тест ошибки валидации изменений через /sandbox_validate"""
    patch_task_executor.validate_sandbox_changes.return_value = (False, "validation failed")

    await bot_module.sandbox_validate_cmd(update, context)

    patch_task_executor.create_task.assert_called_once()
    update.message.reply_text.assert_called_once_with("❌ Ошибка валидации изменений:\n\nvalidation failed")

def test_self_improve_cmd_new_suggestions(monkeypatch):
    update = AsyncMock()
    context = AsyncMock()
    # Очищаем сервис перед тестом
    bot_module.improvement_service.suggestions.clear()
    # Запускаем команду
    asyncio.run(bot_module.self_improve_cmd(update, context))
    # Проверяем, что сообщение содержит оба предложения
    reply_text = update.message.reply_text.call_args[0][0]
    assert "Оптимизировать обработку ошибок" in reply_text
    assert "Добавить больше автотестов" in reply_text
    assert "Новые предложения по улучшениям" in reply_text

def test_accept_and_reject_improvement(monkeypatch):
    update = AsyncMock()
    context = AsyncMock()
    # Очищаем сервис и добавляем предложение
    bot_module.improvement_service.suggestions.clear()
    suggestion = bot_module.improvement_service.generate_suggestions([
        {"recommendation": "Тестовое предложение для принятия."}
    ])[0]
    # Мокаем create_task, чтобы не требовать обязательные параметры
    fake_task = type("FakeTask", (), {"id": "test-task-id"})()
    monkeypatch.setattr(bot_module.task_executor, "create_task", lambda **kwargs: fake_task)
    # Проверяем принятие
    context.args = [suggestion.id]
    asyncio.run(bot_module.accept_improvement_cmd(update, context))
    assert bot_module.improvement_service.get_suggestion(suggestion.id).status == "accepted"
    reply_text = update.message.reply_text.call_args[0][0]
    assert "принято" in reply_text
    # Проверяем отклонение
    context.args = [suggestion.id]
    asyncio.run(bot_module.reject_improvement_cmd(update, context))
    assert bot_module.improvement_service.get_suggestion(suggestion.id).status == "rejected"
    reply_text = update.message.reply_text.call_args[0][0]
    assert "отклонено" in reply_text

def test_accept_improvement_creates_task(monkeypatch):
    update = AsyncMock()
    context = AsyncMock()
    # Очищаем сервис и добавляем предложение
    bot_module.improvement_service.suggestions.clear()
    suggestion = bot_module.improvement_service.generate_suggestions([
        {"recommendation": "Автотест: создать задачу по улучшению."}
    ])[0]
    context.args = [suggestion.id]
    # Мокаем create_task, чтобы не создавать реальную задачу
    fake_task = type("FakeTask", (), {"id": "test-task-id"})()
    monkeypatch.setattr(bot_module.task_executor, "create_task", lambda **kwargs: fake_task)
    asyncio.run(bot_module.accept_improvement_cmd(update, context))
    # Проверяем, что id задачи добавлен в history предложения
    assert "test-task-id" in suggestion.history
    # Проверяем, что бот сообщил о создании задачи
    reply_text = update.message.reply_text.call_args[0][0]
    assert "Автоматически создана задача" in reply_text
    assert "test-task-id" in reply_text
