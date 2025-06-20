"""
Тесты для системы безопасности и режимов работы.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from langchain_api.core.security_modes import (
    SecurityModeManager,
    WorkMode,
    OperationType,
    SecurityContext,
    ConfirmationRequest,
    get_security_mode_manager
)


class TestSecurityModeManager:
    """Тесты для SecurityModeManager."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.manager = SecurityModeManager()
        self.chat_id = 12345
        self.user_id = 67890
    
    def test_initialization(self):
        """Тест инициализации менеджера."""
        assert self.manager.current_mode == WorkMode.PRODUCTION
        assert len(self.manager.active_sessions) == 0
        assert len(self.manager.pending_confirmations) == 0
    
    def test_set_mode(self):
        """Тест установки режима работы."""
        # Тест установки продакшн режима
        success = self.manager.set_mode(WorkMode.PRODUCTION, self.chat_id)
        assert success is True
        
        # Проверяем, что режим установлен
        mode = self.manager.get_mode(self.chat_id)
        assert mode == WorkMode.PRODUCTION
        
        # Проверяем, что сессия создана
        assert self.chat_id in self.manager.active_sessions
        
        # Тест установки режима песочницы
        success = self.manager.set_mode(WorkMode.SANDBOX, self.chat_id)
        assert success is True
        assert self.manager.get_mode(self.chat_id) == WorkMode.SANDBOX
    
    def test_set_invalid_mode(self):
        """Тест установки недопустимого режима."""
        with pytest.raises(AttributeError):
            self.manager.set_mode("invalid_mode", self.chat_id)
    
    def test_get_mode_default(self):
        """Тест получения режима по умолчанию."""
        # Для нового чата должен возвращаться режим по умолчанию
        mode = self.manager.get_mode(self.chat_id)
        assert mode == WorkMode.PRODUCTION
    
    def test_validate_operation_production_mode(self):
        """Тест валидации операций в продакшн режиме."""
        # Устанавливаем продакшн режим
        self.manager.set_mode(WorkMode.PRODUCTION, self.chat_id)
        
        # Тест разрешенной операции (чтение)
        validation = self.manager.validate_operation("/start", self.chat_id)
        assert validation["allowed"] is True
        assert validation["requires_confirmation"] is False
        assert validation["mode"] == "production"
        
        # Тест заблокированной операции (выполнение кода)
        validation = self.manager.validate_operation("/sandbox_exec", self.chat_id)
        assert validation["allowed"] is False
        assert "не разрешена" in validation["reason"]
        assert len(validation["suggestions"]) > 0
    
    def test_validate_operation_sandbox_mode(self):
        """Тест валидации операций в режиме песочницы."""
        # Устанавливаем режим песочницы
        self.manager.set_mode(WorkMode.SANDBOX, self.chat_id)
        
        # Все операции должны быть разрешены
        validation = self.manager.validate_operation("/sandbox_exec", self.chat_id)
        assert validation["allowed"] is True
        assert validation["requires_confirmation"] is False
        assert validation["mode"] == "sandbox"
    
    def test_validate_operation_hybrid_mode(self):
        """Тест валидации операций в гибридном режиме."""
        # Устанавливаем гибридный режим
        self.manager.set_mode(WorkMode.HYBRID, self.chat_id)
        
        # Тест операции, требующей подтверждения
        validation = self.manager.validate_operation("/sandbox_exec", self.chat_id)
        assert validation["allowed"] is True
        assert validation["requires_confirmation"] is True
        assert validation["mode"] == "hybrid"
    
    def test_determine_operation_type(self):
        """Тест определения типа операции."""
        # Тест прямого соответствия
        op_type = self.manager._determine_operation_type("/start")
        assert op_type == OperationType.READ
        
        # Тест shell-команд
        op_type = self.manager._determine_operation_type("!ls -la")
        assert op_type == OperationType.CODE_EXECUTION
        
        # Тест команд песочницы
        op_type = self.manager._determine_operation_type("/sandbox_exec")
        assert op_type == OperationType.CODE_EXECUTION
        
        # Тест команд задач
        op_type = self.manager._determine_operation_type("/task_create")
        assert op_type == OperationType.TASK_CREATION
        
        # Тест команд памяти
        op_type = self.manager._determine_operation_type("/memory_save")
        assert op_type == OperationType.MEMORY_OPERATION
        
        # Тест по умолчанию
        op_type = self.manager._determine_operation_type("/unknown_command")
        assert op_type == OperationType.READ
    
    @pytest.mark.asyncio
    async def test_request_confirmation(self):
        """Тест создания запроса на подтверждение."""
        confirmation = await self.manager.request_confirmation(
            operation_id="test_123",
            operation_type=OperationType.CODE_EXECUTION,
            description="Test operation",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={"test": "data"}
        )
        
        assert confirmation.operation_id == "test_123"
        assert confirmation.operation_type == OperationType.CODE_EXECUTION
        assert confirmation.chat_id == self.chat_id
        assert confirmation.user_id == self.user_id
        assert confirmation.confirmed is False
        assert "test_123" in self.manager.pending_confirmations
    
    def test_confirm_operation(self):
        """Тест подтверждения операции."""
        # Создаем запрос на подтверждение
        confirmation = ConfirmationRequest(
            operation_id="test_123",
            operation_type=OperationType.CODE_EXECUTION,
            description="Test operation",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)
        )
        
        self.manager.pending_confirmations["test_123"] = confirmation
        
        # Подтверждаем операцию
        success = self.manager.confirm_operation("test_123", self.user_id)
        assert success is True
        assert confirmation.confirmed is True
        assert confirmation.confirmed_by == self.user_id
    
    def test_confirm_expired_operation(self):
        """Тест подтверждения просроченной операции."""
        # Создаем просроченный запрос
        confirmation = ConfirmationRequest(
            operation_id="test_123",
            operation_type=OperationType.CODE_EXECUTION,
            description="Test operation",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now() - timedelta(hours=1),
            expires_at=datetime.now() - timedelta(minutes=30)
        )
        
        self.manager.pending_confirmations["test_123"] = confirmation
        
        # Пытаемся подтвердить просроченную операцию
        success = self.manager.confirm_operation("test_123", self.user_id)
        assert success is False
        assert "test_123" not in self.manager.pending_confirmations
    
    def test_reject_operation(self):
        """Тест отклонения операции."""
        # Создаем запрос на подтверждение
        confirmation = ConfirmationRequest(
            operation_id="test_123",
            operation_type=OperationType.CODE_EXECUTION,
            description="Test operation",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)
        )
        
        self.manager.pending_confirmations["test_123"] = confirmation
        
        # Отклоняем операцию
        success = self.manager.reject_operation("test_123", self.user_id)
        assert success is True
        assert "test_123" not in self.manager.pending_confirmations
    
    def test_get_pending_confirmations(self):
        """Тест получения ожидающих подтверждения операций."""
        # Создаем несколько запросов
        confirmation1 = ConfirmationRequest(
            operation_id="test_1",
            operation_type=OperationType.CODE_EXECUTION,
            description="Test 1",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)
        )
        
        confirmation2 = ConfirmationRequest(
            operation_id="test_2",
            operation_type=OperationType.TASK_CREATION,
            description="Test 2",
            chat_id=self.chat_id + 1,  # Другой чат
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)
        )
        
        self.manager.pending_confirmations["test_1"] = confirmation1
        self.manager.pending_confirmations["test_2"] = confirmation2
        
        # Получаем подтверждения для первого чата
        confirmations = self.manager.get_pending_confirmations(self.chat_id)
        assert len(confirmations) == 1
        assert confirmations[0].operation_id == "test_1"
    
    def test_cleanup_expired_confirmations(self):
        """Тест очистки просроченных подтверждений."""
        # Создаем просроченный запрос
        expired_confirmation = ConfirmationRequest(
            operation_id="expired",
            operation_type=OperationType.CODE_EXECUTION,
            description="Expired",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now() - timedelta(hours=1),
            expires_at=datetime.now() - timedelta(minutes=30)
        )
        
        # Создаем активный запрос
        active_confirmation = ConfirmationRequest(
            operation_id="active",
            operation_type=OperationType.CODE_EXECUTION,
            description="Active",
            chat_id=self.chat_id,
            user_id=self.user_id,
            parameters={},
            requested_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)
        )
        
        self.manager.pending_confirmations["expired"] = expired_confirmation
        self.manager.pending_confirmations["active"] = active_confirmation
        
        # Очищаем просроченные
        cleaned_count = self.manager.cleanup_expired_confirmations()
        assert cleaned_count == 1
        assert "expired" not in self.manager.pending_confirmations
        assert "active" in self.manager.pending_confirmations
    
    def test_get_mode_info(self):
        """Тест получения информации о режиме."""
        info = self.manager.get_mode_info(WorkMode.PRODUCTION)
        assert info["mode"] == "production"
        assert "description" in info
        assert "allowed_operations" in info
        assert "requires_confirmation" in info
    
    def test_get_security_status(self):
        """Тест получения статуса безопасности."""
        # Устанавливаем режим
        self.manager.set_mode(WorkMode.SANDBOX, self.chat_id)
        
        status = self.manager.get_security_status(self.chat_id)
        assert status["mode"] == "sandbox"
        assert status["session_active"] is True
        assert "last_activity" in status
        assert "pending_confirmations" in status


