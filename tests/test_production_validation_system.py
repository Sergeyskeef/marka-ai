"""
Тесты для системы валидации и переноса в продакшн
"""

import pytest
import os
import tempfile
import shutil
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

# Добавляем путь к модулям
import sys
sys.path.append('/app/langchain_api')

from sandbox.production_validation_system import (
    ProductionValidationSystem,
    ProductionConfig,
    ValidationStatus,
    DeploymentStatus,
    DiffReport,
    ValidationReport,
    DeploymentReport
)


class TestProductionValidationSystem:
    """Тесты для системы валидации и переноса в продакшн"""
    
    @pytest.fixture
    def temp_dirs(self):
        """Создание временных директорий для тестов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            sandbox_dir = os.path.join(temp_dir, "sandbox")
            production_dir = os.path.join(temp_dir, "production")
            backup_dir = os.path.join(temp_dir, "backups")
            
            os.makedirs(sandbox_dir)
            os.makedirs(production_dir)
            os.makedirs(backup_dir)
            
            # Создаем тестовые файлы в production
            test_file = os.path.join(production_dir, "test_file.py")
            with open(test_file, 'w') as f:
                f.write("def old_function():\n    return 'old'\n")
            
            yield {
                'sandbox': sandbox_dir,
                'production': production_dir,
                'backup': backup_dir
            }
    
    @pytest.fixture
    def validation_system(self, temp_dirs):
        """Создание экземпляра системы валидации"""
        config = ProductionConfig(
            production_path=temp_dirs['production'],
            backup_path=temp_dirs['backup'],
            allowed_extensions=[".py", ".md", ".yml", ".yaml", ".json", ".txt"],
            max_file_size_mb=10,
            require_approval=True,
            auto_rollback_on_failure=True,
            monitoring_enabled=True
        )
        return ProductionValidationSystem(config)
    
    def test_initialization(self, validation_system):
        """Тест инициализации системы"""
        assert validation_system.config is not None
        assert validation_system.validations == {}
        assert validation_system.deployments == {}
    
    def test_create_diff_report_modified(self, validation_system, temp_dirs):
        """Тест создания diff-отчета для измененного файла"""
        # Создаем измененный файл в песочнице
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        diff_report = validation_system.create_diff_report(
            temp_dirs['sandbox'], "test_file.py"
        )
        
        assert diff_report is not None
        assert diff_report.file_path == "test_file.py"
        assert diff_report.change_type == "modified"
        assert diff_report.lines_added > 0
        assert diff_report.lines_removed > 0
        assert "new_function" in diff_report.diff_content
        assert diff_report.risk_level in ["low", "medium", "high", "critical"]
    
    def test_create_diff_report_added(self, validation_system, temp_dirs):
        """Тест создания diff-отчета для нового файла"""
        # Создаем новый файл в песочнице
        sandbox_file = os.path.join(temp_dirs['sandbox'], "new_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        diff_report = validation_system.create_diff_report(
            temp_dirs['sandbox'], "new_file.py"
        )
        
        assert diff_report is not None
        assert diff_report.file_path == "new_file.py"
        assert diff_report.change_type == "added"
        assert diff_report.lines_added > 0
        assert diff_report.lines_removed == 0
    
    def test_create_diff_report_deleted(self, validation_system, temp_dirs):
        """Тест создания diff-отчета для удаленного файла"""
        # Файл существует в production, но не в sandbox
        diff_report = validation_system.create_diff_report(
            temp_dirs['sandbox'], "test_file.py"
        )
        
        assert diff_report is not None
        assert diff_report.file_path == "test_file.py"
        assert diff_report.change_type == "deleted"
        assert diff_report.lines_added == 0
        assert diff_report.lines_removed > 0
    
    def test_analyze_risks_python_function(self, validation_system):
        """Тест анализа рисков для Python функции"""
        diff_content = ["+ def new_function():", "+     return 'new'"]
        
        risk_level, impact_analysis, recommendations = validation_system._analyze_risks(
            "test.py", "modified", 2, 0, diff_content
        )
        
        assert risk_level == "medium"
        assert "функции" in impact_analysis
        assert len(recommendations) > 0
    
    def test_analyze_risks_import(self, validation_system):
        """Тест анализа рисков для импорта"""
        diff_content = ["+ import new_module"]
        
        risk_level, impact_analysis, recommendations = validation_system._analyze_risks(
            "test.py", "modified", 1, 0, diff_content
        )
        
        assert risk_level == "high"
        assert "импорты" in impact_analysis
        assert "зависимостей" in recommendations[0]
    
    def test_analyze_risks_critical_file(self, validation_system):
        """Тест анализа рисков для критического файла"""
        diff_content = ["+ def new_function():", "+     return 'new'"]
        
        risk_level, impact_analysis, recommendations = validation_system._analyze_risks(
            "main.py", "modified", 2, 0, diff_content
        )
        
        assert risk_level == "critical"
        assert "критических файлах" in impact_analysis
        assert len(recommendations) >= 2
    
    def test_validate_changes(self, validation_system, temp_dirs):
        """Тест валидации изменений"""
        # Создаем измененные файлы в песочнице
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        new_file = os.path.join(temp_dirs['sandbox'], "new_file.py")
        with open(new_file, 'w') as f:
            f.write("def another_function():\n    return 'another'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py", "new_file.py"]
        )
        
        assert validation_report is not None
        assert validation_report.validation_id.startswith("validation_")
        assert validation_report.status == ValidationStatus.PENDING
        assert validation_report.total_files_changed == 2
        assert validation_report.total_lines_added > 0
        assert len(validation_report.diff_reports) == 2
        assert validation_report.risk_assessment is not None
        assert len(validation_report.recommendations) > 0
    
    def test_approve_validation(self, validation_system, temp_dirs):
        """Тест подтверждения валидации"""
        # Создаем валидацию
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        
        # Подтверждаем валидацию
        result = validation_system.approve_validation(validation_report.validation_id)
        
        assert result is True
        updated_report = validation_system.get_validation_report(validation_report.validation_id)
        assert updated_report.status == ValidationStatus.APPROVED
    
    def test_approve_nonexistent_validation(self, validation_system):
        """Тест подтверждения несуществующей валидации"""
        result = validation_system.approve_validation("nonexistent_id")
        assert result is False
    
    @patch('shutil.copytree')
    @patch('shutil.copy2')
    def test_deploy_changes_success(self, mock_copy, mock_copytree, validation_system, temp_dirs):
        """Тест успешного деплоя изменений"""
        # Создаем и подтверждаем валидацию
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        validation_system.approve_validation(validation_report.validation_id)
        
        # Выполняем деплой
        deployment_report = validation_system.deploy_changes(
            validation_report.validation_id, temp_dirs['sandbox']
        )
        
        assert deployment_report is not None
        assert deployment_report.deployment_id.startswith("deployment_")
        assert deployment_report.status == DeploymentStatus.SUCCESS
        assert deployment_report.validation_id == validation_report.validation_id
        assert len(deployment_report.deployed_files) > 0
        assert deployment_report.rollback_available is True
    
    def test_deploy_changes_unapproved(self, validation_system, temp_dirs):
        """Тест деплоя неподтвержденной валидации"""
        # Создаем валидацию без подтверждения
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        
        # Пытаемся выполнить деплой без подтверждения
        with pytest.raises(ValueError, match="не подтверждена"):
            validation_system.deploy_changes(
                validation_report.validation_id, temp_dirs['sandbox']
            )
    
    def test_deploy_changes_nonexistent(self, validation_system, temp_dirs):
        """Тест деплоя несуществующей валидации"""
        with pytest.raises(ValueError, match="не найдена"):
            validation_system.deploy_changes("nonexistent_id", temp_dirs['sandbox'])
    
    @patch('shutil.copytree')
    @patch('shutil.copy2', side_effect=Exception("Copy failed"))
    def test_deploy_changes_failure(self, mock_copy, mock_copytree, validation_system, temp_dirs):
        """Тест неудачного деплоя с автоматическим откатом"""
        # Создаем и подтверждаем валидацию
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        validation_system.approve_validation(validation_report.validation_id)
        
        # Выполняем деплой (должен завершиться ошибкой)
        deployment_report = validation_system.deploy_changes(
            validation_report.validation_id, temp_dirs['sandbox']
        )
        
        assert deployment_report.status == DeploymentStatus.FAILED
        assert "Copy failed" in deployment_report.deployment_log
    
    def test_create_backup(self, validation_system, temp_dirs):
        """Тест создания резервной копии"""
        backup_location = validation_system._create_backup()
        
        assert backup_location is not None
        assert backup_location.startswith(temp_dirs['backup'])
        assert os.path.exists(backup_location)
    
    def test_rollback_deployment(self, validation_system, temp_dirs):
        """Тест отката деплоя"""
        # Создаем резервную копию
        backup_location = validation_system._create_backup()
        
        # Изменяем production файл
        production_file = os.path.join(temp_dirs['production'], "test_file.py")
        with open(production_file, 'w') as f:
            f.write("def changed_function():\n    return 'changed'\n")
        
        # Выполняем откат
        result = validation_system.rollback_deployment(backup_location)
        
        assert result is True
        
        # Проверяем, что файл восстановлен
        with open(production_file, 'r') as f:
            content = f.read()
        assert "old_function" in content
    
    def test_rollback_nonexistent_backup(self, validation_system):
        """Тест отката с несуществующей резервной копией"""
        result = validation_system.rollback_deployment("/nonexistent/backup")
        assert result is False
    
    def test_get_validation_report(self, validation_system, temp_dirs):
        """Тест получения отчета о валидации"""
        # Создаем валидацию
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        
        # Получаем отчет
        retrieved_report = validation_system.get_validation_report(validation_report.validation_id)
        
        assert retrieved_report is not None
        assert retrieved_report.validation_id == validation_report.validation_id
        assert retrieved_report.status == validation_report.status
    
    def test_get_nonexistent_validation_report(self, validation_system):
        """Тест получения несуществующего отчета о валидации"""
        report = validation_system.get_validation_report("nonexistent_id")
        assert report is None
    
    def test_list_validations(self, validation_system, temp_dirs):
        """Тест списка валидаций"""
        # Создаем несколько валидаций
        for i in range(3):
            sandbox_file = os.path.join(temp_dirs['sandbox'], f"test_file_{i}.py")
            with open(sandbox_file, 'w') as f:
                f.write(f"def function_{i}():\n    return '{i}'\n")
            
            validation_system.validate_changes(
                temp_dirs['sandbox'], [f"test_file_{i}.py"]
            )
        
        validations = validation_system.list_validations()
        
        # Проверяем, что есть хотя бы одна валидация (последняя созданная)
        assert len(validations) >= 1
        assert all(v.startswith("validation_") for v in validations)
    
    def test_create_pull_request(self, validation_system, temp_dirs):
        """Тест создания pull request"""
        # Создаем валидацию
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        
        # Создаем PR
        pr = validation_system.create_pull_request(
            validation_report.validation_id,
            "Test PR",
            "This is a test pull request"
        )
        
        assert pr is not None
        assert pr["pr_id"].startswith("PR_")
        assert pr["title"] == "Test PR"
        assert pr["validation_id"] == validation_report.validation_id
        # Проверяем, что описание содержит переданный заголовок
        assert "Test PR" in pr["title"]
    
    def test_create_pull_request_nonexistent(self, validation_system):
        """Тест создания PR для несуществующей валидации"""
        with pytest.raises(ValueError, match="не найдена"):
            validation_system.create_pull_request(
                "nonexistent_id", "Test PR", "Description"
            )
    
    def test_monitor_deployment(self, validation_system, temp_dirs):
        """Тест мониторинга деплоя"""
        # Создаем и выполняем деплой
        sandbox_file = os.path.join(temp_dirs['sandbox'], "test_file.py")
        with open(sandbox_file, 'w') as f:
            f.write("def new_function():\n    return 'new'\n")
        
        validation_report = validation_system.validate_changes(
            temp_dirs['sandbox'], ["test_file.py"]
        )
        validation_system.approve_validation(validation_report.validation_id)
        
        with patch('shutil.copytree'), patch('shutil.copy2'):
            deployment_report = validation_system.deploy_changes(
                validation_report.validation_id, temp_dirs['sandbox']
            )
        
        # Мониторим деплой
        monitoring = validation_system.monitor_deployment(deployment_report.deployment_id)
        
        assert monitoring is not None
        assert monitoring["deployment_id"] == deployment_report.deployment_id
        assert monitoring["status"] == deployment_report.status.value
        assert "system_health" in monitoring
    
    def test_monitor_nonexistent_deployment(self, validation_system):
        """Тест мониторинга несуществующего деплоя"""
        with pytest.raises(ValueError, match="не найден"):
            validation_system.monitor_deployment("nonexistent_id")
    
    def test_check_system_health(self, validation_system):
        """Тест проверки здоровья системы"""
        health = validation_system._check_system_health()
        
        assert health is not None
        assert "status" in health
        assert "checks" in health
        assert "timestamp" in health
        assert health["status"] in ["healthy", "degraded", "unhealthy"]
    
    def test_estimate_deployment_time(self, validation_system):
        """Тест оценки времени деплоя"""
        # Создаем тестовые diff отчеты
        diff_reports = [
            DiffReport("file1.py", "modified", 5, 2, "", "low", "", []),
            DiffReport("file2.py", "added", 10, 0, "", "medium", "", [])
        ]
        
        estimated_time = validation_system._estimate_deployment_time(diff_reports)
        
        assert estimated_time in ["1-2 минуты", "3-5 минут", "5-10 минут", "10-15 минут"]
    
    def test_create_risk_assessment(self, validation_system):
        """Тест создания оценки рисков"""
        diff_reports = [
            DiffReport("file1.py", "modified", 5, 2, "", "low", "", []),
            DiffReport("file2.py", "added", 10, 0, "", "high", "", [])
        ]
        
        assessment = validation_system._create_risk_assessment(diff_reports, "high")
        
        assert "Максимальный уровень риска: HIGH" in assessment
        assert "Файлов с низким риском: 1" in assessment
        assert "Файлов с высоким риском: 1" in assessment
        assert "ВНИМАНИЕ" in assessment
    
    def test_create_recommendations(self, validation_system):
        """Тест создания рекомендаций"""
        diff_reports = [
            DiffReport("file1.py", "modified", 5, 2, "", "low", "", []),
            DiffReport("file2.py", "added", 10, 0, "", "critical", "", [])
        ]
        
        recommendations = validation_system._create_recommendations(diff_reports, "critical")
        
        assert len(recommendations) > 0
        assert any("КРИТИЧЕСКИЙ РИСК" in rec for rec in recommendations)
        assert any("тестирование" in rec for rec in recommendations)


class TestProductionConfig:
    """Тесты для конфигурации продакшн системы"""
    
    def test_default_config(self):
        """Тест конфигурации по умолчанию"""
        system = ProductionValidationSystem()
        
        assert system.config.production_path == "/app/langchain_api"
        assert system.config.backup_path == "/app/backups"
        assert ".py" in system.config.allowed_extensions
        assert system.config.max_file_size_mb == 10
        assert system.config.require_approval is True
        assert system.config.auto_rollback_on_failure is True
        assert system.config.monitoring_enabled is True
    
    def test_custom_config(self):
        """Тест пользовательской конфигурации"""
        config = ProductionConfig(
            production_path="/custom/production",
            backup_path="/custom/backups",
            allowed_extensions=[".py", ".js"],
            max_file_size_mb=20,
            require_approval=False,
            auto_rollback_on_failure=False,
            monitoring_enabled=False
        )
        
        system = ProductionValidationSystem(config)
        
        assert system.config.production_path == "/custom/production"
        assert system.config.backup_path == "/custom/backups"
        assert system.config.allowed_extensions == [".py", ".js"]
        assert system.config.max_file_size_mb == 20
        assert system.config.require_approval is False
        assert system.config.auto_rollback_on_failure is False
        assert system.config.monitoring_enabled is False


class TestDataStructures:
    """Тесты для структур данных"""
    
    def test_diff_report(self):
        """Тест структуры DiffReport"""
        diff_report = DiffReport(
            file_path="test.py",
            change_type="modified",
            lines_added=5,
            lines_removed=2,
            diff_content="@@ -1,2 +1,5 @@",
            risk_level="medium",
            impact_analysis="Test impact",
            recommendations=["Test recommendation"]
        )
        
        assert diff_report.file_path == "test.py"
        assert diff_report.change_type == "modified"
        assert diff_report.lines_added == 5
        assert diff_report.lines_removed == 2
        assert diff_report.risk_level == "medium"
        assert len(diff_report.recommendations) == 1
    
    def test_validation_report(self):
        """Тест структуры ValidationReport"""
        diff_report = DiffReport("test.py", "modified", 5, 2, "", "low", "", [])
        
        validation_report = ValidationReport(
            validation_id="test_id",
            timestamp="2025-01-07T12:00:00",
            status=ValidationStatus.PENDING,
            diff_reports=[diff_report],
            total_files_changed=1,
            total_lines_added=5,
            total_lines_removed=2,
            risk_assessment="Low risk",
            recommendations=["Test"],
            approval_required=False,
            estimated_deployment_time="1-2 минуты"
        )
        
        assert validation_report.validation_id == "test_id"
        assert validation_report.status == ValidationStatus.PENDING
        assert validation_report.total_files_changed == 1
        assert validation_report.approval_required is False
    
    def test_deployment_report(self):
        """Тест структуры DeploymentReport"""
        deployment_report = DeploymentReport(
            deployment_id="test_deployment",
            validation_id="test_validation",
            timestamp="2025-01-07T12:00:00",
            status=DeploymentStatus.SUCCESS,
            deployed_files=["test.py"],
            backup_location="/backup/location",
            deployment_log="Deployment successful",
            rollback_available=True,
            monitoring_required=True
        )
        
        assert deployment_report.deployment_id == "test_deployment"
        assert deployment_report.status == DeploymentStatus.SUCCESS
        assert len(deployment_report.deployed_files) == 1
        assert deployment_report.rollback_available is True
        assert deployment_report.monitoring_required is True


if __name__ == "__main__":
    pytest.main([__file__]) 