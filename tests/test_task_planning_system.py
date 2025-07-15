"""
Тесты для системы планирования и декомпозиции задач.
"""

import pytest
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from langchain_api.sandbox.task_planning_system import (
    TaskAnalyzer, TaskDecomposer, ComplexityEstimator, DependencyPlanner,
    TaskPlanningSystem, TaskRequirement, Subtask, TaskPlan, ComplexityMetrics,
    analyze_task_requirements, create_task_plan, estimate_task_complexity,
    get_task_plan, list_task_plans
)


class TestTaskAnalyzer:
    """Тесты для анализатора задач."""
    
    def setup_method(self):
        self.analyzer = TaskAnalyzer()
    
    def test_analyze_requirements_simple_task(self):
        """Тест анализа простой задачи."""
        description = "Создать простую функцию для вывода приветствия"
        requirements = self.analyzer.analyze_requirements(description)
        
        assert requirements.id.startswith("task_")
        assert requirements.description == description
        assert requirements.priority == "medium"
        assert requirements.complexity == "simple"
        assert requirements.estimated_time > 0
        assert isinstance(requirements.dependencies, list)
        assert isinstance(requirements.risks, list)
        assert isinstance(requirements.acceptance_criteria, list)
        assert isinstance(requirements.created_at, datetime)
    
    def test_analyze_requirements_complex_task(self):
        """Тест анализа сложной задачи."""
        description = "Разработать алгоритм машинного обучения для оптимизации производительности системы"
        requirements = self.analyzer.analyze_requirements(description)
        
        assert requirements.complexity == "complex"
        assert requirements.estimated_time > 8  # Должно быть больше для сложной задачи
    
    def test_analyze_requirements_high_priority(self):
        """Тест анализа задачи с высоким приоритетом."""
        description = "Критично важно исправить баг в системе безопасности"
        requirements = self.analyzer.analyze_requirements(description)
        
        assert requirements.priority == "high"
    
    def test_extract_dependencies(self):
        """Тест извлечения зависимостей."""
        description = "Интеграция с внешней системой API требует использования базы данных"
        requirements = self.analyzer.analyze_requirements(description)
        
        assert len(requirements.dependencies) > 0
        assert "api" in [dep.lower() for dep in requirements.dependencies]
    
    def test_analyze_risks(self):
        """Тест анализа рисков."""
        description = "Обработка чувствительных данных пользователей"
        requirements = self.analyzer.analyze_requirements(description)
        
        assert len(requirements.risks) > 0
        assert any("данн" in risk.lower() for risk in requirements.risks)


class TestTaskDecomposer:
    """Тесты для декомпозитора задач."""
    
    def setup_method(self):
        self.decomposer = TaskDecomposer()
        self.analyzer = TaskAnalyzer()
    
    def test_decompose_simple_task(self):
        """Тест декомпозиции простой задачи."""
        description = "Создать простую функцию"
        requirements = self.analyzer.analyze_requirements(description)
        subtasks = self.decomposer.decompose_task(requirements)
        
        assert len(subtasks) >= 4  # Минимум: анализ, разработка, тестирование, документация
        assert all(isinstance(subtask, Subtask) for subtask in subtasks)
        assert all(subtask.parent_task_id == requirements.id for subtask in subtasks)
    
    def test_decompose_complex_task(self):
        """Тест декомпозиции сложной задачи."""
        description = "Разработать сложную систему интеграции с машинным обучением"
        requirements = self.analyzer.analyze_requirements(description)
        subtasks = self.decomposer.decompose_task(requirements)
        
        # Сложная задача должна иметь больше подзадач
        assert len(subtasks) >= 5  # Включая проектирование
        assert any("Проектирование" in subtask.title for subtask in subtasks)
    
    def test_subtask_dependencies(self):
        """Тест зависимостей между подзадачами."""
        description = "Создать API с тестированием"
        requirements = self.analyzer.analyze_requirements(description)
        subtasks = self.decomposer.decompose_task(requirements)
        
        # Проверяем, что есть задачи с зависимостями
        tasks_with_deps = [task for task in subtasks if task.dependencies]
        assert len(tasks_with_deps) > 0


