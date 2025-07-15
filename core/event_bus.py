#!/usr/bin/env python3
"""
Event Bus System - центральная система управления событиями для Марка.
Обеспечивает автоматические триггеры и интеграцию между компонентами системы.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from pathlib import Path

from langchain_api.core.command_monitoring import CommandEvent, CommandMonitoringSystem


class EventType(Enum):
    """Типы событий в системе"""
    COMMAND = "command"
    TASK = "task"
    ERROR = "error"
    SUCCESS = "success"
    SYSTEM = "system"
    REFLECTION = "reflection"
    SANDBOX = "sandbox"
    SECURITY = "security"


@dataclass
class Event:
    """Базовый класс для всех событий в системе"""
    event_type: EventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует событие в словарь для сериализации"""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
            "metadata": self.metadata or {}
        }


@dataclass
class CommandEventWrapper:
    event_type: EventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    command_event: CommandEvent
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.event_type = EventType.COMMAND
        self.timestamp = self.command_event.timestamp
        self.source = self.command_event.source
        self.data = {
            "command": self.command_event.command,
            "user_id": self.command_event.user_id,
            "chat_id": self.command_event.chat_id,
            "parameters": self.command_event.parameters,
            "success": getattr(self.command_event, 'success', True),
            "result": getattr(self.command_event, 'result', ''),
            "execution_time": getattr(self.command_event, 'execution_time', 0)
        }
        self.metadata = self.command_event.metadata


@dataclass
class TaskEvent:
    event_type: EventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    task_id: str
    task_type: str
    status: str  # created, started, completed, failed
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.data.update({
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status
        })


@dataclass
class ErrorEvent:
    event_type: EventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.event_type = EventType.ERROR
        self.data.update({
            "error_type": self.error_type,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace
        })


@dataclass
class SuccessEvent:
    event_type: EventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    operation: str
    result: str
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.event_type = EventType.SUCCESS
        self.data.update({
            "operation": self.operation,
            "result": self.result
        })


@dataclass
class SystemEvent:
    event_type: EventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    system_component: str
    action: str
    details: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self.event_type = EventType.SYSTEM
        self.data.update({
            "system_component": self.system_component,
            "action": self.action,
            "details": self.details
        })


class EventBus:
    """Центральная система управления событиями"""
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {
            event_type: [] for event_type in EventType
        }
        self._event_history: List[Event] = []
        self._command_monitoring = CommandMonitoringSystem()
        self._log_file = Path("sandbox/event_bus.log")
        self._log_file.parent.mkdir(exist_ok=True)
        
        # Автоматическая подписка на события CommandMonitoring
        self._setup_command_monitoring_integration()
    
    def _setup_command_monitoring_integration(self):
        """Настраивает интеграцию с CommandMonitoringSystem"""
        # Перехватываем события команд для автоматической обработки
        original_log_command = self._command_monitoring.log_command
        
        def enhanced_log_command(*args, **kwargs):
            event = original_log_command(*args, **kwargs)
            # Создаем событие Event Bus из CommandEvent
            event_wrapper = CommandEventWrapper(
                event_type=EventType.COMMAND,
                timestamp=event.timestamp,
                source=event.source,
                data={},
                command_event=event
            )
            self.publish(event_wrapper)
            return event
        
        self._command_monitoring.log_command = enhanced_log_command
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Подписывает callback на события определенного типа"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logging.info(f"Подписка на события {event_type.value}: {callback.__name__}")
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Отписывает callback от событий определенного типа"""
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logging.info(f"Отписка от событий {event_type.value}: {callback.__name__}")
    
    def publish(self, event: Event) -> None:
        """Публикует событие в Event Bus"""
        # Добавляем в историю
        self._event_history.append(event)
        
        # Логируем событие
        self._log_event(event)
        
        # Уведомляем подписчиков
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    logging.error(f"Ошибка в callback {callback.__name__}: {e}")
        
        # Уведомляем подписчиков на все события
        if EventType.SYSTEM in self._subscribers:
            for callback in self._subscribers[EventType.SYSTEM]:
                try:
                    callback(event)
                except Exception as e:
                    logging.error(f"Ошибка в системном callback {callback.__name__}: {e}")
    
    def _log_event(self, event: Event) -> None:
        """Логирует событие в файл"""
        try:
            log_entry = {
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "source": event.source,
                "data": event.data,
                "metadata": event.metadata
            }
            
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logging.error(f"Ошибка при логировании события: {e}")
    
    def get_events_by_type(self, event_type: EventType, limit: int = 100) -> List[Event]:
        """Возвращает события определенного типа"""
        return [event for event in self._event_history if event.event_type == event_type][-limit:]
    
    def get_recent_events(self, limit: int = 100) -> List[Event]:
        """Возвращает последние события"""
        return self._event_history[-limit:]
    
    def get_events_by_source(self, source: str, limit: int = 100) -> List[Event]:
        """Возвращает события от определенного источника"""
        return [event for event in self._event_history if event.source == source][-limit:]
    
    def clear_history(self) -> None:
        """Очищает историю событий"""
        self._event_history.clear()
        logging.info("История событий очищена")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Возвращает статистику по событиям"""
        stats = {
            "total_events": len(self._event_history),
            "events_by_type": {},
            "events_by_source": {},
            "subscribers_count": {}
        }
        
        # Подсчет по типам
        for event_type in EventType:
            count = len([e for e in self._event_history if e.event_type == event_type])
            stats["events_by_type"][event_type.value] = count
        
        # Подсчет по источникам
        sources = set(event.source for event in self._event_history)
        for source in sources:
            count = len([e for e in self._event_history if e.source == source])
            stats["events_by_source"][source] = count
        
        # Количество подписчиков
        for event_type in EventType:
            stats["subscribers_count"][event_type.value] = len(self._subscribers.get(event_type, []))
        
        return stats


# Глобальный экземпляр Event Bus
event_bus = EventBus()


def publish_event(event: Event) -> None:
    """Глобальная функция для публикации событий"""
    event_bus.publish(event)


def subscribe_to_events(event_type: EventType, callback: Callable[[Event], None]) -> None:
    """Глобальная функция для подписки на события"""
    event_bus.subscribe(event_type, callback)


def get_event_bus() -> EventBus:
    """Возвращает глобальный экземпляр Event Bus"""
    return event_bus 