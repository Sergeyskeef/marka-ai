"""
Тесты для системы автономной разработки

Автор: Марк (Автономная система разработки)
Дата создания: 2025-01-07
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Добавляем путь к модулю для импорта
sys.path.append(str(Path(__file__).parent.parent))

from sandbox.autonomous_development_system import (
    TaskAnalyzer,
    AutonomousDevelopmentSystem,
    TaskRequirements,
    ImplementationPlan,
    CodeQualityReport,
    TestReport,
    CodeReviewReport
)


class TestTaskAnalyzer:
    """Тесты для TaskAnalyzer"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        with patch('sandbox.autonomous_development_system.ReflectionManager'):
            self.analyzer = TaskAnalyzer()
    
    def test_analyze_task(self):
        """Тест анализа задачи"""
        task_description = "Создать систему логирования"
        
        requirements = self.analyzer.analyze_task(task_description)
        
        assert isinstance(requirements, TaskRequirements)
        assert requirements.title == "Создать систему"
        assert requirements.description == task_description
        assert requirements.complexity in ["low", "medium", "high"]
        assert requirements.priority in ["low", "medium", "high", "critical"]
        assert isinstance(requirements.dependencies, list)
        assert isinstance(requirements.risks, list)
        assert isinstance(requirements.acceptance_criteria, list)
    
    def test_decompose_task(self):
        """Тест декомпозиции задачи"""
        requirements = TaskRequirements(
            title="Test Task",
            description="Test description",
            complexity="medium",
            estimated_time="4-8 часов",
            dependencies=[],
            risks=[],
            acceptance_criteria=[],
            priority="medium"
        )
        
        sub_tasks = self.analyzer.decompose_task(requirements)
        
        assert isinstance(sub_tasks, list)
        assert len(sub_tasks) >= 3  # Должно быть минимум 3 подзадачи
        
        # Проверяем наличие основных подзадач
        task_titles = [task["title"] for task in sub_tasks]
        assert "Планирование и анализ" in task_titles
        assert "Реализация" in task_titles
        assert "Тестирование" in task_titles
    
    def test_create_basic_requirements(self):
        """Тест создания базовых требований"""
        description = "Создать простую функцию"
        
        requirements = self.analyzer._create_basic_requirements(description)
        
        assert isinstance(requirements, TaskRequirements)
        assert requirements.title == "Создать простую"
        assert requirements.description == description
        assert requirements.complexity == "medium"
        assert requirements.priority == "medium"