class TestComplexityEstimator:
    """Тесты для оценщика сложности."""
    
    def setup_method(self):
        self.estimator = ComplexityEstimator()
    
    def test_estimate_complexity_simple(self):
        """Тест оценки сложности простой задачи."""
        description = "Показать список пользователей"
        estimation = self.estimator.estimate_complexity(description)
        
        assert "overall_complexity" in estimation
        assert "confidence" in estimation
        assert "factors" in estimation
        assert "recommendations" in estimation
        assert estimation["overall_complexity"] in ["simple", "medium", "complex"]
    
    def test_estimate_complexity_with_metrics(self):
        """Тест оценки сложности с метриками кода."""
        description = "Оптимизировать алгоритм"
        metrics = ComplexityMetrics(
            lines_of_code=100,
            cyclomatic_complexity=3,
            cognitive_complexity=2,
            technical_debt=0.1,
            test_coverage=0.8,
            documentation_coverage=0.7
        )
        
        estimation = self.estimator.estimate_complexity(description, metrics)
        assert "factors" in estimation
        assert len(estimation["factors"]) > 1  # Должно быть больше факторов
    
    def test_generate_recommendations(self):
        """Тест генерации рекомендаций."""
        description = "Разработать сложную систему машинного обучения"
        estimation = self.estimator.estimate_complexity(description)
        
        assert len(estimation["recommendations"]) > 0
        assert all(isinstance(rec, str) for rec in estimation["recommendations"])


class TestDependencyPlanner:
    """Тесты для планировщика зависимостей."""
    
    def setup_method(self):
        self.planner = DependencyPlanner()
    
    def test_create_dependency_graph(self):
        """Тест создания графа зависимостей."""
        tasks = [
            TaskRequirement(
                id="task1", description="Task 1", priority="high", complexity="simple",
                estimated_time=2, dependencies=[], risks=[], acceptance_criteria=[],
                created_at=datetime.now()
            ),
            TaskRequirement(
                id="task2", description="Task 2", priority="medium", complexity="medium",
                estimated_time=4, dependencies=["task1"], risks=[], acceptance_criteria=[],
                created_at=datetime.now()
            )
        ]
        
        graph = self.planner.create_dependency_graph(tasks)
        assert "task1" in graph
        assert "task2" in graph
        assert graph["task2"] == ["task1"]
    
    def test_find_critical_path(self):
        """Тест поиска критического пути."""
        subtasks = [
            Subtask(
                id="sub1", title="Analysis", description="Analysis", parent_task_id="task1",
                priority="high", complexity="simple", estimated_time=2, dependencies=[],
                status="pending", created_at=datetime.now()
            ),
            Subtask(
                id="sub2", title="Development", description="Development", parent_task_id="task1",
                priority="high", complexity="medium", estimated_time=8, dependencies=["sub1"],
                status="pending", created_at=datetime.now()
            )
        ]
        
        critical_path = self.planner.find_critical_path(subtasks)
        assert len(critical_path) > 0
        assert "sub1" in critical_path
        assert "sub2" in critical_path
    
    def test_detect_circular_dependencies(self):
        """Тест обнаружения циклических зависимостей."""
        graph = {
            "task1": ["task2"],
            "task2": ["task3"],
            "task3": ["task1"]
        }
        
        circular = self.planner.detect_circular_dependencies(graph)
        assert len(circular) > 0
        assert any("task1" in cycle for cycle in circular)
    
    def test_optimize_execution_order(self):
        """Тест оптимизации порядка выполнения."""
        subtasks = [
            Subtask(
                id="sub1", title="Analysis", description="Analysis", parent_task_id="task1",
                priority="high", complexity="simple", estimated_time=2, dependencies=[],
                status="pending", created_at=datetime.now()
            ),
            Subtask(
                id="sub2", title="Development", description="Development", parent_task_id="task1",
                priority="high", complexity="medium", estimated_time=8, dependencies=["sub1"],
                status="pending", created_at=datetime.now()
            )
        ]
        
        parallel_groups = self.planner.optimize_execution_order(subtasks)
        assert len(parallel_groups) > 0
        assert "sub1" in parallel_groups[0]  # Первая группа должна содержать независимые задачи


class TestTaskPlanningSystem:
    """Тесты для основной системы планирования."""
    
    def setup_method(self):
        self.system = TaskPlanningSystem()
        # Очищаем файл планов перед тестами
        if self.system.plans_file.exists():
            self.system.plans_file.unlink()
    
    def test_create_task_plan(self):
        """Тест создания плана задачи."""
        description = "Создать API для управления пользователями"
        plan = self.system.create_task_plan(description)
        
        assert isinstance(plan, TaskPlan)
        assert plan.task_id.startswith("task_")
        assert plan.description == description
        assert len(plan.subtasks) > 0
        assert len(plan.critical_path) > 0
        assert plan.total_estimated_time > 0
        assert len(plan.parallel_tasks) > 0
        assert isinstance(plan.risks, list)
        assert isinstance(plan.mitigation_strategies, list)
    
    def test_save_and_load_plan(self):
        """Тест сохранения и загрузки плана."""
        description = "Тестовая задача"
        plan = self.system.create_task_plan(description)
        
        # Загружаем план
        loaded_plan = self.system.get_plan(plan.task_id)
        assert loaded_plan is not None
        assert loaded_plan.task_id == plan.task_id
        assert loaded_plan.description == plan.description
    
    def test_list_plans(self):
        """Тест получения списка планов."""
        # Создаем несколько планов
        self.system.create_task_plan("Задача 1")
        self.system.create_task_plan("Задача 2")
        
        plans = self.system.list_plans()
        assert len(plans) == 2
        assert all("task_id" in plan for plan in plans)
        assert all("title" in plan for plan in plans)
    
    def test_generate_mitigation_strategies(self):
        """Тест генерации стратегий снижения рисков."""
        risks = ["Высокая сложность может привести к задержкам"]
        strategies = self.system._generate_mitigation_strategies(risks)
        
        assert len(strategies) > 0
        assert all(isinstance(strategy, str) for strategy in strategies)


