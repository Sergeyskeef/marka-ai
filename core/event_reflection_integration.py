#!/usr/bin/env python3
"""
Интеграция Event Bus с ReflectionManager для автоматических размышлений.
Обеспечивает создание размышлений на основе событий системы.
"""

import logging
from typing import Any

from langchain_api.core.event_bus import (
    CommandEventWrapper,
    ErrorEvent,
    EventType,
    SystemEvent,
    TaskEvent,
    get_event_bus,
    subscribe_to_events,
)
from langchain_api.sandbox.reflection_manager import ReflectionManager


class EventReflectionIntegration:
    """Интеграция Event Bus с ReflectionManager"""

    def __init__(self):
        self.event_bus = get_event_bus()
        self.reflection_manager = ReflectionManager()
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Настраивает обработчики событий для автоматических размышлений"""
        # Подписываемся на команды
        subscribe_to_events(EventType.COMMAND, self._handle_command_event)

        # Подписываемся на ошибки
        subscribe_to_events(EventType.ERROR, self._handle_error_event)

        # Подписываемся на системные события
        subscribe_to_events(EventType.SYSTEM, self._handle_system_event)

        # Подписываемся на задачи
        subscribe_to_events(EventType.TASK, self._handle_task_event)

        logging.info("Event Reflection Integration настроена")

    def _handle_command_event(self, event: CommandEventWrapper) -> None:
        """Обрабатывает события команд для создания размышлений"""
        try:
            # Создаем размышление о команде
            command_data = event.data
            command = command_data.get('command', '')
            user_id = command_data.get('user_id', '')
            success = command_data.get('success', True)
            result = command_data.get('result', '')

            # Определяем тип размышления
            if success:
                reflection_type = "команда_успешная"
                topic = f"Успешное выполнение команды: {command}"
            else:
                reflection_type = "команда_ошибка"
                topic = f"Ошибка при выполнении команды: {command}"

            # Создаем контент размышления
            content = f"""## Анализ выполнения команды

