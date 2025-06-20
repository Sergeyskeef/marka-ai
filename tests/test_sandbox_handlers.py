import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_api.telegram_bot.handlers.sandbox_handlers import SandboxHandler
from langchain_api.memory.memory_manager import MemoryManager
from langchain_api.sandbox.task_manager import TaskPriority
import asyncio

@pytest.mark.asyncio
@patch("langchain_api.telegram_bot.handlers.sandbox_handlers.MarkSelfAwareness")
async def test_handle_self_analysis(MockAwareness):
    memory_manager = MagicMock(spec=MemoryManager)
    handler = SandboxHandler(memory_manager)
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    
    mock_awareness = MockAwareness.return_value
    mock_awareness.get_self_description.return_value = "desc"
    mock_awareness.analyze_project_structure.return_value = {"structure": 1}
    handler.mark_awareness = mock_awareness

    await handler.handle_self_analysis(update, context)
    memory_manager.add_message.assert_any_call(sender="self_analysis", message="desc")
    memory_manager.add_message.assert_any_call(sender="self_analysis_structure", message='{"structure": 1}')
    update.message.reply_text.assert_any_call("✅ Анализ завершен. Результаты сохранены в памяти.\nТеперь я лучше понимаю свою структуру и возможности.")

@pytest.mark.asyncio
@patch("langchain_api.telegram_bot.handlers.sandbox_handlers.MarkSelfAwareness")
@patch("langchain_api.telegram_bot.handlers.sandbox_handlers.SandboxIntegrator")
async def test_handle_sandbox_experiment(MockIntegrator, MockAwareness):
    memory_manager = MagicMock(spec=MemoryManager)
    handler = SandboxHandler(memory_manager)
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["test_experiment"]

    mock_awareness = MockAwareness.return_value
    mock_awareness.analyze_project_structure.return_value = {"structure": 2}
    handler.mark_awareness = mock_awareness

    mock_integrator = MockIntegrator.return_value
    mock_integrator.create_experiment_task.return_value = "taskid"
    mock_integrator.run_experiment.return_value = {"result": 123}
    handler.sandbox_integrator = mock_integrator

    await handler.handle_sandbox_experiment(update, context)
    mock_integrator.create_experiment_task.assert_called_with(
        title="test_experiment",
        description="Эксперимент по анализу возможностей: test_experiment",
        priority=TaskPriority.HIGH
    )
    mock_integrator.run_experiment.assert_called_with(
        task_id="taskid",
        experiment_data={"analysis": {"structure": 2}, "focus": "test_experiment"}
    )
    memory_manager.add_message.assert_any_call(sender="sandbox_experiment", message='{"result": 123}')
    update.message.reply_text.assert_any_call("✅ Эксперимент 'test_experiment' завершен.\nРезультаты сохранены в памяти.") 