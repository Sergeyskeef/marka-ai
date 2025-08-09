"""
Тесты для системы мониторинга команд (Command Monitoring System)
"""

import os
import tempfile
from unittest.mock import Mock

import pytest

from core.command_monitoring import CommandEvent, CommandMonitoringSystem


class TestCommandEvent:
    """Тесты для структуры данных CommandEvent"""

    def test_command_event_creation(self):
        """Тест создания события команды"""
        event = CommandEvent(
            command="test_command",
            source="telegram",
            user_id="user123"
        )

        assert event.command == "test_command"
        assert event.source == "telegram"
        assert event.user_id == "user123"
        assert event.success is True
        assert event.timestamp is not None
        assert event.parameters == {}
        assert event.metadata == {}

    def test_command_event_with_parameters(self):
        """Тест создания события с параметрами"""
        parameters = {"param1": "value1", "param2": 42}
        metadata = {"meta1": "data1"}

        event = CommandEvent(
            command="test_command",
            source="api",
            parameters=parameters,
            metadata=metadata
        )

        assert event.parameters == parameters
        assert event.metadata == metadata


class TestCommandMonitoringSystem:
    """Тесты для системы мониторинга команд"""

    @pytest.fixture
    def monitoring_system(self):
        """Фикстура для создания системы мониторинга"""
        return CommandMonitoringSystem()

    def test_init(self, monitoring_system):
        """Тест инициализации системы"""
        assert monitoring_system.command_history == []
        assert 'before_execution' in monitoring_system.hooks
        assert 'after_execution' in monitoring_system.hooks
        assert 'on_error' in monitoring_system.hooks

    def test_register_hook(self, monitoring_system):
        """Тест регистрации хуков"""
        mock_callback = Mock()

        monitoring_system.register_hook('before_execution', mock_callback)

        assert mock_callback in monitoring_system.hooks['before_execution']

    def test_log_command(self, monitoring_system):
        """Тест логирования команды"""
        event = monitoring_system.log_command(
            command="test_command",
            source="telegram",
            user_id="user123"
        )

        assert isinstance(event, CommandEvent)
        assert event.command == "test_command"
        assert event.source == "telegram"
        assert event.user_id == "user123"
        assert len(monitoring_system.command_history) == 1

    def test_log_result_success(self, monitoring_system):
        """Тест логирования успешного результата"""
        event = monitoring_system.log_command("test_command", "telegram")

        monitoring_system.log_result(
            event=event,
            result="Success result",
            success=True,
            execution_time=1.5
        )

        assert event.result == "Success result"
        assert event.success is True
        assert event.execution_time == 1.5
        assert event.error_message is None

    def test_log_result_error(self, monitoring_system):
        """Тест логирования ошибки"""
        event = monitoring_system.log_command("test_command", "telegram")

        monitoring_system.log_result(
            event=event,
            result="Error occurred",
            success=False,
            execution_time=0.5,
            error_message="Test error"
        )

        assert event.result == "Error occurred"
        assert event.success is False
        assert event.execution_time == 0.5
        assert event.error_message == "Test error"

    def test_get_recent_commands(self, monitoring_system):
        """Тест получения последних команд"""
        # Добавляем несколько команд
        for i in range(5):
            monitoring_system.log_command(f"command_{i}", "telegram")

        recent = monitoring_system.get_recent_commands(limit=3)

        assert len(recent) == 3
        assert recent[-1]['command'] == "command_4"

    def test_get_recent_errors(self, monitoring_system):
        """Тест получения последних ошибок"""
        # Добавляем команды с ошибками
        for i in range(3):
            event = monitoring_system.log_command(f"command_{i}", "telegram")
            monitoring_system.log_result(
                event=event,
                result="Error",
                success=False,
                error_message=f"Error {i}"
            )

        # Добавляем успешную команду
        event = monitoring_system.log_command("success_command", "telegram")
        monitoring_system.log_result(event=event, result="Success", success=True)

        errors = monitoring_system.get_recent_errors(limit=2)

        assert len(errors) == 2
        assert all(not error['success'] for error in errors)

    def test_get_commands_by_source(self, monitoring_system):
        """Тест получения команд по источнику"""
        monitoring_system.log_command("cmd1", "telegram")
        monitoring_system.log_command("cmd2", "api")
        monitoring_system.log_command("cmd3", "telegram")

        telegram_commands = monitoring_system.get_commands_by_source("telegram")

        assert len(telegram_commands) == 2
        assert all(cmd.source == "telegram" for cmd in telegram_commands)

    def test_get_commands_by_user(self, monitoring_system):
        """Тест получения команд по пользователю"""
        monitoring_system.log_command("cmd1", "telegram", user_id="user1")
        monitoring_system.log_command("cmd2", "telegram", user_id="user2")
        monitoring_system.log_command("cmd3", "telegram", user_id="user1")

        user1_commands = monitoring_system.get_commands_by_user("user1")

        assert len(user1_commands) == 2
        assert all(cmd.user_id == "user1" for cmd in user1_commands)

    def test_analyze_command_patterns(self, monitoring_system):
        """Тест анализа паттернов команд"""
        # Добавляем повторяющиеся команды
        for _i in range(5):
            monitoring_system.log_command("frequent_command", "telegram")

        for _i in range(2):
            monitoring_system.log_command("rare_command", "api")

        patterns = monitoring_system.analyze_command_patterns()

        # Проверяем, что возвращается словарь с анализом
        assert isinstance(patterns, dict)
        assert 'total_commands' in patterns
        assert 'most_common_commands' in patterns
        assert patterns['total_commands'] == 7
        assert patterns['most_common_commands']['frequent_command'] == 5
        assert patterns['most_common_commands']['rare_command'] == 2

    def test_export_history(self, monitoring_system):
        """Тест экспорта истории"""
        # Добавляем команду
        monitoring_system.log_command("test_command", "telegram")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        try:
            success = monitoring_system.export_history(temp_file)
            assert success is True

            # Проверяем, что файл создан и не пустой
            assert os.path.exists(temp_file)
            assert os.path.getsize(temp_file) > 0
        finally:
            os.unlink(temp_file)

    def test_clear_history(self, monitoring_system):
        """Тест очистки истории"""
        monitoring_system.log_command("test_command", "telegram")
        assert len(monitoring_system.command_history) == 1

        monitoring_system.clear_history()
        assert len(monitoring_system.command_history) == 0

    def test_get_statistics(self, monitoring_system):
        """Тест получения статистики"""
        # Добавляем команды с разными результатами
        for i in range(3):
            event = monitoring_system.log_command(f"command_{i}", "telegram")
            monitoring_system.log_result(
                event=event,
                result="Success",
                success=True,
                execution_time=1.0
            )

        event = monitoring_system.log_command("error_command", "api")
        monitoring_system.log_result(
            event=event,
            result="Error",
            success=False,
            execution_time=0.5
        )

        stats = monitoring_system.get_statistics()

        # Проверяем основные поля статистики
        assert 'total_commands' in stats
        assert 'successful_commands' in stats
        assert 'failed_commands' in stats
        assert 'analysis' in stats
        assert stats['total_commands'] == 4
        assert stats['successful_commands'] == 3
        assert stats['failed_commands'] == 1

        # Проверяем вложенную структуру analysis
        analysis = stats['analysis']
        assert 'average_execution_time' in analysis
        assert 'success_rate' in analysis


class TestCommandMonitoringIntegration:
    """Тесты интеграции системы мониторинга"""

    def test_hook_execution(self):
        """Тест выполнения хуков"""
        monitoring_system = CommandMonitoringSystem()

        before_hook_called = False
        after_hook_called = False

        def before_hook(event):
            nonlocal before_hook_called
            before_hook_called = True

        def after_hook(event):
            nonlocal after_hook_called
            after_hook_called = True

        monitoring_system.register_hook('before_execution', before_hook)
        monitoring_system.register_hook('after_execution', after_hook)

        event = monitoring_system.log_command("test_command", "telegram")
        monitoring_system.log_result(event=event, result="Success", success=True)

        assert before_hook_called
        assert after_hook_called

    def test_error_hook_execution(self):
        """Тест выполнения хука ошибки"""
        monitoring_system = CommandMonitoringSystem()

        error_hook_called = False

        def error_hook(event):
            nonlocal error_hook_called
            error_hook_called = True

        monitoring_system.register_hook('on_error', error_hook)

        event = monitoring_system.log_command("test_command", "telegram")
        monitoring_system.log_result(
            event=event,
            result="Error",
            success=False,
            error_message="Test error"
        )

        assert error_hook_called
