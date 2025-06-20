"""
Тесты интеграции Command Monitoring System с Telegram Bot.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from langchain_api.core.command_monitoring import CommandMonitoringSystem, CommandEvent
from langchain_api.telegram_bot.bot import log_telegram_command, command_monitoring


class TestCommandMonitoringTelegramIntegration:
    """Тесты интеграции системы мониторинга команд с Telegram Bot."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.command_monitoring = CommandMonitoringSystem()
    
    def test_log_telegram_command_basic(self):
        """Тест базового логирования команды из Telegram."""
        # Arrange
        command = "/start"
        chat_id = 12345
        user_id = 67890
        
        # Act
        event = log_telegram_command(command, chat_id, user_id)
        
        # Assert
        assert event.command == command
        assert event.source == "telegram_bot"
        assert event.user_id == str(user_id)
        assert event.metadata["chat_id"] == chat_id
        assert event.timestamp is not None
    
    def test_log_telegram_command_with_parameters(self):
        """Тест логирования команды с параметрами."""
        # Arrange
        command = "/help"
        chat_id = 12345
        user_id = 67890
        parameters = {"section": "commands"}
        metadata = {"message_type": "command"}
        
        # Act
        event = log_telegram_command(
            command, chat_id, user_id, 
            parameters=parameters, metadata=metadata
        )
        
        # Assert
        assert event.parameters == parameters
        assert event.metadata["message_type"] == "command"
        assert event.metadata["chat_id"] == chat_id
    
    def test_log_telegram_command_without_user_id(self):
        """Тест логирования команды без user_id."""
        # Arrange
        command = "Привет, Марк!"
        chat_id = 12345
        
        # Act
        event = log_telegram_command(command, chat_id)
        
        # Assert
        assert event.user_id == str(chat_id)  # Используется chat_id как user_id
        assert event.source == "telegram_bot"
    
    def test_command_monitoring_integration(self):
        """Тест интеграции с системой мониторинга команд."""
        # Arrange
        command = "/sync"
        chat_id = 12345
        user_id = 67890
        
        # Act
        event = log_telegram_command(command, chat_id, user_id)
        
        # Проверяем, что событие попало в историю
        recent_commands = command_monitoring.get_recent_commands(limit=1)
        
        # Assert
        assert len(recent_commands) > 0
        assert recent_commands[0]["command"] == command
        assert recent_commands[0]["source"] == "telegram_bot"
    
    def test_command_result_logging(self):
        """Тест логирования результатов выполнения команд."""
        # Arrange
        command = "/start"
        chat_id = 12345
        user_id = 67890
        
        # Act
        event = log_telegram_command(command, chat_id, user_id)
        
        # Логируем успешный результат
        command_monitoring.log_result(
            event,
            result="Start command executed successfully",
            success=True,
            execution_time=0.5
        )
        
        # Assert
        assert event.success is True
        assert event.result == "Start command executed successfully"
        assert event.execution_time == 0.5
        assert event.error_message is None
    
    def test_command_error_logging(self):
        """Тест логирования ошибок выполнения команд."""
        # Arrange
        command = "/unknown_command"
        chat_id = 12345
        user_id = 67890
        
        # Act
        event = log_telegram_command(command, chat_id, user_id)
        
        # Логируем ошибку
        command_monitoring.log_result(
            event,
            result="Command not found",
            success=False,
            execution_time=0.1,
            error_message="Unknown command"
        )
        
        # Assert
        assert event.success is False
        assert event.error_message == "Unknown command"
        
        # Проверяем, что ошибка попадает в список ошибок
        recent_errors = command_monitoring.get_recent_errors(limit=1)
        assert len(recent_errors) > 0
        assert recent_errors[0]["command"] == command
    
    def test_command_statistics(self):
        """Тест получения статистики команд."""
        # Arrange
        commands = [
            ("/start", 12345, 67890),
            ("/help", 12345, 67890),
            ("/sync", 12345, 67890),
        ]
        
        # Act
        for command, chat_id, user_id in commands:
            event = log_telegram_command(command, chat_id, user_id)
            command_monitoring.log_result(
                event,
                result="Command executed",
                success=True,
                execution_time=0.1
            )
        
        # Получаем статистику
        stats = command_monitoring.get_statistics()
        
        # Assert
        assert stats["total_commands"] >= len(commands)
        assert stats["successful_commands"] >= len(commands)
        assert "telegram_bot" in stats["commands_by_source"]
    
    def test_command_history_by_source(self):
        """Тест получения истории команд по источнику."""
        # Arrange
        command = "/start"
        chat_id = 12345
        user_id = 67890
        
        # Act
        log_telegram_command(command, chat_id, user_id)
        
        # Получаем команды от telegram_bot
        telegram_commands = command_monitoring.get_commands_by_source("telegram_bot", limit=10)
        
        # Assert
        assert len(telegram_commands) > 0
        assert all(cmd.source == "telegram_bot" for cmd in telegram_commands)
    
    def test_command_history_by_user(self):
        """Тест получения истории команд по пользователю."""
        # Arrange
        command = "/help"
        chat_id = 12345
        user_id = 67890
        
        # Act
        log_telegram_command(command, chat_id, user_id)
        
        # Получаем команды пользователя
        user_commands = command_monitoring.get_commands_by_user(str(user_id), limit=10)
        
        # Assert
        assert len(user_commands) > 0
        assert all(cmd.user_id == str(user_id) for cmd in user_commands)


