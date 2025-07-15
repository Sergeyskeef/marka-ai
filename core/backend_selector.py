#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend Selector для A/B тестирования памяти
Реализует переключение между различными backend'ами памяти.
"""

import os
import logging
from typing import Dict, Any, Optional, Type, Union
from enum import Enum

# Настройка логирования
logger = logging.getLogger(__name__)

class MemoryBackend(Enum):
    """Доступные backend'ы памяти"""
    GRAPHITI = "graphiti"
    AUTO = "auto"  # Автоматический выбор на основе доступности

class BackendSelector:
    """
    Селектор backend'а памяти для A/B тестирования и миграции.
    
    Поддерживает:
    - Переменную окружения MEMORY_BACKEND=graphiti|auto
    - Query-параметр ?backend= для ручных тестов
    - Fallback логику при недоступности backend'а
    - Мониторинг производительности разных backend'ов
    """
    
    def __init__(self):
        # Настройки из окружения
        self.default_backend = MemoryBackend(
            os.getenv('MEMORY_BACKEND', 'auto').lower()
        )
        
        # Настройки A/B тестирования
        self.ab_test_enabled = os.getenv('AB_TEST_MEMORY', 'true').lower() == 'true'
        self.ab_test_ratio = float(os.getenv('AB_TEST_RATIO', '0.5'))  # 50/50 по умолчанию
        
        # Настройки fallback
        self.fallback_enabled = os.getenv('MEMORY_FALLBACK_ENABLED', 'true').lower() == 'true'
        self.fallback_timeout = int(os.getenv('MEMORY_FALLBACK_TIMEOUT', '5'))
        
        logger.info(f"✅ BackendSelector инициализирован (default={self.default_backend.value}, ab_test={self.ab_test_enabled})")
    
    def get_memory_class(self, 
                         backend: Optional[str] = None, 
                         session_id: Optional[str] = None,
                         force_fallback: bool = False) -> Type:
        """
        Получить класс памяти на основе выбранного backend'а.
        
        Args:
            backend: Принудительный выбор backend'а (из query-параметра)
            session_id: ID сессии для A/B тестирования
            force_fallback: Принудительно использовать fallback
            
        Returns:
            Класс памяти (GraphitiMemoryAdapter)
        """
        try:
            # Импортируем классы здесь, чтобы избежать циклических импортов
            from langchain_api.memory.graphiti_memory import GraphitiMemoryAdapter
            
            # Определяем backend для использования
            selected_backend = self._determine_backend(backend, session_id, force_fallback)
            
            if selected_backend == MemoryBackend.GRAPHITI:
                # Проверяем доступность GraphitiMemory
                if self._is_graphiti_available():
                    logger.debug(f"🧠 Используем GraphitiMemory для backend={selected_backend.value}")
                    return GraphitiMemoryAdapter
                else:
                    raise RuntimeError("GraphitiMemory недоступен")
            
            else:  # AUTO
                # Автоматический выбор на основе доступности
                if self._is_graphiti_available():
                    logger.debug(f"🤖 AUTO: GraphitiMemory доступен, используем его")
                    return GraphitiMemoryAdapter
                else:
                    logger.debug(f"🤖 AUTO: GraphitiMemory недоступен, fallback на GraphitiMemory")
                    return GraphitiMemoryAdapter
        
        except Exception as e:
            logger.error(f"❌ Ошибка выбора backend'а: {e}")
            if self.fallback_enabled:
                logger.info(f"🔄 Fallback на GraphitiMemoryAdapter")
                from langchain_api.memory.graphiti_memory import GraphitiMemoryAdapter
                return GraphitiMemoryAdapter
            else:
                raise
    
    def create_memory_instance(self, 
                             short_term_limit: int = 20,
                             backend: Optional[str] = None,
                             session_id: Optional[str] = None,
                             **kwargs) -> Union['GraphitiMemoryAdapter', 'MultiLayerMemory']:
        """
        Создать экземпляр памяти с выбранным backend'ом.
        
        Args:
            short_term_limit: Лимит краткосрочной памяти
            backend: Принудительный выбор backend'а
            session_id: ID сессии для A/B тестирования
            **kwargs: Дополнительные параметры
            
        Returns:
            Экземпляр GraphitiMemoryAdapter
        """
        memory_class = self.get_memory_class(backend, session_id)
        
        try:
            # 🔗 F2: Используем Connection Pool для избежания переинициализации
            from langchain_api.core.connection_pool import get_connection_pool
            pool = get_connection_pool()
            
            instance = pool.get_graphiti_memory_adapter(short_term_limit)
            logger.info(f"✅ Использован кешированный экземпляр GraphitiMemoryAdapter (limit={short_term_limit})")
            return instance
        except Exception as e:
            logger.error(f"❌ Ошибка создания {memory_class.__name__}: {e}")
            raise
    
    def _determine_backend(self, 
                          backend: Optional[str], 
                          session_id: Optional[str],
                          force_fallback: bool) -> MemoryBackend:
        """Определить backend для использования"""
        
        if force_fallback:
            return MemoryBackend.GRAPHITI
        
        # Приоритет: query-параметр > A/B тест > default
        if backend:
            try:
                return MemoryBackend(backend.lower())
            except ValueError:
                logger.warning(f"⚠️ Неизвестный backend '{backend}', используем default")
        
        # A/B тестирование на основе session_id
        if self.ab_test_enabled and session_id:
            return MemoryBackend.GRAPHITI  # Всегда используем GraphitiMemory
        
        return self.default_backend
    

    
    def _is_graphiti_available(self) -> bool:
        """Проверить доступность GraphitiMemory"""
        try:
            from langchain_api.core.graphiti_config import get_graphiti_config
            
            config = get_graphiti_config()
            if not config.enabled:
                return False
            
            # Быстрая проверка health endpoint
            import requests
            response = requests.get(
                f"{config.base_url}/health",
                timeout=self.fallback_timeout
            )
            return response.status_code == 200
        
        except Exception as e:
            logger.debug(f"GraphitiMemory недоступен: {e}")
            return False
    
    def get_backend_status(self) -> Dict[str, Any]:
        """Получить статус всех backend'ов"""
        status = {
            'default_backend': self.default_backend.value,
            'ab_test_enabled': self.ab_test_enabled,
            'ab_test_ratio': self.ab_test_ratio,
            'fallback_enabled': self.fallback_enabled,
            'backends': {}
        }
        
        # Проверяем GraphitiMemory
        try:
            graphiti_available = self._is_graphiti_available()
            status['backends']['graphiti'] = {
                'available': graphiti_available,
                'status': 'healthy' if graphiti_available else 'unavailable'
            }
        except Exception as e:
            status['backends']['graphiti'] = {
                'available': False,
                'status': f'error: {e}'
            }
        

        
        return status
    
    def switch_backend(self, new_backend: str) -> bool:
        """
        Переключить default backend (для runtime изменений).
        
        Args:
            new_backend: Новый backend (graphiti|auto)
            
        Returns:
            True если переключение успешно
        """
        try:
            new_backend_enum = MemoryBackend(new_backend.lower())
            old_backend = self.default_backend
            self.default_backend = new_backend_enum
            
            logger.info(f"🔄 Backend переключен: {old_backend.value} → {new_backend_enum.value}")
            return True
        
        except ValueError:
            logger.error(f"❌ Неизвестный backend: {new_backend}")
            return False

