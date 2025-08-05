"""
Система мониторинга команд.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class CommandEvent:
    """Структура данных для события команды."""
    command: str
    source: str  # 'telegram', 'script', 'api', 'task_executor'
    user_id: str | None = None
    timestamp: str = None
    parameters: dict[str, Any] = None
    result: str | None = None
    success: bool = True
    execution_time: float = 0.0
    error_message: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.parameters is None:
            self.parameters = {}
        if self.metadata is None:
            self.metadata = {}

class CommandMonitoringSystem:
    """
    Система мониторинга команд.

    Отвечает за:
    - Перехват всех команд и скриптов
    - Логирование событий с метаданными
    - Анализ команд LLM
    - Интеграцию с ContextManager
    """

    def __init__(self, context_manager=None):
        """
        Инициализация системы мониторинга команд.

        Args:
            context_manager: Менеджер контекста для интеграции
        """
        self.context_manager = context_manager
        self.command_history: list[CommandEvent] = []
        self.hooks: dict[str, list[Callable]] = {
            'before_execution': [],
            'after_execution': [],
            'on_error': []
        }

        # Настройка логирования
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # Создаем обработчик для файла только если еще не создан
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Проверяем, есть ли уже обработчики
        if not self.logger.handlers:
            handler = logging.FileHandler(log_dir / "command_monitoring.log")
            handler.setLevel(logging.INFO)

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def register_hook(self, event_type: str, callback: Callable) -> None:
        """
        Регистрация хука для обработки событий.

        Args:
            event_type: Тип события ('before_execution', 'after_execution', 'on_error')
            callback: Функция обратного вызова
        """
        if event_type in self.hooks:
            self.hooks[event_type].append(callback)

    def log_command(self, command: str, source: str, user_id: str | None = None,
                   parameters: dict[str, Any] = None, metadata: dict[str, Any] = None) -> CommandEvent:
        """
        Логирование команды.

        Args:
            command: Команда для выполнения
            source: Источник команды
            user_id: ID пользователя
            parameters: Параметры команды
            metadata: Дополнительные метаданные

        Returns:
            Созданное событие команды
        """
        event = CommandEvent(
            command=command,
            source=source,
            user_id=user_id,
            parameters=parameters or {},
            metadata=metadata or {}
        )

        # Вызываем хуки перед выполнением
        self._call_hooks('before_execution', event)

        # Логируем событие
        self.command_history.append(event)
        self.logger.info(f"Command logged: {command} from {source}")

        return event

    def log_result(self, event: CommandEvent, result: str, success: bool = True,
                  execution_time: float = 0.0, error_message: str | None = None) -> None:
        """
        Логирование результата выполнения команды.

        Args:
            event: Событие команды
            result: Результат выполнения
            success: Успешность выполнения
            execution_time: Время выполнения
            error_message: Сообщение об ошибке
        """
        event.result = result
        event.success = success
        event.execution_time = execution_time
        event.error_message = error_message

        # Вызываем хуки после выполнения
        if success:
            self._call_hooks('after_execution', event)
        else:
            self._call_hooks('on_error', event)

        # Логируем результат
        if success:
            self.logger.info(f"Command completed: {event.command} in {execution_time:.2f}s")
        else:
            self.logger.error(f"Command failed: {event.command} - {error_message}")

    def get_recent_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Получение последних команд в формате словарей.

        Args:
            limit: Максимальное количество команд

        Returns:
            Список последних команд в формате словарей
        """
        recent_commands = self.command_history[-limit:]
        return [asdict(cmd) for cmd in recent_commands]

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Получение последних ошибок.

        Args:
            limit: Максимальное количество ошибок

        Returns:
            Список последних ошибок
        """
        errors = [cmd for cmd in self.command_history if not cmd.success][-limit:]
        return [asdict(cmd) for cmd in errors]

    def get_commands_by_source(self, source: str, limit: int = 50) -> list[CommandEvent]:
        """
        Получение команд по источнику.

        Args:
            source: Источник команд
            limit: Максимальное количество команд

        Returns:
            Список команд от указанного источника
        """
        return [cmd for cmd in self.command_history if cmd.source == source][-limit:]

    def get_commands_by_user(self, user_id: str, limit: int = 50) -> list[CommandEvent]:
        """
        Получение команд по пользователю.

        Args:
            user_id: ID пользователя
            limit: Максимальное количество команд

        Returns:
            Список команд пользователя
        """
        return [cmd for cmd in self.command_history if cmd.user_id == user_id][-limit:]

    def analyze_command_patterns(self) -> dict[str, Any]:
        """
        Анализ паттернов команд.

        Returns:
            Словарь с анализом паттернов
        """
        if not self.command_history:
            return {}

        analysis = {
            'total_commands': len(self.command_history),
            'sources': {},
            'success_rate': 0.0,
            'average_execution_time': 0.0,
            'most_common_commands': {},
            'recent_activity': {}
        }

        # Анализ по источникам
        for cmd in self.command_history:
            source = cmd.source
            if source not in analysis['sources']:
                analysis['sources'][source] = {
                    'count': 0,
                    'success_count': 0,
                    'total_time': 0.0
                }

            analysis['sources'][source]['count'] += 1
            if cmd.success:
                analysis['sources'][source]['success_count'] += 1
            analysis['sources'][source]['total_time'] += cmd.execution_time

        # Анализ успешности
        successful_commands = sum(1 for cmd in self.command_history if cmd.success)
        analysis['success_rate'] = successful_commands / len(self.command_history)

        # Среднее время выполнения
        total_time = sum(cmd.execution_time for cmd in self.command_history)
        analysis['average_execution_time'] = total_time / len(self.command_history)

        # Самые частые команды
        command_counts = {}
        for cmd in self.command_history:
            command_counts[cmd.command] = command_counts.get(cmd.command, 0) + 1

        analysis['most_common_commands'] = dict(
            sorted(command_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        # Недавняя активность (последние 24 часа)
        recent_time = datetime.utcnow().timestamp() - 86400  # 24 часа назад
        recent_commands = [
            cmd for cmd in self.command_history[-100:]  # Проверяем последние 100 команд
            if datetime.fromisoformat(cmd.timestamp).timestamp() > recent_time
        ]

        analysis['recent_activity'] = {
            'last_24h_commands': len(recent_commands),
            'last_command': self.command_history[-1].timestamp if self.command_history else None
        }

        return analysis

    def send_to_llm(self, event: CommandEvent) -> None:
        """
        Отправка события в LLM через ContextManager.

        Args:
            event: Событие команды
        """
        if not self.context_manager:
            return

        try:
            # Формируем контекст для LLM
            llm_context = {
                'command': event.command,
                'source': event.source,
                'user_id': event.user_id,
                'parameters': event.parameters,
                'timestamp': event.timestamp,
                'success': event.success,
                'execution_time': event.execution_time,
                'result': event.result,
                'error_message': event.error_message
            }

            # Отправляем в ContextManager
            self.context_manager.add_command_event(llm_context)

        except Exception as e:
            self.logger.error(f"Error sending command to LLM: {e}")

    def _call_hooks(self, event_type: str, event: CommandEvent) -> None:
        """
        Вызов хуков для события.

        Args:
            event_type: Тип события
            event: Событие команды
        """
        for hook in self.hooks.get(event_type, []):
            try:
                hook(event)
            except Exception as e:
                self.logger.error(f"Error in hook {event_type}: {e}")

    def export_history(self, filepath: str) -> bool:
        """
        Экспорт истории команд в файл.

        Args:
            filepath: Путь к файлу для экспорта

        Returns:
            True если экспорт прошел успешно
        """
        try:
            # Конвертируем события в словари
            history_data = [asdict(event) for event in self.command_history]

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Command history exported to {filepath}")
            return True

        except Exception as e:
            self.logger.error(f"Error exporting command history: {e}")
            return False

    def clear_history(self) -> None:
        """Очистка истории команд."""
        self.command_history.clear()
        self.logger.info("Command history cleared")

    def get_statistics(self) -> dict[str, Any]:
        """
        Получение статистики системы мониторинга.

        Returns:
            Словарь со статистикой
        """
        total_commands = len(self.command_history)
        successful_commands = sum(1 for cmd in self.command_history if cmd.success)
        failed_commands = total_commands - successful_commands
        commands_by_source = {}
        for cmd in self.command_history:
            commands_by_source[cmd.source] = commands_by_source.get(cmd.source, 0) + 1
        return {
            'total_commands': total_commands,
            'successful_commands': successful_commands,
            'failed_commands': failed_commands,
            'commands_by_source': commands_by_source,
            'hooks_registered': {k: len(v) for k, v in self.hooks.items()},
            'analysis': self.analyze_command_patterns(),
            'last_update': datetime.utcnow().isoformat()
        }


# Глобальный экземпляр системы мониторинга команд
_monitoring_system = None

def get_monitoring_system() -> CommandMonitoringSystem:
    """Получить глобальный экземпляр системы мониторинга."""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = CommandMonitoringSystem()
    return _monitoring_system

def log_command(command: str, source: str, user_id: str | None = None,
               parameters: dict[str, Any] = None, metadata: dict[str, Any] = None) -> CommandEvent:
    """Логировать команду через глобальную систему мониторинга."""
    return get_monitoring_system().log_command(command, source, user_id, parameters, metadata)

def complete_command(event: CommandEvent, result: str, success: bool = True,
                    execution_time: float = 0.0, error_message: str | None = None) -> None:
    """Логировать результат команды через глобальную систему мониторинга."""
    get_monitoring_system().log_result(event, result, success, execution_time, error_message)