**Команда:** {command}
**Пользователь:** {user_id}
**Статус:** {'✅ Успешно' if success else '❌ Ошибка'}
**Время выполнения:** {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

### Детали выполнения:
{result if result else 'Нет дополнительной информации'}

### Анализ:
- Команда выполнена через Event Bus
- Интеграция с системой мониторинга команд
- Автоматическое создание размышления

### Выводы:
{'Команда выполнена успешно. Система работает корректно.' if success else 'Обнаружена ошибка. Требуется анализ и исправление.'}
"""

            # Создаем размышление
            self.reflection_manager.create_reflection(
                topic=topic,
                content=content,
                reflection_type=reflection_type,
                context={
                    "source": "event_bus",
                    "event_type": "command",
                    "command": command,
                    "user_id": user_id,
                    "success": success,
                    "event_timestamp": event.timestamp.isoformat()
                }
            )

            logging.info(f"Создано размышление о команде: {command}")

        except Exception as e:
            logging.error(f"Ошибка при создании размышления о команде: {e}")

    def _handle_error_event(self, event: ErrorEvent) -> None:
        """Обрабатывает события ошибок для создания размышлений"""
        try:
            error_type = event.data.get('error_type', 'Unknown')
            error_message = event.data.get('error_message', '')
            stack_trace = event.data.get('stack_trace', '')

            topic = f"Ошибка системы: {error_type}"

            content = f"""## Анализ системной ошибки

**Тип ошибки:** {error_type}
**Сообщение:** {error_message}
**Время:** {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
**Источник:** {event.source}

### Детали ошибки:
```
{error_message}
```

### Stack Trace:
```
{stack_trace if stack_trace else 'Stack trace недоступен'}
```

### Анализ:
- Ошибка зафиксирована через Event Bus
- Требуется анализ причин и исправление
- Возможные последствия для системы

### Рекомендации:
1. Проанализировать причины ошибки
2. Внести исправления в код
3. Добавить дополнительные проверки
4. Обновить документацию
"""

            self.reflection_manager.create_reflection(
                topic=topic,
                content=content,
                reflection_type="системная_ошибка",
                context={
                    "source": "event_bus",
                    "event_type": "error",
                    "error_type": error_type,
                    "error_message": error_message,
                    "event_source": event.source,
                    "event_timestamp": event.timestamp.isoformat()
                }
            )

            logging.info(f"Создано размышление об ошибке: {error_type}")

        except Exception as e:
            logging.error(f"Ошибка при создании размышления об ошибке: {e}")

    def _handle_system_event(self, event: SystemEvent) -> None:
        """Обрабатывает системные события для создания размышлений"""
        try:
            component = event.data.get('system_component', 'Unknown')
            action = event.data.get('action', '')
            details = event.data.get('details', '')

            # Добавляем детали команды если это выполнение команды
            command_output = event.data.get('command_output', '')
            command_error = event.data.get('command_error', '')

            topic = f"Системное событие: {component} - {action}"

            content = f"""## Анализ системного события

**Компонент:** {component}
**Действие:** {action}
**Время:** {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
**Источник:** {event.source}

### Детали события:
{details if details else 'Нет дополнительных деталей'}

### Детали команды:
"""

            if command_output:
                content += f"**Вывод команды:**\n```\n{command_output}\n```\n\n"

            if command_error:
                content += f"**Ошибка команды:**\n```\n{command_error}\n```\n\n"

            content += f"""### Анализ:
- Системное событие зафиксировано через Event Bus
- Компонент {component} выполнил действие {action}
- Возможное влияние на общую работу системы

### Выводы:
Система функционирует нормально. Событие зафиксировано для мониторинга.
"""

            self.reflection_manager.create_reflection(
                topic=topic,
                content=content,
                reflection_type="системное_событие",
                context={
                    "source": "event_bus",
                    "event_type": "system",
                    "component": component,
                    "action": action,
                    "details": details,
                    "event_timestamp": event.timestamp.isoformat()
                }
            )

            logging.info(f"Создано размышление о системном событии: {component} - {action}")

        except Exception as e:
            logging.error(f"Ошибка при создании размышления о системном событии: {e}")

    def _handle_task_event(self, event: TaskEvent) -> None:
        """Обрабатывает события задач для создания размышлений"""
        try:
            task_id = event.data.get('task_id', '')
            task_name = event.data.get('task_name', '')
            task_type = event.data.get('task_type', '')
            status = event.data.get('status', '')

            topic = f"Задача: {task_type} - {status}"

            content = f"""## Анализ задачи

**ID задачи:** {task_id}
**Имя задачи:** {task_name}
**Тип задачи:** {task_type}
**Статус:** {status}
**Время:** {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
**Источник:** {event.source}

### Детали задачи:
- Задача зафиксирована через Event Bus
- Статус изменен на: {status}
- Тип задачи: {task_type}
- Имя задачи: {task_name}

### Анализ:
- Задача обрабатывается системой
- Статус обновлен корректно
- Интеграция с Event Bus работает

### Следующие шаги:
{'Задача завершена успешно.' if status == 'completed' else 'Задача в процессе выполнения.'}
"""

            self.reflection_manager.create_reflection(
                topic=topic,
                content=content,
                reflection_type="задача",
                context={
                    "source": "event_bus",
                    "event_type": "task",
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": status,
                    "event_timestamp": event.timestamp.isoformat()
                }
            )

            logging.info(f"Создано размышление о задаче: {task_type} - {status}")

        except Exception as e:
            logging.error(f"Ошибка при создании размышления о задаче: {e}")

    def get_reflection_statistics(self) -> dict[str, Any]:
        """Возвращает статистику по размышлениям, созданным через Event Bus"""
        try:
            # Получаем все размышления
            reflections = self.reflection_manager.list_reflections()

            # Фильтруем размышления, созданные через Event Bus
            event_reflections = [
                ref for ref in reflections
                if ref.get('metadata', {}).get('source') == 'event_bus'
            ]

            # Группируем по типам событий
            by_event_type = {}
            for ref in event_reflections:
                event_type = ref.get('metadata', {}).get('event_type', 'unknown')
                if event_type not in by_event_type:
                    by_event_type[event_type] = []
                by_event_type[event_type].append(ref)

            # Группируем по типам размышлений
            by_reflection_type = {}
            for ref in event_reflections:
                ref_type = ref.get('reflection_type', 'unknown')
                if ref_type not in by_reflection_type:
                    by_reflection_type[ref_type] = []
                by_reflection_type[ref_type].append(ref)

            return {
                "total_event_reflections": len(event_reflections),
                "by_event_type": {k: len(v) for k, v in by_event_type.items()},
                "by_reflection_type": {k: len(v) for k, v in by_reflection_type.items()},
                "recent_reflections": event_reflections[-10:] if event_reflections else []
            }

        except Exception as e:
            logging.error(f"Ошибка при получении статистики размышлений: {e}")
            return {"error": str(e)}


# Глобальный экземпляр интеграции
event_reflection_integration = EventReflectionIntegration()


def get_event_reflection_integration() -> EventReflectionIntegration:
    """Возвращает глобальный экземпляр интеграции"""
    return event_reflection_integration