class TestAutonomousDevelopmentSystem:
    """Тесты для AutonomousDevelopmentSystem"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        with patch('sandbox.autonomous_development_system.TaskAnalyzer'):
            with patch('sandbox.autonomous_development_system.ReflectionManager'):
                self.system = AutonomousDevelopmentSystem()
    
    def test_develop_feature(self):
        """Тест разработки функции"""
        task_description = "Создать калькулятор"
        
        with patch.object(self.system.task_analyzer, 'analyze_task') as mock_analyze:
            with patch.object(self.system.task_analyzer, 'decompose_task') as mock_decompose:
                with patch.object(self.system, '_create_development_reflection') as mock_reflection:
                    
                    # Настраиваем моки
                    mock_requirements = TaskRequirements(
                        title="Калькулятор",
                        description=task_description,
                        complexity="medium",
                        estimated_time="4-8 часов",
                        dependencies=[],
                        risks=[],
                        acceptance_criteria=[],
                        priority="medium"
                    )
                    mock_analyze.return_value = mock_requirements
                    
                    mock_sub_tasks = [
                        {"id": "planning", "title": "Планирование", "description": "План", "estimated_time": "1 час", "dependencies": [], "priority": "high"}
                    ]
                    mock_decompose.return_value = mock_sub_tasks
                    
                    # Выполняем тест
                    result = self.system.develop_feature(task_description)
                    
                    # Проверяем результат
                    assert isinstance(result, dict)
                    assert result["task_description"] == task_description
                    assert result["status"] == "analysis_completed"
                    assert "completion_time" in result
                    assert "requirements" in result
                    assert "sub_tasks" in result
                    
                    # Проверяем вызовы методов
                    mock_analyze.assert_called_once_with(task_description)
                    mock_decompose.assert_called_once_with(mock_requirements)
                    mock_reflection.assert_called_once()


class TestDataClasses:
    """Тесты для dataclass структур"""
    
    def test_task_requirements(self):
        """Тест TaskRequirements"""
        requirements = TaskRequirements(
            title="Test",
            description="Test description",
            complexity="medium",
            estimated_time="4-8 часов",
            dependencies=["dep1", "dep2"],
            risks=["risk1"],
            acceptance_criteria=["criteria1"],
            priority="high"
        )
        
        assert requirements.title == "Test"
        assert requirements.complexity == "medium"
        assert len(requirements.dependencies) == 2
        assert len(requirements.risks) == 1
        assert len(requirements.acceptance_criteria) == 1
        assert requirements.priority == "high"
    
    def test_implementation_plan(self):
        """Тест ImplementationPlan"""
        plan = ImplementationPlan(
            task_id="task_123",
            phases=[{"name": "Phase 1", "duration": "1 hour"}],
            timeline={"start": "2025-01-07", "end": "2025-01-08"},
            resources_needed=["resource1"],
            milestones=[{"name": "Milestone 1", "date": "2025-01-07"}],
            risk_mitigation=[{"risk": "Risk 1", "mitigation": "Mitigation 1"}]
        )
        
        assert plan.task_id == "task_123"
        assert len(plan.phases) == 1
        assert len(plan.resources_needed) == 1
        assert len(plan.milestones) == 1
        assert len(plan.risk_mitigation) == 1
    
    def test_code_quality_report(self):
        """Тест CodeQualityReport"""
        report = CodeQualityReport(
            syntax_score=8.5,
            security_score=9.0,
            maintainability_score=8.0,
            test_coverage=85.5,
            issues=[{"type": "warning", "message": "Test warning"}],
            recommendations=["Add more comments"]
        )
        
        assert report.syntax_score == 8.5
        assert report.security_score == 9.0
        assert report.maintainability_score == 8.0
        assert report.test_coverage == 85.5
        assert len(report.issues) == 1
        assert len(report.recommendations) == 1
    
    def test_test_report(self):
        """Тест TestReport"""
        report = TestReport(
            total_tests=10,
            passed_tests=9,
            failed_tests=1,
            coverage_percentage=90.0,
            test_duration=5.5,
            issues=[{"test": "test_1", "error": "Assertion failed"}]
        )
        
        assert report.total_tests == 10
        assert report.passed_tests == 9
        assert report.failed_tests == 1
        assert report.coverage_percentage == 90.0
        assert report.test_duration == 5.5
        assert len(report.issues) == 1
    
    def test_code_review_report(self):
        """Тест CodeReviewReport"""
        report = CodeReviewReport(
            overall_score=8.5,
            code_quality={"readability": 8.0, "maintainability": 9.0},
            suggestions=["Add more comments"],
            critical_issues=[],
            approved=True
        )
        
        assert report.overall_score == 8.5
        assert len(report.code_quality) == 2
        assert len(report.suggestions) == 1
        assert len(report.critical_issues) == 0
        assert report.approved is True


class TestIntegration:
    """Интеграционные тесты"""
    
    def test_full_workflow(self):
        """Тест полного рабочего процесса"""
        with patch('sandbox.autonomous_development_system.ReflectionManager'):
            system = AutonomousDevelopmentSystem()
            
            task_description = "Создать простой API endpoint"
            
            # Выполняем полный цикл разработки
            result = system.develop_feature(task_description)
            
            # Проверяем структуру результата
            assert isinstance(result, dict)
            assert "task_description" in result
            assert "requirements" in result
            assert "sub_tasks" in result
            assert "status" in result
            assert "completion_time" in result
            
            # Проверяем типы данных
            assert isinstance(result["requirements"], dict)
            assert isinstance(result["sub_tasks"], list)
            assert isinstance(result["status"], str)
            assert isinstance(result["completion_time"], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 