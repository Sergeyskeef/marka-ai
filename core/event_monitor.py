"""
Event Monitor - модуль для мониторинга и логирования событий
"""

import logging
from datetime import datetime
from typing import Dict, Any

from core.event_bus import event_bus, EventTypes, Event, on

logger = logging.getLogger(__name__)


class EventMonitor:
    """Мониторинг и аналитика событий системы"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.event_counts = {}
        self.error_events = []
        self.performance_metrics = {}
        
        # Подписываемся на все важные события
        self._subscribe_to_events()
        logger.info("✅ EventMonitor инициализирован")
    
    def _subscribe_to_events(self):
        """Подписка на события для мониторинга"""
        
        # Планирование
        event_bus.subscribe(EventTypes.PLAN_CREATED, self._handle_plan_created, priority=5)
        event_bus.subscribe(EventTypes.PLAN_EXECUTED, self._handle_plan_executed, priority=5)
        event_bus.subscribe(EventTypes.PLAN_FAILED, self._handle_plan_failed, priority=10)
        
        # Песочница
        event_bus.subscribe(EventTypes.SANDBOX_EXECUTED, self._handle_sandbox_executed, priority=5)
        event_bus.subscribe(EventTypes.SANDBOX_BLOCKED, self._handle_sandbox_blocked, priority=10)
        event_bus.subscribe(EventTypes.SANDBOX_ERROR, self._handle_sandbox_error, priority=10)
        
        # Память
        event_bus.subscribe(EventTypes.MEMORY_STORED, self._handle_memory_stored, priority=5)
        event_bus.subscribe(EventTypes.MEMORY_SEARCHED, self._handle_memory_searched, priority=5)
        
        # Ошибки
        event_bus.subscribe(EventTypes.ERROR_OCCURRED, self._handle_error, priority=15)
        
    async def _handle_plan_created(self, event: Event):
        """Обработка создания плана"""
        logger.info(f"📋 План создан: {event.data.get('goal', 'Unknown')[:50]}... ({event.data.get('subtasks_count', 0)} задач)")
        self._increment_counter("plans_created")
        
    async def _handle_plan_executed(self, event: Event):
        """Обработка выполнения плана"""
        logger.info(f"✅ План выполнен: {event.data.get('plan_id')} - {event.data.get('completed_tasks')}/{event.data.get('total_tasks')} задач")
        self._increment_counter("plans_executed")
        
    async def _handle_plan_failed(self, event: Event):
        """Обработка неудачного плана"""
        logger.error(f"❌ План не выполнен: {event.data.get('plan_id')} - {event.data.get('error')}")
        self._increment_counter("plans_failed")
        self.error_events.append(event)
        
    async def _handle_sandbox_executed(self, event: Event):
        """Обработка выполнения команды в песочнице"""
        exec_time = event.data.get('execution_time', 0)
        logger.info(f"🔧 Песочница выполнила: {event.data.get('command', '')[:50]}... за {exec_time:.2f}с")
        self._increment_counter("sandbox_executions")
        self._update_performance("sandbox_exec_time", exec_time)
        
    async def _handle_sandbox_blocked(self, event: Event):
        """Обработка блокировки команды"""
        logger.warning(f"🚫 Песочница заблокировала: {event.data.get('command', '')[:50]}... - {event.data.get('reason')}")
        self._increment_counter("sandbox_blocks")
        
    async def _handle_sandbox_error(self, event: Event):
        """Обработка ошибки песочницы"""
        logger.error(f"❌ Ошибка песочницы: {event.data.get('error')}")
        self._increment_counter("sandbox_errors")
        self.error_events.append(event)
        
    async def _handle_memory_stored(self, event: Event):
        """Обработка сохранения в память"""
        logger.debug(f"💾 Сохранено в память: {event.data.get('text_preview', '')[:50]}...")
        self._increment_counter("memory_stores")
        self._update_performance("memory_size", event.data.get('size', 0))
        
    async def _handle_memory_searched(self, event: Event):
        """Обработка поиска в памяти"""
        logger.debug(f"🔍 Поиск в памяти: {event.data.get('query', '')[:50]}...")
        self._increment_counter("memory_searches")
        
    async def _handle_error(self, event: Event):
        """Обработка ошибок"""
        logger.error(f"🚨 Ошибка в системе: {event.data.get('error_type')} - {event.data.get('error_message')}")
        self._increment_counter("system_errors")
        self.error_events.append(event)
        
    def _increment_counter(self, counter_name: str):
        """Увеличение счетчика событий"""
        self.event_counts[counter_name] = self.event_counts.get(counter_name, 0) + 1
        
    def _update_performance(self, metric_name: str, value: float):
        """Обновление метрик производительности"""
        if metric_name not in self.performance_metrics:
            self.performance_metrics[metric_name] = {
                "count": 0,
                "total": 0,
                "min": value,
                "max": value
            }
        
        metric = self.performance_metrics[metric_name]
        metric["count"] += 1
        metric["total"] += value
        metric["min"] = min(metric["min"], value)
        metric["max"] = max(metric["max"], value)
        metric["avg"] = metric["total"] / metric["count"]
    
    def get_report(self) -> Dict[str, Any]:
        """Получение отчета о работе системы"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "event_counts": self.event_counts,
            "performance_metrics": self.performance_metrics,
            "error_count": len(self.error_events),
            "recent_errors": [
                {
                    "type": e.type,
                    "message": e.data.get("error_message", e.data.get("error", "Unknown")),
                    "timestamp": e.timestamp.isoformat()
                }
                for e in self.error_events[-10:]  # Последние 10 ошибок
            ],
            "event_bus_stats": event_bus.get_stats()
        }
    
    def print_summary(self):
        """Вывод краткой сводки"""
        report = self.get_report()
        
        print("\n📊 === Сводка работы системы ===")
        print(f"⏱️  Время работы: {report['uptime_seconds']:.0f} сек")
        print("\n📈 Счетчики событий:")
        for name, count in report['event_counts'].items():
            print(f"   {name}: {count}")
        
        print("\n⚡ Метрики производительности:")
        for name, metrics in report['performance_metrics'].items():
            print(f"   {name}:")
            print(f"     - Среднее: {metrics['avg']:.2f}")
            print(f"     - Мин/Макс: {metrics['min']:.2f} / {metrics['max']:.2f}")
            print(f"     - Всего: {metrics['count']} операций")
        
        if report['error_count'] > 0:
            print(f"\n❌ Ошибок: {report['error_count']}")
            for error in report['recent_errors'][-3:]:
                print(f"   - {error['type']}: {error['message'][:100]}...")


# Глобальный экземпляр монитора
event_monitor = EventMonitor()


# Пример использования с декоратором
@on(EventTypes.PLAN_CREATED, priority=1)
async def log_plan_creation(event: Event):
    """Дополнительное логирование создания планов"""
    plan_id = event.data.get("plan_id")
    logger.debug(f"[AUDIT] План {plan_id} создан пользователем {event.data.get('user_id', 'unknown')}")