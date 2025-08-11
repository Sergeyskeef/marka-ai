"""
Event Bus - центральная шина событий для связи компонентов
"""

import asyncio
import logging
from typing import Callable, Dict, List, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Приоритеты обработки событий"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Event:
    """Структура события"""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = None
    source: str = None
    priority: EventPriority = EventPriority.NORMAL
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class EventTypes:
    """Предопределенные типы событий"""
    # Планирование
    PLAN_CREATED = "plan.created"
    PLAN_UPDATED = "plan.updated"
    PLAN_EXECUTED = "plan.executed"
    PLAN_FAILED = "plan.failed"
    
    # Задачи
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    
    # Память
    MEMORY_STORED = "memory.stored"
    MEMORY_SEARCHED = "memory.searched"
    MEMORY_UPDATED = "memory.updated"
    
    # Песочница
    SANDBOX_EXECUTED = "sandbox.executed"
    SANDBOX_BLOCKED = "sandbox.blocked"
    SANDBOX_ERROR = "sandbox.error"
    
    # Бот
    BOT_COMMAND = "bot.command"
    BOT_MESSAGE = "bot.message"
    BOT_CALLBACK = "bot.callback"
    
    # Ошибки и диагностика
    ERROR_OCCURRED = "error.occurred"
    ERROR_DIAGNOSED = "error.diagnosed"
    
    # Система
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    COMPONENT_READY = "component.ready"


class EventBus:
    """Центральная шина событий для связи компонентов"""
    
    def __init__(self, max_history_size: int = 1000):
        self.subscribers: Dict[str, List[Tuple[int, Callable]]] = defaultdict(list)
        self.event_history: List[Event] = []
        self.max_history_size = max_history_size
        self.stats = {
            "total_events": 0,
            "events_by_type": defaultdict(int),
            "events_by_source": defaultdict(int),
            "handler_errors": 0
        }
        logger.info("✅ EventBus инициализирован")
        
    def subscribe(self, event_type: str, handler: Callable, priority: int = 0):
        """
        Подписка на событие
        
        Args:
            event_type: Тип события
            handler: Асинхронная функция-обработчик
            priority: Приоритет обработки (больше = выше приоритет)
        """
        self.subscribers[event_type].append((priority, handler))
        # Сортируем по приоритету (по убыванию)
        self.subscribers[event_type].sort(key=lambda x: x[0], reverse=True)
        logger.debug(f"📌 Подписка {handler.__name__} на {event_type} (приоритет: {priority})")
        
    def unsubscribe(self, event_type: str, handler: Callable):
        """Отписка от события"""
        self.subscribers[event_type] = [
            (p, h) for p, h in self.subscribers[event_type] if h != handler
        ]
        logger.debug(f"🔌 Отписка {handler.__name__} от {event_type}")
        
    async def publish(self, event_type: str, data: Dict[str, Any], 
                     source: str = None, priority: EventPriority = EventPriority.NORMAL):
        """
        Публикация события
        
        Args:
            event_type: Тип события
            data: Данные события
            source: Источник события
            priority: Приоритет события
        """
        event = Event(
            type=event_type,
            data=data,
            source=source or "unknown",
            priority=priority
        )
        
        # Обновляем статистику
        self.stats["total_events"] += 1
        self.stats["events_by_type"][event_type] += 1
        self.stats["events_by_source"][source or "unknown"] += 1
        
        # Сохраняем в историю
        self.event_history.append(event)
        if len(self.event_history) > self.max_history_size:
            self.event_history = self.event_history[-self.max_history_size:]
        
        # Получаем обработчики
        handlers = self.subscribers.get(event_type, [])
        
        if handlers:
            logger.info(f"📢 Событие {event_type} от {source}, обработчиков: {len(handlers)}")
            
            # Выполняем обработчики параллельно
            tasks = []
            for _, handler in handlers:
                task = self._safe_handler_call(handler, event)
                tasks.append(task)
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Считаем ошибки
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                self.stats["handler_errors"] += len(errors)
                
        else:
            logger.debug(f"📢 Событие {event_type} от {source} (нет подписчиков)")
    
    async def _safe_handler_call(self, handler: Callable, event: Event):
        """Безопасный вызов обработчика"""
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"❌ Ошибка в обработчике {handler.__name__}: {e}")
            raise
            
    def get_history(self, event_type: Optional[str] = None, 
                   source: Optional[str] = None,
                   limit: int = 100) -> List[Event]:
        """
        Получение истории событий
        
        Args:
            event_type: Фильтр по типу события
            source: Фильтр по источнику
            limit: Максимальное количество событий
        """
        history = self.event_history
        
        if event_type:
            history = [e for e in history if e.type == event_type]
            
        if source:
            history = [e for e in history if e.source == source]
            
        return history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики событий"""
        return {
            "total_events": self.stats["total_events"],
            "events_by_type": dict(self.stats["events_by_type"]),
            "events_by_source": dict(self.stats["events_by_source"]),
            "handler_errors": self.stats["handler_errors"],
            "subscribers": {k: len(v) for k, v in self.subscribers.items()},
            "history_size": len(self.event_history)
        }
    
    def clear_history(self):
        """Очистка истории событий"""
        self.event_history.clear()
        logger.info("🧹 История событий очищена")
        
    def reset_stats(self):
        """Сброс статистики"""
        self.stats = {
            "total_events": 0,
            "events_by_type": defaultdict(int),
            "events_by_source": defaultdict(int),
            "handler_errors": 0
        }
        logger.info("📊 Статистика сброшена")


# Глобальный экземпляр шины событий
event_bus = EventBus()


# Вспомогательные функции для упрощения работы
async def emit(event_type: str, data: Dict[str, Any], source: str = None):
    """Быстрая публикация события"""
    await event_bus.publish(event_type, data, source)


def on(event_type: str, priority: int = 0):
    """Декоратор для подписки на событие"""
    def decorator(func):
        event_bus.subscribe(event_type, func, priority)
        return func
    return decorator


# Пример использования декоратора:
# @on(EventTypes.PLAN_CREATED)
# async def handle_plan_created(event: Event):
#     print(f"План создан: {event.data}")


if __name__ == "__main__":
    # Пример использования
    async def example():
        # Подписываемся на событие
        @on(EventTypes.PLAN_CREATED, priority=10)
        async def handle_plan(event: Event):
            print(f"Обработка плана: {event.data}")
        
        # Публикуем событие
        await emit(EventTypes.PLAN_CREATED, {"plan_id": "123"}, source="example")
        
        # Получаем статистику
        stats = event_bus.get_stats()
        print(f"Статистика: {stats}")
    
    asyncio.run(example())