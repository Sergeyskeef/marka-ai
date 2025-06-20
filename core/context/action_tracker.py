"""
Модуль для отслеживания действий в системе.
"""

from typing import Dict, List, Optional, Any, Type
from datetime import datetime
import json
import uuid
from .action import Action
from ..memory.memory_manager import MemoryManager

class ActionTracker:
    """
    Класс для отслеживания действий в системе.
    
    Отвечает за:
    - Отслеживание всех действий
    - Сохранение действий в память
    - Анализ последовательности действий
    - Генерацию отчетов
    """
    
    def __init__(self, memory_manager: MemoryManager):
        """
        Инициализация трекера действий.
        
        Args:
            memory_manager: Менеджер памяти для интеграции с системой памяти
        """
        self.memory_manager = memory_manager
        self.actions: List[Action] = []
        
    def track_action(self, action: Action) -> str:
        """
        Отслеживание действия.
        
        Args:
            action: Экземпляр действия
            
        Returns:
            ID действия
        """
        self.actions.append(action)
        action.save_to_memory()
        return action.id
        
    def get_actions(self, action_type: Optional[str] = None, limit: int = 10) -> List[Action]:
        """
        Получение списка действий.
        
        Args:
            action_type: Фильтр по типу действия
            limit: Максимальное количество действий
            
        Returns:
            Список действий
        """
        actions = self.actions
        if action_type:
            actions = [a for a in actions if a.type == action_type]
        return actions[-limit:]
        
    def get_action_sequence(self, start_time: datetime, end_time: datetime) -> List[Action]:
        """
        Получение последовательности действий за период.
        
        Args:
            start_time: Начало периода
            end_time: Конец периода
            
        Returns:
            Список действий за период
        """
        return [
            a for a in self.actions
            if start_time <= datetime.fromisoformat(a.timestamp.replace('Z', '+00:00')) <= end_time
        ]
        
    def generate_report(self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Генерация отчета по действиям.
        
        Args:
            start_time: Начальное время
            end_time: Конечное время
            
        Returns:
            Отчет по действиям
        """
        actions = self.actions
        if start_time:
            actions = [a for a in actions if datetime.fromisoformat(a.timestamp) >= start_time]
        if end_time:
            actions = [a for a in actions if datetime.fromisoformat(a.timestamp) <= end_time]
            
        # Группируем действия по типу
        action_types = {}
        for action in actions:
            action_type = action.type
            if action_type not in action_types:
                action_types[action_type] = []
            action_types[action_type].append(action)
            
        return {
            'total_actions': len(actions),
            'action_types': {k: len(v) for k, v in action_types.items()},
            'time_range': {
                'start': start_time.isoformat() if start_time else None,
                'end': end_time.isoformat() if end_time else None
            }
        } 
        
    def get_action_by_id(self, action_id: str) -> Optional[Action]:
        """
        Получение действия по ID.
        
        Args:
            action_id: ID действия
            
        Returns:
            Действие или None, если не найдено
        """
        for action in self.actions:
            if action.id == action_id:
                return action
        return None
        
    def get_actions_by_status(self, status: str) -> List[Action]:
        """
        Получение действий по статусу.
        
        Args:
            status: Статус действия
            
        Returns:
            Список действий с указанным статусом
        """
        return [a for a in self.actions if a.status == status]
        
    def get_actions_by_session(self, session_id: str) -> List[Action]:
        """
        Получение действий по ID сессии.
        
        Args:
            session_id: ID сессии
            
        Returns:
            Список действий для указанной сессии
        """
        return [a for a in self.actions if a.session_id == session_id] 