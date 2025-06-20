from enum import Enum
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
import logging
import time
import psutil
import json
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)

class AccessLevel(Enum):
    """Уровни доступа к задачам"""
    READ = "read"  # Только просмотр
    EXECUTE = "execute"  # Выполнение задач
    MANAGE = "manage"  # Управление задачами
    ADMIN = "admin"  # Полный доступ

class TaskCategory(Enum):
    """Категории задач"""
    SYSTEM = "system"  # Системные задачи
    MEMORY = "memory"  # Работа с памятью
    SANDBOX = "sandbox"  # Работа с песочницей
    ANALYSIS = "analysis"  # Аналитические задачи
    CUSTOM = "custom"  # Пользовательские задачи

@dataclass
class ResourceUsage:
    """Метрики использования ресурсов"""
    cpu_percent: float
    memory_percent: float
    execution_time: float
    timestamp: datetime

@dataclass
class SecurityPolicy:
    required_access_level: AccessLevel
    allowed_categories: list[TaskCategory]
    max_execution_time: int
    max_memory_usage: int
    requires_confirmation: bool = False
    allowed_commands: Set[str] = None
    allowed_paths: Set[str] = None
    max_parallel_tasks: int = 1

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class SecurityManager:
    """Менеджер безопасности для управления доступом к задачам"""
    
    def __init__(self):
        self.policies = {
            "system": SecurityPolicy(
                required_access_level=AccessLevel.ADMIN,
                allowed_categories=[TaskCategory.SYSTEM],
                max_execution_time=300,
                max_memory_usage=512,
                requires_confirmation=True,
                allowed_commands={"restart", "shutdown", "update"},
                allowed_paths={"/etc", "/var"},
                max_parallel_tasks=1
            ),
            "memory": SecurityPolicy(
                required_access_level=AccessLevel.MANAGE,
                allowed_categories=[TaskCategory.MEMORY],
                max_execution_time=60,
                max_memory_usage=256,
                allowed_commands={"read", "write", "delete"},
                allowed_paths={"/memory", "/cache"},
                max_parallel_tasks=3
            ),
            "sandbox": SecurityPolicy(
                required_access_level=AccessLevel.EXECUTE,
                allowed_categories=[TaskCategory.SANDBOX],
                max_execution_time=30,
                max_memory_usage=128,
                requires_confirmation=True,
                allowed_commands={"run", "test", "build"},
                allowed_paths={"/sandbox"},
                max_parallel_tasks=2
            )
        }
        self.default_policy = SecurityPolicy(
            required_access_level=AccessLevel.READ,
            allowed_categories=[TaskCategory.CUSTOM],
            max_execution_time=30,
            max_memory_usage=128,
            allowed_commands={"read"},
            allowed_paths={"/public"},
            max_parallel_tasks=1
        )
        
        # Инициализация мониторинга
        self.resource_usage: Dict[str, List[ResourceUsage]] = {}
        self.active_tasks: Dict[str, datetime] = {}
        self.snapshots_dir = Path("snapshots")
        self.snapshots_dir.mkdir(exist_ok=True)
    
    def validate_task(self, task_name: str, category: TaskCategory, parameters: Dict[str, Any], access_level: AccessLevel) -> bool:
        """Валидация задачи на основе политик безопасности"""
        policy = self.policies.get(task_name, self.default_policy)
        
        # Проверка уровня доступа
        if not self._validate_access_level(access_level, policy.required_access_level):
            logger.warning(f"Недостаточный уровень доступа для задачи {task_name}")
            return False
            
        # Проверка категории
        if not self._validate_category(category, policy.allowed_categories):
            logger.warning(f"Недопустимая категория для задачи {task_name}")
            return False
            
        # Проверка параметров
        if not self._validate_parameters(parameters, task_name):
            logger.warning(f"Недопустимые параметры для задачи {task_name}")
            return False
            
        # Проверка параллельных задач
        if not self._validate_parallel_tasks(task_name, policy.max_parallel_tasks):
            logger.warning(f"Превышен лимит параллельных задач для {task_name}")
            return False
            
        # Проверка ресурсов
        if not self._validate_resources(task_name, policy):
            logger.warning(f"Недостаточно ресурсов для задачи {task_name}")
            return False
            
        return True
    
    def _validate_access_level(self, user_level: AccessLevel, required_level: AccessLevel) -> bool:
        """Проверка уровня доступа"""
        access_levels = {
            AccessLevel.READ: 1,
            AccessLevel.EXECUTE: 2,
            AccessLevel.MANAGE: 3,
            AccessLevel.ADMIN: 4
        }
        return access_levels[user_level] >= access_levels[required_level]
    
    def _validate_category(self, category: TaskCategory, allowed_categories: list[TaskCategory]) -> bool:
        """Проверка категории задачи"""
        return category in allowed_categories
    
    def _validate_parameters(self, parameters: Dict[str, Any], task_name: str) -> bool:
        """Проверка параметров задачи"""
        policy = self.policies.get(task_name, self.default_policy)
        
        if "command" in parameters:
            if parameters["command"] not in policy.allowed_commands:
                return False
                
        if "path" in parameters:
            if not any(parameters["path"].startswith(p) for p in policy.allowed_paths):
                return False
                
        return True
    
    def _validate_parallel_tasks(self, task_name: str, max_parallel: int) -> bool:
        """Проверка количества параллельных задач"""
        active_count = sum(1 for t in self.active_tasks.values() 
                         if (datetime.now() - t).total_seconds() < 300)
        return active_count < max_parallel
    
    def _validate_resources(self, task_name: str, policy: SecurityPolicy) -> bool:
        """Проверка доступности ресурсов"""
        current_usage = self.get_current_resource_usage()
        
        if current_usage.cpu_percent > 90:
            return False
            
        if current_usage.memory_percent > policy.max_memory_usage:
            return False
            
        return True
    
    def get_current_resource_usage(self) -> ResourceUsage:
        """Получение текущего использования ресурсов"""
        process = psutil.Process()
        return ResourceUsage(
            cpu_percent=process.cpu_percent(),
            memory_percent=process.memory_percent(),
            execution_time=time.time() - process.create_time(),
            timestamp=datetime.now()
        )
    
    def track_task_start(self, task_name: str):
        """Отслеживание начала выполнения задачи"""
        self.active_tasks[task_name] = datetime.now()
        self.resource_usage[task_name] = []
    
    def track_task_end(self, task_name: str):
        """Отслеживание завершения задачи"""
        if task_name in self.active_tasks:
            del self.active_tasks[task_name]
        if task_name in self.resource_usage:
            del self.resource_usage[task_name]
    
    def update_resource_usage(self, task_name: str):
        """Обновление метрик использования ресурсов"""
        if task_name in self.resource_usage:
            self.resource_usage[task_name].append(self.get_current_resource_usage())
    
    def create_snapshot(self, task_name: str) -> str:
        """Создает снапшот состояния задачи"""
        # Сохраняем все resource_usage как словарь списков dict'ов
        resource_usage_serialized = {
            t: [vars(u) for u in usages]
            for t, usages in self.resource_usage.items()
        }
        snapshot = {
            "task_name": task_name,
            "timestamp": datetime.now(),
            "resource_usage": resource_usage_serialized,
            "active_tasks": list(self.active_tasks.keys())
        }
        
        snapshot_dir = Path("snapshots")
        snapshot_dir.mkdir(exist_ok=True)
        snapshot_path = snapshot_dir / f"snapshot_{task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(snapshot_path, "w") as f:
            json.dump(snapshot, f, indent=2, cls=DateTimeEncoder)
            
        return str(snapshot_path)
    
    def restore_from_snapshot(self, snapshot_path: str) -> bool:
        """Восстановление из снапшота"""
        try:
            with open(snapshot_path) as f:
                snapshot = json.load(f)
            # Восстановление активных задач
            self.active_tasks = {
                task: datetime.fromisoformat(snapshot["timestamp"])
                for task in snapshot["active_tasks"]
            }
            # Восстановление метрик ресурсов
            self.resource_usage = {}
            for task_name, usage_list in snapshot["resource_usage"].items():
                self.resource_usage[task_name] = [ResourceUsage(
                    cpu_percent=u["cpu_percent"],
                    memory_percent=u["memory_percent"],
                    execution_time=u["execution_time"],
                    timestamp=datetime.fromisoformat(u["timestamp"])
                ) for u in usage_list]
            return True
        except Exception as e:
            logger.error(f"Ошибка при восстановлении из снапшота: {e}")
            return False
    
    def requires_confirmation(self, task_name: str) -> bool:
        """Проверка необходимости подтверждения для задачи"""
        policy = self.policies.get(task_name, self.default_policy)
        return policy.requires_confirmation
    
    def get_resource_limits(self, task_name: str) -> Dict[str, int]:
        """Получение лимитов ресурсов для задачи"""
        policy = self.policies.get(task_name, self.default_policy)
        return {
            "max_execution_time": policy.max_execution_time,
            "max_memory_usage": policy.max_memory_usage,
            "max_parallel_tasks": policy.max_parallel_tasks
        } 