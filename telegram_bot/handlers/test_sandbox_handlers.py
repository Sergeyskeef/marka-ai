import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_api.memory.memory_manager import MemoryManager
from langchain_api.sandbox.task_manager import TaskPriority
from langchain_api.telegram_bot.handlers.sandbox_handlers import SandboxHandler


class TestSandboxHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.memory_manager = MagicMock(spec=MemoryManager)
        self.handler = SandboxHandler(self.memory_manager)
        self.update = MagicMock()
        self.update.message.reply_text = AsyncMock()
        self.context = MagicMock()
        self.context.args = ["test_experiment"]

    @patch("langchain_api.telegram_bot.handlers.sandbox_handlers.MarkSelfAwareness")
    async def test_handle_self_analysis(self, MockAwareness):
        mock_awareness = MockAwareness.return_value
        mock_awareness.get_self_description.return_value = "desc"
        mock_awareness.analyze_project_structure.return_value = {"structure": 1}
        self.handler.mark_awareness = mock_awareness

        await self.handler.handle_self_analysis(self.update, self.context)
        self.memory_manager.add_message.assert_any_call(sender="self_analysis", message="desc")
        self.memory_manager.add_message.assert_any_call(sender="self_analysis_structure", message='{"structure": 1}')
        self.update.message.reply_text.assert_any_call("✅ Анализ завершен. Результаты сохранены в памяти.\nТеперь я лучше понимаю свою структуру и возможности.")

    @patch("langchain_api.telegram_bot.handlers.sandbox_handlers.MarkSelfAwareness")
    @patch("langchain_api.telegram_bot.handlers.sandbox_handlers.SandboxIntegrator")
    async def test_handle_sandbox_experiment(self, MockIntegrator, MockAwareness):
        mock_awareness = MockAwareness.return_value
        mock_awareness.analyze_project_structure.return_value = {"structure": 2}
        self.handler.mark_awareness = mock_awareness

        mock_integrator = MockIntegrator.return_value
        mock_integrator.create_experiment_task.return_value = "taskid"
        mock_integrator.run_experiment.return_value = {"result": 123}
        self.handler.sandbox_integrator = mock_integrator

        await self.handler.handle_sandbox_experiment(self.update, self.context)
        mock_integrator.create_experiment_task.assert_called_with(
            title="test_experiment",
            description="Эксперимент по анализу возможностей: test_experiment",
            priority=TaskPriority.HIGH
        )
        mock_integrator.run_experiment.assert_called_with(
            task_id="taskid",
            experiment_data={"analysis": {"structure": 2}, "focus": "test_experiment"}
        )
        self.memory_manager.add_message.assert_any_call(sender="sandbox_experiment", message='{"result": 123}')
        self.update.message.reply_text.assert_any_call("✅ Эксперимент 'test_experiment' завершен.\nРезультаты сохранены в памяти.")

if __name__ == "__main__":
    unittest.main()