# Глобальный экземпляр селектора
backend_selector = BackendSelector()

# Удобные функции для использования в проекте
def get_memory_class(backend: Optional[str] = None, 
                    session_id: Optional[str] = None) -> Type:
    """Получить класс памяти"""
    return backend_selector.get_memory_class(backend, session_id)

def create_memory(short_term_limit: int = 20,
                 backend: Optional[str] = None,
                 session_id: Optional[str] = None,
                 **kwargs) -> 'GraphitiMemoryAdapter':
    """Создать экземпляр памяти"""
    return backend_selector.create_memory_instance(
        short_term_limit=short_term_limit,
        backend=backend,
        session_id=session_id,
        **kwargs
    )

def get_backend_status() -> Dict[str, Any]:
    """Получить статус backend'ов"""
    return backend_selector.get_backend_status()

def switch_default_backend(backend: str) -> bool:
    """Переключить default backend"""
    return backend_selector.switch_backend(backend)

if __name__ == "__main__":
    # Тестирование селектора
    selector = BackendSelector()
    
    print("=== Backend Selector Test ===")
    print(f"Default backend: {selector.default_backend.value}")
    
    status = selector.get_backend_status()
    print(f"Backend status: {status}")
    
    # Тест создания экземпляров
    try:
        memory = selector.create_memory_instance(backend="graphiti")
        print(f"✅ GraphitiMemory создан: {type(memory).__name__}")
    except Exception as e:
        print(f"❌ GraphitiMemory ошибка: {e}")
    
 