class TestCommandMonitoringTelegramCommands:
    """Тесты для конкретных команд Telegram."""
    
    @pytest.mark.asyncio
    async def test_start_command_logging(self):
        """Тест логирования команды /start."""
        # Arrange
        mock_update = Mock()
        mock_update.effective_chat.id = 12345
        mock_update.effective_user.id = 67890
        mock_update.message.reply_markdown_v2 = AsyncMock()
        
        mock_context = Mock()
        
        # Act
        from langchain_api.telegram_bot.bot import start_cmd
        await start_cmd(mock_update, mock_context)
        
        # Assert
        # Проверяем, что команда была залогирована
        recent_commands = command_monitoring.get_recent_commands(limit=1)
        assert len(recent_commands) > 0
        assert recent_commands[0]["command"] == "/start"
        assert recent_commands[0]["source"] == "telegram_bot"
        
        # Проверяем, что ответ был отправлен
        mock_update.message.reply_markdown_v2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sync_command_logging(self):
        """Тест логирования команды /sync."""
        # Arrange
        mock_update = Mock()
        mock_update.effective_chat.id = 12345
        mock_update.effective_user.id = 67890
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = Mock()
        
        # Mock для _sandbox_sync
        with patch('langchain_api.telegram_bot.bot._sandbox_sync', return_value=True):
            # Act
            from langchain_api.telegram_bot.bot import sync_cmd
            await sync_cmd(mock_update, mock_context)
            
            # Assert
            # Проверяем, что команда была залогирована
            recent_commands = command_monitoring.get_recent_commands(limit=1)
            assert len(recent_commands) > 0
            assert recent_commands[0]["command"] == "/sync"
            assert recent_commands[0]["source"] == "telegram_bot"
            
            # Проверяем, что ответ был отправлен
            mock_update.message.reply_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shell_command_logging(self):
        """Тест логирования shell-команд."""
        # Arrange
        # Очищаем историю команд перед тестом
        command_monitoring.clear_history()
        
        mock_update = Mock()
        mock_update.effective_chat.id = 12345
        mock_update.effective_user.id = 67890
        mock_update.message = Mock()
        mock_update.message.text = "!ls -la"
        mock_update.message.reply_markdown_v2 = AsyncMock()
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = Mock()
        
        # Mock для _sandbox_exec
        with patch('langchain_api.telegram_bot.bot._sandbox_exec', return_value="file1.txt\nfile2.txt"):
            # Act
            from langchain_api.telegram_bot.bot import sandbox_exec_cmd
            await sandbox_exec_cmd(mock_update, mock_context)
            
            # Assert
            # Проверяем, что команда была залогирована
            recent_commands = command_monitoring.get_recent_commands(limit=1)
            assert len(recent_commands) > 0
            assert "SANDBOX_EXEC: ls -la" in recent_commands[0]["command"]
            assert recent_commands[0]["source"] == "telegram_bot"
            
            # Проверяем, что ответ был отправлен
            mock_update.message.reply_markdown_v2.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
