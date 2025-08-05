"""
Система безопасности и режимов работы для Telegram-бота.

Обеспечивает безопасное взаимодействие с системой через различные режимы работы:
- Продакшн режим - только чтение, анализ, создание задач
- Песочница режим - полная свобода экспериментов
- Гибридный режим - анализ в продакшне, выполнение в песочнице
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from langchain_api.core.command_monitoring import CommandMonitoringSystem
from langchain_api.services.security import AccessLevel, SecurityManager


class WorkMode(Enum):
    """Режимы работы системы"""
    PRODUCTION = "production"  # Продакшн режим - только чтение и анализ
    SANDBOX = "sandbox"        # Песочница - полная свобода
    HYBRID = "hybrid"          # Гибридный - анализ в продакшне, выполнение в песочнице


class OperationType(Enum):
    """Типы операций"""
    READ = "read"              # Чтение данных
    ANALYSIS = "analysis"      # Анализ и исследование
    TASK_CREATION = "task_creation"  # Создание задач
    CODE_EXECUTION = "code_execution"  # Выполнение кода
    SYSTEM_MODIFICATION = "system_modification"  # Изменение системы
    FILE_OPERATION = "file_operation"  # Операции с файлами
    MEMORY_OPERATION = "memory_operation"  # Операции с памятью


@dataclass
class SecurityContext:
    """Контекст безопасности для операции"""
    mode: WorkMode
    chat_id: int
    user_id: int | None = None
    session_id: str | None = None
    access_level: AccessLevel = AccessLevel.READ
    requires_confirmation: bool = False
    allowed_operations: set[OperationType] = None
    confirmation_pending: bool = False
    confirmation_expires: datetime | None = None


@dataclass
class ConfirmationRequest:
    """Запрос на подтверждение операции"""
    operation_id: str
    operation_type: OperationType
    description: str
    chat_id: int
    user_id: int | None
    parameters: dict[str, Any]
    requested_at: datetime
    expires_at: datetime
    confirmed: bool = False
    confirmed_at: datetime | None = None
    confirmed_by: int | None = None


class SecurityModeManager:
    """
    Менеджер режимов безопасности.

    Отвечает за:
    - Управление режимами работы
    - Валидацию операций
    - Систему подтверждений
    - Логирование действий
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.security_manager = SecurityManager()
        from langchain_api.core.command_monitoring import get_monitoring_system
        self.command_monitoring = get_monitoring_system()

        # Состояние системы
        self.current_mode = WorkMode.PRODUCTION
        self.active_sessions: dict[int, SecurityContext] = {}
        self.pending_confirmations: dict[str, ConfirmationRequest] = {}

        # Настройки режимов
        self.mode_configurations = {
            WorkMode.PRODUCTION: {
                "allowed_operations": {
                    OperationType.READ,
                    OperationType.ANALYSIS,
                    OperationType.TASK_CREATION,
                    OperationType.MEMORY_OPERATION
                },
                "requires_confirmation": {
                    OperationType.TASK_CREATION
                },
                "description": "Безопасный режим - только чтение, анализ и создание задач"
            },
            WorkMode.SANDBOX: {
                "allowed_operations": {
                    OperationType.READ,
                    OperationType.ANALYSIS,
                    OperationType.TASK_CREATION,
                    OperationType.CODE_EXECUTION,
                    OperationType.SYSTEM_MODIFICATION,
                    OperationType.FILE_OPERATION,
                    OperationType.MEMORY_OPERATION
                },
                "requires_confirmation": set(),
                "description": "Режим песочницы - полная свобода экспериментов"
            },
            WorkMode.HYBRID: {
                "allowed_operations": {
                    OperationType.READ,
                    OperationType.ANALYSIS,
                    OperationType.TASK_CREATION,
                    OperationType.CODE_EXECUTION,
                    OperationType.MEMORY_OPERATION
                },
                "requires_confirmation": {
                    OperationType.CODE_EXECUTION,
                    OperationType.TASK_CREATION
                },
                "description": "Гибридный режим - анализ в продакшне, выполнение в песочнице"
            }
        }

        # Команды и их типы операций
        self.command_operation_mapping = {
            # Безопасные команды (все режимы)
            "/start": OperationType.READ,
            "/help": OperationType.READ,
            "/status": OperationType.READ,
            "/selfcheck": OperationType.READ,
            "/memory_search": OperationType.MEMORY_OPERATION,
            "/memory_analyze": OperationType.MEMORY_OPERATION,

            # Команды с подтверждением
            "/sync": OperationType.SYSTEM_MODIFICATION,
            "/sandbox_exec": OperationType.CODE_EXECUTION,
            "/sandbox_diff": OperationType.FILE_OPERATION,
            "/sandbox_apply": OperationType.SYSTEM_MODIFICATION,
            "/pytest": OperationType.CODE_EXECUTION,
            "/task_create": OperationType.TASK_CREATION,
            "/memory_save": OperationType.MEMORY_OPERATION,
            "/memory_update": OperationType.MEMORY_OPERATION,
            "/memory_delete": OperationType.MEMORY_OPERATION,

            # Команды анализа
            "/self_analyze": OperationType.ANALYSIS,
            "/analyze_self": OperationType.ANALYSIS,
            "/decompose": OperationType.ANALYSIS,

            # Команды управления
            "/approve": OperationType.READ,  # Специальная команда для подтверждений
            "/reject": OperationType.READ,   # Специальная команда для отклонений
        }

        self.logger.info("Security Mode Manager инициализирован")

    def set_mode(self, mode: WorkMode, chat_id: int) -> bool:
        """Установка режима работы для чата"""
        try:
            if not isinstance(mode, WorkMode):
                self.logger.error(f"Неизвестный режим работы: {mode}")
                raise AttributeError(f"Invalid work mode: {mode}")

            # Создаем или обновляем контекст безопасности
            context = SecurityContext(
                mode=mode,
                chat_id=chat_id,
                allowed_operations=self.mode_configurations[mode]["allowed_operations"],
                requires_confirmation=bool(self.mode_configurations[mode]["requires_confirmation"])
            )

            self.active_sessions[chat_id] = context
            self.current_mode = mode

            # Логируем изменение режима
            self.command_monitoring.log_command(
                command=f"set_mode_{mode.value}",
                source="security_mode_manager",
                user_id=str(chat_id),
                parameters={"mode": mode.value},
                metadata={"operation": "mode_change"}
            )

            self.logger.info(f"Режим работы изменен на {mode.value} для чата {chat_id}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка установки режима {mode}: {e}")
            raise

    def get_mode(self, chat_id: int) -> WorkMode:
        """Получение текущего режима работы для чата"""
        context = self.active_sessions.get(chat_id)
        if context:
            return context.mode
        return self.current_mode

    def validate_operation(self, command: str, chat_id: int, parameters: dict[str, Any] = None) -> dict[str, Any]:
        """
        Валидация операции в текущем режиме.

        Returns:
            Dict с результатом валидации:
            {
                "allowed": bool,
                "requires_confirmation": bool,
                "reason": str,
                "suggestions": List[str]
            }
        """
        try:
            context = self.active_sessions.get(chat_id)
            if not context:
                # Создаем контекст по умолчанию
                context = SecurityContext(
                    mode=self.current_mode,
                    chat_id=chat_id,
                    allowed_operations=self.mode_configurations[self.current_mode]["allowed_operations"]
                )
                self.active_sessions[chat_id] = context

            # Определяем тип операции
            operation_type = self._determine_operation_type(command, parameters)

            # Проверяем разрешенность операции
            allowed = operation_type in context.allowed_operations

            # Проверяем необходимость подтверждения
            requires_confirmation = (
                operation_type in self.mode_configurations[context.mode]["requires_confirmation"]
            )

            result = {
                "allowed": allowed,
                "requires_confirmation": requires_confirmation and allowed,
                "operation_type": operation_type.value,
                "mode": context.mode.value,
                "reason": "",
                "suggestions": []
            }

            if not allowed:
                result["reason"] = f"Операция {operation_type.value} не разрешена в режиме {context.mode.value}"
                result["suggestions"] = self._get_suggestions(operation_type, context.mode)

            # Логируем валидацию
            self.command_monitoring.log_command(
                command=f"validate_{command}",
                source="security_mode_manager",
                user_id=str(chat_id),
                parameters={
                    "operation_type": operation_type.value,
                    "mode": context.mode.value,
                    "allowed": allowed,
                    "requires_confirmation": requires_confirmation
                },
                metadata={"operation": "validation"}
            )

            return result

        except Exception as e:
            self.logger.error(f"Ошибка валидации операции {command}: {e}")
            return {
                "allowed": False,
                "requires_confirmation": False,
                "reason": f"Ошибка валидации: {str(e)}",
                "suggestions": ["Обратитесь к администратору"]
            }

    def _determine_operation_type(self, command: str, parameters: dict[str, Any] = None) -> OperationType:
        """Определение типа операции по команде и параметрам"""

        # Проверяем прямое соответствие команды
        if command in self.command_operation_mapping:
            return self.command_operation_mapping[command]

        # Анализируем команду по паттернам
        if command.startswith("/sandbox_"):
            if "exec" in command or "run" in command:
                return OperationType.CODE_EXECUTION
            elif "diff" in command or "apply" in command:
                return OperationType.SYSTEM_MODIFICATION
            else:
                return OperationType.FILE_OPERATION

        if command.startswith("/task_"):
            return OperationType.TASK_CREATION

        if command.startswith("/memory_"):
            if command in ["/memory_save", "/memory_update", "/memory_delete"]:
                return OperationType.MEMORY_OPERATION
            else:
                return OperationType.READ

        if command.startswith("!"):
            return OperationType.CODE_EXECUTION

        # Анализируем параметры для определения типа
        if parameters:
            if "command" in parameters or "script" in parameters:
                return OperationType.CODE_EXECUTION
            if "file" in parameters or "path" in parameters:
                return OperationType.FILE_OPERATION
            if "task" in parameters:
                return OperationType.TASK_CREATION

        # По умолчанию считаем операцией чтения
        return OperationType.READ

    def _get_suggestions(self, operation_type: OperationType, current_mode: WorkMode) -> list[str]:
        """Получение предложений для разрешения операции"""
        suggestions = []

        if operation_type in [OperationType.CODE_EXECUTION, OperationType.SYSTEM_MODIFICATION]:
            if current_mode == WorkMode.PRODUCTION:
                suggestions.append("Переключитесь в режим песочницы: /mode_sandbox")
                suggestions.append("Используйте гибридный режим: /mode_hybrid")
            elif current_mode == WorkMode.HYBRID:
                suggestions.append("Переключитесь в режим песочницы: /mode_sandbox")

        elif operation_type == OperationType.TASK_CREATION:
            suggestions.append("Используйте команду /approve для подтверждения")

        return suggestions

    async def request_confirmation(self, operation_id: str, operation_type: OperationType,
                                 description: str, chat_id: int, user_id: int | None,
                                 parameters: dict[str, Any]) -> ConfirmationRequest:
        """Создание запроса на подтверждение операции"""

        confirmation = ConfirmationRequest(
            operation_id=operation_id,
            operation_type=operation_type,
            description=description,
            chat_id=chat_id,
            user_id=user_id,
            parameters=parameters,
            requested_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=30)  # 30 минут на подтверждение
        )

        self.pending_confirmations[operation_id] = confirmation

        # Логируем запрос подтверждения
        self.command_monitoring.log_command(
            command="request_confirmation",
            source="security_mode_manager",
            user_id=str(user_id) if user_id else str(chat_id),
            parameters={
                "operation_id": operation_id,
                "operation_type": operation_type.value,
                "description": description
            },
            metadata={"operation": "confirmation_request"}
        )

        self.logger.info(f"Запрос подтверждения создан: {operation_id}")
        return confirmation

    def confirm_operation(self, operation_id: str, user_id: int) -> bool:
        """Подтверждение операции"""
        if operation_id not in self.pending_confirmations:
            return False

        confirmation = self.pending_confirmations[operation_id]

        # Проверяем срок действия
        if datetime.now() > confirmation.expires_at:
            del self.pending_confirmations[operation_id]
            return False

        # Подтверждаем операцию
        confirmation.confirmed = True
        confirmation.confirmed_at = datetime.now()
        confirmation.confirmed_by = user_id

        # Логируем подтверждение
        self.command_monitoring.log_command(
            command="confirm_operation",
            source="security_mode_manager",
            user_id=str(user_id),
            parameters={
                "operation_id": operation_id,
                "operation_type": confirmation.operation_type.value
            },
            metadata={"operation": "confirmation"}
        )

        self.logger.info(f"Операция подтверждена: {operation_id}")
        return True

    def reject_operation(self, operation_id: str, user_id: int) -> bool:
        """Отклонение операции"""
        if operation_id not in self.pending_confirmations:
            return False

        confirmation = self.pending_confirmations[operation_id]

        # Удаляем запрос подтверждения
        del self.pending_confirmations[operation_id]

        # Логируем отклонение
        self.command_monitoring.log_command(
            command="reject_operation",
            source="security_mode_manager",
            user_id=str(user_id),
            parameters={
                "operation_id": operation_id,
                "operation_type": confirmation.operation_type.value
            },
            metadata={"operation": "rejection"}
        )

        self.logger.info(f"Операция отклонена: {operation_id}")
        return True

    def get_pending_confirmations(self, chat_id: int) -> list[ConfirmationRequest]:
        """Получение ожидающих подтверждения операций для чата"""
        return [
            conf for conf in self.pending_confirmations.values()
            if conf.chat_id == chat_id and not conf.confirmed
        ]

    def cleanup_expired_confirmations(self) -> int:
        """Очистка просроченных подтверждений"""
        expired = []
        for operation_id, confirmation in self.pending_confirmations.items():
            if datetime.now() > confirmation.expires_at:
                expired.append(operation_id)

        for operation_id in expired:
            del self.pending_confirmations[operation_id]

        if expired:
            self.logger.info(f"Очищено {len(expired)} просроченных подтверждений")

        return len(expired)

    def get_mode_info(self, mode: WorkMode) -> dict[str, Any]:
        """Получение информации о режиме работы"""
        config = self.mode_configurations.get(mode, {})
        return {
            "mode": mode.value,
            "description": config.get("description", ""),
            "allowed_operations": [op.value for op in config.get("allowed_operations", [])],
            "requires_confirmation": [op.value for op in config.get("requires_confirmation", [])]
        }

    def get_security_status(self, chat_id: int) -> dict[str, Any]:
        """Получение статуса безопасности для чата"""
        context = self.active_sessions.get(chat_id)
        if not context:
            context = SecurityContext(
                mode=self.current_mode,
                chat_id=chat_id,
                allowed_operations=self.mode_configurations[self.current_mode]["allowed_operations"]
            )

        pending_count = len(self.get_pending_confirmations(chat_id))

        return {
            "mode": context.mode.value,
            "access_level": context.access_level.value,
            "pending_confirmations": pending_count,
            "session_active": True,
            "last_activity": datetime.now().isoformat()
        }

    async def cleanup_expired_confirmations_task(self):
        """Асинхронная задача для периодической очистки просроченных подтверждений."""
        while True:
            try:
                self.cleanup_expired_confirmations()
                await asyncio.sleep(300)
            except Exception as e:
                self.logger.error(f"Ошибка в задаче очистки подтверждений: {e}")
                await asyncio.sleep(60)


# Глобальный экземпляр менеджера режимов
_security_mode_manager: SecurityModeManager | None = None


def get_security_mode_manager() -> SecurityModeManager:
    """Получение глобального экземпляра менеджера режимов"""
    global _security_mode_manager
    if _security_mode_manager is None:
        _security_mode_manager = SecurityModeManager()
    return _security_mode_manager


async def cleanup_expired_confirmations_task():
    """Задача для периодической очистки просроченных подтверждений"""
    manager = get_security_mode_manager()
    while True:
        try:
            manager.cleanup_expired_confirmations()
            await asyncio.sleep(300)  # Проверяем каждые 5 минут
        except Exception as e:
            logging.error(f"Ошибка в задаче очистки подтверждений: {e}")
            await asyncio.sleep(60)
