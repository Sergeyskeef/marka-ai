import pytest
from unittest import TestCase
from langchain_api.sandbox.sandbox_manager import SandboxManager
from langchain_api.sandbox.self_awareness import MarkSelfAwareness
from langchain_api.services.security import SecurityManager

class TestSandboxManagement(TestCase):
    def setUp(self):
        self.sandbox_manager = SandboxManager()
        self.self_awareness = MarkSelfAwareness()
        self.security_manager = SecurityManager()

    def test_sandbox_creation(self):
        """Тест создания изолированной песочницы"""
        sandbox = self.sandbox_manager.create_sandbox()
        self.assertIsNotNone(sandbox)
        self.assertTrue(self.sandbox_manager.is_sandbox_active(sandbox.id))

    def test_command_execution(self):
        """Тест выполнения команд в песочнице"""
        sandbox = self.sandbox_manager.create_sandbox()
        result = self.sandbox_manager.execute_command(sandbox.id, "echo 'test'")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output.strip(), "test")

    def test_diff_creation(self):
        """Тест создания диффа изменений"""
        sandbox = self.sandbox_manager.create_sandbox()
        self.sandbox_manager.execute_command(sandbox.id, "echo 'test' > test.txt")
        diff = self.sandbox_manager.create_diff(sandbox.id)
        self.assertIsNotNone(diff)
        # Проверяем наличие файла в выводе ls
        ls_output = self.sandbox_manager.execute_command(sandbox.id, "ls -la").output
        self.assertIn("test.txt", ls_output)

    def test_changes_validation(self):
        """Тест валидации изменений"""
        sandbox = self.sandbox_manager.create_sandbox()
        self.sandbox_manager.execute_command(sandbox.id, "echo 'test' > test.txt")
        is_valid = self.sandbox_manager.validate_changes(sandbox.id)
        self.assertTrue(is_valid)

    def test_automatic_rollback(self):
        """Тест автоматического отката изменений"""
        sandbox = self.sandbox_manager.create_sandbox()
        snapshot_id = self.sandbox_manager.create_snapshot(sandbox.id)
        self.sandbox_manager.execute_command(sandbox.id, "rm -rf /")
        self.sandbox_manager.rollback(sandbox.id, snapshot_id)
        self.assertTrue(self.sandbox_manager.is_sandbox_active(sandbox.id))

    def test_parallel_sandboxes(self):
        """Тест параллельной работы нескольких песочниц"""
        sandbox1 = self.sandbox_manager.create_sandbox()
        sandbox2 = self.sandbox_manager.create_sandbox()
        self.sandbox_manager.execute_command(sandbox1.id, "echo 'test1' > test1.txt")
        self.sandbox_manager.execute_command(sandbox2.id, "echo 'test2' > test2.txt")
        self.assertTrue(self.sandbox_manager.is_sandbox_active(sandbox1.id))
        self.assertTrue(self.sandbox_manager.is_sandbox_active(sandbox2.id))

    def test_resource_limits(self):
        """Тест ограничений ресурсов"""
        sandbox = self.sandbox_manager.create_sandbox()
        # Запускаем команду, которая должна быть прервана по таймауту
        result = self.sandbox_manager.execute_command(sandbox.id, "while true; do : ; done")
        self.assertEqual(result.status, "failed")
        self.assertIn("timed out", result.error)

    def test_sandbox_cleanup(self):
        """Тест очистки песочницы"""
        sandbox = self.sandbox_manager.create_sandbox()
        self.sandbox_manager.cleanup(sandbox.id)
        self.assertFalse(self.sandbox_manager.is_sandbox_active(sandbox.id))

class TestExtendedSelfAnalysis(TestCase):
    def setUp(self):
        self.sandbox_manager = SandboxManager()
        self.self_awareness = MarkSelfAwareness()

    def test_task_analysis_in_sandbox(self):
        """Тест анализа задач в песочнице"""
        sandbox = self.sandbox_manager.create_sandbox()
        result = self.sandbox_manager.execute_command(sandbox.id, "echo 'test'")
        analysis = self.self_awareness.analyze_task_execution(result)
        self.assertIsNotNone(analysis)
        self.assertGreaterEqual(analysis.success_rate, 0.0)

    def test_performance_analysis(self):
        """Тест анализа производительности"""
        sandbox = self.sandbox_manager.create_sandbox()
        result = self.sandbox_manager.execute_command(sandbox.id, "sleep 1")
        analysis = self.self_awareness.analyze_task_execution(result)
        self.assertIsNotNone(analysis.performance_score)
        self.assertIsNotNone(analysis.resource_efficiency)

    def test_error_analysis(self):
        """Тест анализа ошибок"""
        sandbox = self.sandbox_manager.create_sandbox()
        result = self.sandbox_manager.execute_command(sandbox.id, "invalid_command")
        analysis = self.self_awareness.analyze_task_execution(result)
        self.assertIsNotNone(analysis.error_patterns)
        self.assertGreater(len(analysis.recommendations), 0)

    def test_learning_from_experience(self):
        """Тест обучения на основе опыта"""
        sandbox = self.sandbox_manager.create_sandbox()
        for _ in range(3):
            result = self.sandbox_manager.execute_command(sandbox.id, "echo 'test'")
            self.self_awareness.analyze_task_execution(result)
        insights = self.self_awareness.get_recent_insights(limit=3)
        self.assertEqual(len(insights), 3)

    def test_recommendation_generation(self):
        """Тест генерации рекомендаций"""
        sandbox = self.sandbox_manager.create_sandbox()
        result = self.sandbox_manager.execute_command(sandbox.id, "sleep 2")
        analysis = self.self_awareness.analyze_task_execution(result)
        recommendations = self.self_awareness.get_task_recommendations(result)
        self.assertGreater(len(recommendations), 0)
        # Проверяем, что рекомендации содержат полезную информацию
        self.assertTrue(any("рекомендуется" in rec.lower() for rec in recommendations)) 