class TestIntegrationFunctions:
    """Тесты для функций интеграции с OpenAI Tools API."""
    
    def setup_method(self):
        # Очищаем файл планов перед тестами
        plans_file = Path("sandbox/task_plans.json")
        if plans_file.exists():
            plans_file.unlink()
    
    def test_analyze_task_requirements_function(self):
        """Тест функции анализа требований."""
        description = "Создать простую функцию"
        result = analyze_task_requirements(description)
        
        assert isinstance(result, dict)
        assert "id" in result
        assert "description" in result
        assert "priority" in result
        assert "complexity" in result
    
    def test_create_task_plan_function(self):
        """Тест функции создания плана."""
        description = "Разработать систему уведомлений"
        result = create_task_plan(description)
        
        assert isinstance(result, dict)
        assert "task_id" in result
        assert "subtasks" in result
        assert "critical_path" in result
    
    def test_estimate_task_complexity_function(self):
        """Тест функции оценки сложности."""
        description = "Оптимизировать алгоритм"
        result = estimate_task_complexity(description)
        
        assert isinstance(result, dict)
        assert "overall_complexity" in result
        assert "recommendations" in result
    
    def test_get_task_plan_function(self):
        """Тест функции получения плана."""
        # Сначала создаем план
        description = "Тестовая задача"
        create_result = create_task_plan(description)
        task_id = create_result["task_id"]
        
        # Получаем план
        result = get_task_plan(task_id)
        assert isinstance(result, dict)
        assert result["task_id"] == task_id
    
    def test_list_task_plans_function(self):
        """Тест функции получения списка планов."""
        # Создаем несколько планов
        create_task_plan("Задача 1")
        create_task_plan("Задача 2")
        
        result = list_task_plans()
        assert isinstance(result, dict)
        assert "plans" in result
        assert "count" in result
        assert result["count"] == 2


class TestDataStructures:
    """Тесты для структур данных."""
    
    def test_task_requirement_creation(self):
        """Тест создания объекта TaskRequirement."""
        requirement = TaskRequirement(
            id="test_id",
            description="Test description",
            priority="high",
            complexity="medium",
            estimated_time=8,
            dependencies=["dep1", "dep2"],
            risks=["risk1"],
            acceptance_criteria=["criteria1"],
            created_at=datetime.now()
        )
        
        assert requirement.id == "test_id"
        assert requirement.description == "Test description"
        assert requirement.priority == "high"
        assert requirement.complexity == "medium"
        assert requirement.estimated_time == 8
        assert len(requirement.dependencies) == 2
        assert len(requirement.risks) == 1
        assert len(requirement.acceptance_criteria) == 1
    
    def test_subtask_creation(self):
        """Тест создания объекта Subtask."""
        subtask = Subtask(
            id="sub1",
            title="Test Subtask",
            description="Test description",
            parent_task_id="task1",
            priority="medium",
            complexity="simple",
            estimated_time=4,
            dependencies=[],
            status="pending",
            created_at=datetime.now()
        )
        
        assert subtask.id == "sub1"
        assert subtask.title == "Test Subtask"
        assert subtask.parent_task_id == "task1"
        assert subtask.status == "pending"
    
    def test_task_plan_creation(self):
        """Тест создания объекта TaskPlan."""
        plan = TaskPlan(
            task_id="task1",
            title="Test Plan",
            description="Test description",
            subtasks=[],
            critical_path=["sub1"],
            total_estimated_time=10,
            parallel_tasks=[["sub1"]],
            risks=["risk1"],
            mitigation_strategies=["strategy1"],
            created_at=datetime.now()
        )
        
        assert plan.task_id == "task1"
        assert plan.title == "Test Plan"
        assert len(plan.critical_path) == 1
        assert plan.total_estimated_time == 10
        assert len(plan.parallel_tasks) == 1
        assert len(plan.risks) == 1
        assert len(plan.mitigation_strategies) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 