#!/usr/bin/env python3
"""
Тесты для OutcomeLogger
"""

import pytest
import time
import unittest.mock as mock
from unittest.mock import MagicMock, patch

from core.metrics.outcome_logger import (
    OutcomeLogger,
    OutcomeStatus,
    ToolCallOutcome,
    outcome_logger
)


class TestToolCallOutcome:
    """Тесты для ToolCallOutcome"""
    
    def test_outcome_creation(self):
        """Тест создания outcome"""
        outcome = ToolCallOutcome(
            tool_name="test_tool",
            status=OutcomeStatus.SUCCESS,
            duration_ms=100
        )
        
        assert outcome.tool_name == "test_tool"
        assert outcome.status == OutcomeStatus.SUCCESS
        assert outcome.duration_ms == 100
        assert outcome.error is None
        assert outcome.details is None
        assert outcome.tool_call_id is None
        assert outcome.timestamp is not None
    
    def test_outcome_with_failure(self):
        """Тест создания outcome с ошибкой"""
        outcome = ToolCallOutcome(
            tool_name="test_tool",
            status=OutcomeStatus.FAIL,
            duration_ms=50,
            error="Test error",
            details={"key": "value"},
            tool_call_id="call_123"
        )
        
        assert outcome.tool_name == "test_tool"
        assert outcome.status == OutcomeStatus.FAIL
        assert outcome.duration_ms == 50
        assert outcome.error == "Test error"
        assert outcome.details == {"key": "value"}
        assert outcome.tool_call_id == "call_123"


