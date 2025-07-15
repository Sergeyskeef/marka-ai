"""
MemoryManager - менеджер памяти для управления различными типами памяти
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryManager:
    """Менеджер памяти"""
    
    def __init__(self):
        self.memory_instances = {}
        self.memory_stats = {
            "total_entries": 0,
            "memory_types": []
        }
        logger.info("✅ MemoryManager инициализирован")
    
    def register_memory(self, name: str, memory_instance: Any):
        """Регистрирует экземпляр памяти"""
        self.memory_instances[name] = memory_instance
        self.memory_stats["memory_types"].append(name)
        logger.info(f"🧠 Зарегистрирована память: {name}")
    
    def get_memory(self, name: str) -> Optional[Any]:
        """Возвращает экземпляр памяти по имени"""
        return self.memory_instances.get(name)
    
    def list_memories(self) -> List[str]:
        """Возвращает список зарегистрированных типов памяти"""
        return list(self.memory_instances.keys())
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Возвращает статистику памяти"""
        stats = self.memory_stats.copy()
        stats["registered_memories"] = len(self.memory_instances)
        return stats
    
    def clear_memory(self, name: str) -> bool:
        """Очищает память по имени"""
        if name in self.memory_instances:
            memory = self.memory_instances[name]
            if hasattr(memory, 'clear_all'):
                memory.clear_all()
            elif hasattr(memory, 'clear'):
                memory.clear()
            logger.info(f"🧹 Очищена память: {name}")
            return True
        return False
    
    def clear_all_memories(self):
        """Очищает все типы памяти"""
        for name in self.memory_instances:
            self.clear_memory(name)
        logger.info("🧹 Очищены все типы памяти")


# Глобальный экземпляр MemoryManager
memory_manager = MemoryManager() 