"""
SecurityManager - сервис для управления безопасностью
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """Уровни доступа"""
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class TaskCategory(Enum):
    """Категории задач"""
    DEFAULT = "default"
    CRITICAL = "critical"
    OPTIONAL = "optional"
    SYSTEM = "system"
    MAINTENANCE = "maintenance"


class SecurityManager:
    """Менеджер безопасности"""
    
    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}
        self.permissions: Dict[str, List[str]] = {}
        self.access_log: List[Dict[str, Any]] = []
        logger.info("✅ SecurityManager инициализирован")
    
    def add_user(self, user_id: str, access_level: AccessLevel = AccessLevel.USER):
        """Добавляет пользователя"""
        self.users[user_id] = {
            "access_level": access_level.value,
            "created_at": datetime.now().isoformat(),
            "last_access": datetime.now().isoformat()
        }
        logger.info(f"👤 Добавлен пользователь: {user_id} (уровень: {access_level.value})")
    
    def check_permission(self, user_id: str, required_level: AccessLevel) -> bool:
        """Проверяет права доступа пользователя"""
        if user_id not in self.users:
            return False
        
        user_level = AccessLevel(self.users[user_id]["access_level"])
        return user_level.value >= required_level.value
    
    def log_access(self, user_id: str, action: str, resource: str, success: bool):
        """Логирует попытку доступа"""
        log_entry = {
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        self.access_log.append(log_entry)
        
        if user_id in self.users:
            self.users[user_id]["last_access"] = datetime.now().isoformat()
        
        level = "INFO" if success else "WARNING"
        logger.log(
            getattr(logging, level),
            f"🔐 Доступ: {user_id} -> {action} {resource} ({'разрешено' if success else 'отклонено'})"
        )
    
    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает информацию о пользователе"""
        return self.users.get(user_id)
    
    def get_access_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Возвращает лог доступа"""
        return self.access_log[-limit:] if self.access_log else []
    
    def validate_task_category(self, category: TaskCategory, user_level: AccessLevel) -> bool:
        """Проверяет, может ли пользователь выполнять задачи данной категории"""
        if category == TaskCategory.SYSTEM:
            return user_level in [AccessLevel.SYSTEM, AccessLevel.ADMIN]
        elif category == TaskCategory.CRITICAL:
            return user_level in [AccessLevel.ADMIN, AccessLevel.SYSTEM]
        else:
            return True  # DEFAULT, OPTIONAL, MAINTENANCE доступны всем
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Возвращает статистику безопасности"""
        return {
            "total_users": len(self.users),
            "access_log_entries": len(self.access_log),
            "users_by_level": {
                level.value: len([u for u in self.users.values() if u["access_level"] == level.value])
                for level in AccessLevel
            }
        }