class TestOutcomeLogger:
    """Тесты для OutcomeLogger"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        self.logger = OutcomeLogger()
        
        # Мокаем драйвер Neo4j
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_driver.session.return_value.__enter__.return_value = self.mock_session
    
    def test_log_outcome_success(self):
        """Тест логирования успешного outcome"""
        with patch.object(OutcomeLogger, 'driver', self.mock_driver):
            outcome = ToolCallOutcome(
                tool_name="test_tool",
                status=OutcomeStatus.SUCCESS,
                duration_ms=100,
                tool_call_id="call_123"
            )
            
            self.logger.log_outcome(outcome)
            
            # Проверяем что Neo4j запрос был выполнен
            self.mock_session.run.assert_called_once()
            call_args = self.mock_session.run.call_args
            
            # Проверяем параметры запроса
            params = call_args[0][1]
            assert params["tool_name"] == "test_tool"
            assert params["status"] == "success"
            assert params["duration_ms"] == 100
            assert params["tool_call_id"] == "call_123"
            assert params["error"] is None
    
    def test_log_outcome_failure(self):
        """Тест логирования неудачного outcome"""
        with patch.object(OutcomeLogger, 'driver', self.mock_driver):
            outcome = ToolCallOutcome(
                tool_name="test_tool",
                status=OutcomeStatus.FAIL,
                duration_ms=50,
                error="Test error",
                tool_call_id="call_456"
            )
            
            self.logger.log_outcome(outcome)
            
            # Проверяем что Neo4j запрос был выполнен
            self.mock_session.run.assert_called_once()
            call_args = self.mock_session.run.call_args
            
            # Проверяем параметры запроса
            params = call_args[0][1]
            assert params["tool_name"] == "test_tool"
            assert params["status"] == "fail"
            assert params["duration_ms"] == 50
            assert params["error"] == "Test error"
            assert params["tool_call_id"] == "call_456"
    
    def test_log_success_helper(self):
        """Тест вспомогательного метода log_success"""
        with patch.object(self.logger, 'log_outcome') as mock_log:
            self.logger.log_success(
                tool_name="test_tool",
                duration_ms=100,
                details={"result": "ok"},
                tool_call_id="call_789"
            )
            
            mock_log.assert_called_once()
            outcome = mock_log.call_args[0][0]
            assert outcome.tool_name == "test_tool"
            assert outcome.status == OutcomeStatus.SUCCESS
            assert outcome.duration_ms == 100
            assert outcome.details == {"result": "ok"}
            assert outcome.tool_call_id == "call_789"
    
    def test_log_failure_helper(self):
        """Тест вспомогательного метода log_failure"""
        with patch.object(self.logger, 'log_outcome') as mock_log:
            self.logger.log_failure(
                tool_name="test_tool",
                duration_ms=50,
                error="Test error",
                details={"error_code": 500},
                tool_call_id="call_999"
            )
            
            mock_log.assert_called_once()
            outcome = mock_log.call_args[0][0]
            assert outcome.tool_name == "test_tool"
            assert outcome.status == OutcomeStatus.FAIL
            assert outcome.duration_ms == 50
            assert outcome.error == "Test error"
            assert outcome.details == {"error_code": 500}
            assert outcome.tool_call_id == "call_999"
    
    def test_measure_execution_success(self):
        """Тест контекстного менеджера при успешном выполнении"""
        with patch.object(self.logger, 'log_outcome') as mock_log:
            with self.logger.measure_execution("test_tool", "call_123"):
                time.sleep(0.01)  # Небольшая задержка для измерения времени
            
            mock_log.assert_called_once()
            outcome = mock_log.call_args[0][0]
            assert outcome.tool_name == "test_tool"
            assert outcome.status == OutcomeStatus.SUCCESS
            assert outcome.duration_ms > 0  # Время должно быть измерено
            assert outcome.tool_call_id == "call_123"
    
    def test_measure_execution_failure(self):
        """Тест контекстного менеджера при ошибке выполнения"""
        with patch.object(self.logger, 'log_outcome') as mock_log:
            with pytest.raises(ValueError):
                with self.logger.measure_execution("test_tool", "call_456"):
                    time.sleep(0.01)  # Небольшая задержка для измерения времени
                    raise ValueError("Test error")
            
            mock_log.assert_called_once()
            outcome = mock_log.call_args[0][0]
            assert outcome.tool_name == "test_tool"
            assert outcome.status == OutcomeStatus.FAIL
            assert outcome.error == "Test error"
            assert outcome.duration_ms >= 0  # Время может быть 0 для быстрых операций
            assert outcome.tool_call_id == "call_456"
    
    def test_get_tool_stats(self):
        """Тест получения статистики по инструменту"""
        # Мокаем результат запроса
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {
            "total_calls": 10,
            "success_count": 8,
            "fail_count": 2,
            "avg_duration_ms": 150.5,
            "min_duration_ms": 50,
            "max_duration_ms": 300
        }[key]
        
        self.mock_session.run.return_value.single.return_value = mock_record
        
        with patch.object(OutcomeLogger, 'driver', self.mock_driver):
            stats = self.logger.get_tool_stats("test_tool")
            
            assert stats["tool_name"] == "test_tool"
            assert stats["total_calls"] == 10
            assert stats["success_count"] == 8
            assert stats["fail_count"] == 2
            assert stats["success_rate"] == 0.8
            assert stats["avg_duration_ms"] == 150.5
            assert stats["min_duration_ms"] == 50
            assert stats["max_duration_ms"] == 300
    
    def test_neo4j_connection_error(self):
        """Тест обработки ошибки подключения к Neo4j"""
        mock_driver = MagicMock()
        mock_driver.session.side_effect = Exception("Connection failed")
        
        with patch.object(OutcomeLogger, 'driver', mock_driver):
            outcome = ToolCallOutcome(
                tool_name="test_tool",
                status=OutcomeStatus.SUCCESS,
                duration_ms=100
            )
            
            # Не должно упасть, только логировать ошибку
            self.logger.log_outcome(outcome)


class TestGlobalOutcomeLogger:
    """Тесты для глобального экземпляра outcome_logger"""
    
    def test_global_instance_exists(self):
        """Тест что глобальный экземпляр существует"""
        assert outcome_logger is not None
        assert isinstance(outcome_logger, OutcomeLogger)
    
    def test_global_instance_is_singleton(self):
        """Тест что глобальный экземпляр - синглтон"""
        from core.metrics.outcome_logger import outcome_logger as logger2
        assert outcome_logger is logger2


@pytest.mark.integration
class TestOutcomeLoggerIntegration:
    """Интеграционные тесты с реальным Neo4j"""
    
    def test_real_neo4j_logging(self):
        """Тест логирования в реальный Neo4j"""
        # Используем уникальные ID для избежания конфликтов
        unique_id = f"test_{int(time.time())}"
        
        logger = OutcomeLogger()
        
        try:
            # Логируем тестовый outcome
            outcome = ToolCallOutcome(
                tool_name=f"integration_test_{unique_id}",
                status=OutcomeStatus.SUCCESS,
                duration_ms=42,
                tool_call_id=f"call_{unique_id}"
            )
            
            logger.log_outcome(outcome)
            
            # Проверяем что данные сохранились
            stats = logger.get_tool_stats(f"integration_test_{unique_id}")
            assert stats["total_calls"] == 1
            assert stats["success_count"] == 1
            assert stats["fail_count"] == 0
            assert stats["success_rate"] == 1.0
            
        finally:
            # Очищаем тестовые данные
            with logger.driver.session() as session:
                session.run(
                    "MATCH (o:Outcome {tool_name: $tool_name}) DELETE o",
                    {"tool_name": f"integration_test_{unique_id}"}
                )
            logger.close()