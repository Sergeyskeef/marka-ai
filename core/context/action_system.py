"""
Система действий.
"""

import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Deque
from uuid import UUID

from .action import Action
from .action_types import ActionPriority, ActionStatus, ActionType
from .retry_config import RetryConfig

class ActionSystem:
    """Система управления действиями."""
    
    def __init__(self, memory_manager):
        """Инициализация системы действий."""
        self.memory_manager = memory_manager
        self.action_queue: Deque[Action] = deque()
        self.retry_queue: Dict[str, Dict[str, Any]] = {}
        self.action_dependencies: Dict[str, List[str]] = {}
        self._action_types: Dict[str, type] = {}
        self._completed_actions: Dict[str, Action] = {}  # Хранилище выполненных действий
        
    def register_action_type(self, action_type: str, action_class: type) -> None:
        """Регистрация типа действия."""
        self._action_types[action_type] = action_class
        
    async def add_action(self, action: Action, dependencies: Optional[List[str]] = None) -> str:
        """Добавление действия в очередь."""
        if dependencies:
            self.action_dependencies[action.id] = dependencies
            
        # Обновляем время ожидания для всех действий в очереди
        for queued_action in self.action_queue:
            queued_action.update_wait_time()
            
        self.action_queue.append(action)
        
        # Сортируем очередь по динамическому приоритету
        self.action_queue = deque(sorted(
            self.action_queue,
            key=lambda x: x.calculate_dynamic_priority(),
            reverse=True
        ))
        
        return action.id
        
    async def execute_next_action(self) -> Optional[Dict[str, Any]]:
        """Выполнение следующего действия из очереди."""
        if not self.action_queue:
            return None
            
        action = self.action_queue[0]
        
        # Проверяем зависимости
        if not await self._check_dependencies(action):
            return None
            
        try:
            # Обновляем время ожидания перед выполнением
            action.update_wait_time()
            
            result = await action.execute()
            action.status = ActionStatus.COMPLETED.value
            action.completed_at = datetime.utcnow()
            action.result = result
            
            # Сохраняем действие в хранилище выполненных действий
            self._completed_actions[action.id] = action
            
            # Удаляем действие из очереди
            self.action_queue.popleft()
            
            # Удаляем зависимости
            if action.id in self.action_dependencies:
                del self.action_dependencies[action.id]
                
            return result
            
        except Exception as e:
            action.status = ActionStatus.FAILED.value
            action.completed_at = datetime.utcnow()
            action.error = str(e)
            
            # Проверяем возможность повторной попытки
            if action.can_retry():
                action.increment_retry_count()
                next_retry = datetime.utcnow() + timedelta(seconds=action.retry_config.get_delay(action.retry_count))
                
                # Добавляем в очередь повторных попыток
                self.retry_queue[action.id] = {
                    'action': action,
                    'next_retry': next_retry,
                    'error': str(e)
                }
                
                # Удаляем из основной очереди
                self.action_queue.popleft()
                
            return None
            
    async def _check_dependencies(self, action: Action) -> bool:
        """Проверка зависимостей действия."""
        if action.id not in self.action_dependencies:
            return True
            
        dependencies = self.action_dependencies[action.id]
        for dep_id in dependencies:
            # Проверяем, что зависимость выполнена
            for queued_action in self.action_queue:
                if queued_action.id == dep_id:
                    return False
                    
        return True
        
    async def cancel_action(self, action_id: str) -> bool:
        """Отмена действия."""
        for i, action in enumerate(self.action_queue):
            if action.id == action_id:
                action.status = ActionStatus.CANCELLED.value
                self.action_queue.remove(action)
                return True
        return False
        
    async def rollback_action(self, action_id: str) -> bool:
        """Откат действия."""
        # Проверяем в хранилище выполненных действий
        if action_id in self._completed_actions:
            action = self._completed_actions[action_id]
            if action.status == ActionStatus.COMPLETED.value:
                try:
                    await action.rollback()
                    action.status = ActionStatus.ROLLED_BACK.value
                    return True
                except Exception:
                    return False
        return False
        
    def get_queue_status(self) -> Dict[str, Any]:
        """Получение статуса очереди."""
        return {
            'actions_count': len(self.action_queue),
            'retry_count': len(self.retry_queue),
            'actions': [
                {
                    'id': action.id,
                    'type': action.type,
                    'priority': action.priority,
                    'dynamic_priority': action.calculate_dynamic_priority(),
                    'status': action.status,
                    'wait_time': action.wait_time,
                    'retry_count': action.retry_count
                }
                for action in self.action_queue
            ],
            'retry_queue': [
                {
                    'id': action_id,
                    'next_retry': info['next_retry'],
                    'error': info['error']
                }
                for action_id, info in self.retry_queue.items()
            ]
        }
        
    def get_all_actions(self) -> List[Dict[str, Any]]:
        """Получение всех действий."""
        actions = []
        
        # Добавляем действия из основной очереди
        for action in self.action_queue:
            actions.append({
                'id': action.id,
                'type': action.type,
                'priority': action.priority,
                'dynamic_priority': action.calculate_dynamic_priority(),
                'status': action.status,
                'wait_time': action.wait_time,
                'retry_count': action.retry_count
            })
            
        # Добавляем действия из очереди повторных попыток
        for action_id, info in self.retry_queue.items():
            action = info['action']
            actions.append({
                'id': action.id,
                'type': action.type,
                'priority': action.priority,
                'dynamic_priority': action.calculate_dynamic_priority(),
                'status': action.status,
                'wait_time': action.wait_time,
                'retry_count': action.retry_count,
                'next_retry': info['next_retry']
            })
            
        return actions
        
    async def initialize(self) -> None:
        """Инициализация системы действий."""
        # Очищаем очереди
        self.action_queue.clear()
        self.retry_queue.clear()
        self.action_dependencies.clear()
        self._completed_actions.clear()
        
    async def get_recent_actions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение последних выполненных действий."""
        recent_actions = []
        
        # Получаем последние выполненные действия
        completed_actions = list(self._completed_actions.values())
        completed_actions.sort(key=lambda x: x.created_at, reverse=True)
        
        for action in completed_actions[:limit]:
            recent_actions.append({
                'id': action.id,
                'type': action.type,
                'priority': action.priority,
                'status': action.status,
                'created_at': action.created_at,
                'completed_at': action.completed_at,
                'result': action.result
            })
            
        return recent_actions
        
    async def shutdown(self) -> None:
        """Завершение работы системы действий."""
        # Отменяем все действия в очереди
        for action in list(self.action_queue):
            action.status = ActionStatus.CANCELLED.value
            
        # Очищаем очереди
        self.action_queue.clear()
        self.retry_queue.clear()
        self.action_dependencies.clear() 