class TestGlobalManager:
    """Тесты для глобального менеджера."""
    
    def test_get_security_mode_manager(self):
        """Тест получения глобального экземпляра."""
        manager1 = get_security_mode_manager()
        manager2 = get_security_mode_manager()
        
        # Должен возвращаться один и тот же экземпляр
        assert manager1 is manager2


@pytest.mark.asyncio
class TestAsyncOperations:
    """Тесты асинхронных операций."""
    
    @pytest.mark.asyncio
    async def test_cleanup_task(self):
        """Тест задачи очистки подтверждений."""
        manager = SecurityModeManager()
        
        # Создаем просроченный запрос
        expired_confirmation = ConfirmationRequest(
            operation_id="expired",
            operation_type=OperationType.CODE_EXECUTION,
            description="Expired",
            chat_id=123,
            user_id=456,
            parameters={},
            requested_at=datetime.now() - timedelta(hours=1),
            expires_at=datetime.now() - timedelta(minutes=30)
        )
        
        manager.pending_confirmations["expired"] = expired_confirmation
        
        # Запускаем задачу очистки (сокращенное время для теста)
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = asyncio.CancelledError()  # Прерываем после первого цикла
            
            try:
                await manager.cleanup_expired_confirmations_task()
            except asyncio.CancelledError:
                pass
        
        # Проверяем, что просроченные подтверждения очищены
        assert "expired" not in manager.pending_confirmations


if __name__ == "__main__":
    pytest.main([__file__]) 