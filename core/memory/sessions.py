#!/usr/bin/env python3
"""
Session Buffer для короткой памяти
Буфер на 20 сообщений с автоматическим удалением старых
"""
import json
import logging
import os
from typing import List, Optional, Dict, Any
import redis

logger = logging.getLogger(__name__)


class SessionBuffer:
    """Буфер сессий для короткой памяти пользователей"""
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://redis:6379')
        self.max_len = int(os.getenv('SESSION_MAX_LEN', '20'))
        self.redis_client = None
        self._connect()
    
    def _connect(self):
        """Подключение к Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Проверка подключения
            self.redis_client.ping()
            logger.info(f"✅ Подключение к Redis установлено: {self.redis_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Redis: {e}")
            self.redis_client = None
    
    def _get_session_key(self, user_id: str) -> str:
        """Получить ключ сессии для пользователя"""
        return f"sess:{user_id}"
    
    def add_message(self, user_id: str, message: Dict[str, Any]) -> bool:
        """
        Добавить сообщение в сессию пользователя
        
        Args:
            user_id: ID пользователя
            message: Сообщение в формате {"role": "user", "content": "текст", "timestamp": "..."}
        
        Returns:
            bool: True если успешно добавлено
        """
        if not self.redis_client:
            logger.warning("Redis недоступен, сообщение не добавлено")
            return False
        
        try:
            key = self._get_session_key(user_id)
            message_json = json.dumps(message, ensure_ascii=False)
            
            # Добавляем сообщение в начало списка
            self.redis_client.lpush(key, message_json)
            
            # Обрезаем список до максимальной длины
            self.redis_client.ltrim(key, 0, self.max_len - 1)
            
            # Устанавливаем TTL (24 часа)
            self.redis_client.expire(key, 86400)
            
            logger.debug(f"✅ Сообщение добавлено в сессию {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления сообщения в сессию: {e}")
            return False
    
    def get_session(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Получить сессию пользователя
        
        Args:
            user_id: ID пользователя
        
        Returns:
            List[Dict]: Список сообщений в сессии
        """
        if not self.redis_client:
            logger.warning("Redis недоступен, возвращаем пустую сессию")
            return []
        
        try:
            key = self._get_session_key(user_id)
            messages_json = self.redis_client.lrange(key, 0, -1)
            
            messages = []
            for msg_json in messages_json:
                try:
                    message = json.loads(msg_json)
                    messages.append(message)
                except json.JSONDecodeError:
                    logger.warning(f"Некорректный JSON в сессии {user_id}: {msg_json}")
                    continue
            
            # Возвращаем в правильном порядке (новые в конце)
            messages.reverse()
            logger.debug(f"✅ Получена сессия {user_id}: {len(messages)} сообщений")
            return messages
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения сессии {user_id}: {e}")
            return []
    
    def clear_session(self, user_id: str) -> bool:
        """
        Очистить сессию пользователя
        
        Args:
            user_id: ID пользователя
        
        Returns:
            bool: True если успешно очищено
        """
        if not self.redis_client:
            logger.warning("Redis недоступен, сессия не очищена")
            return False
        
        try:
            key = self._get_session_key(user_id)
            self.redis_client.delete(key)
            logger.info(f"✅ Сессия {user_id} очищена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки сессии {user_id}: {e}")
            return False
    
    def get_session_length(self, user_id: str) -> int:
        """
        Получить количество сообщений в сессии
        
        Args:
            user_id: ID пользователя
        
        Returns:
            int: Количество сообщений
        """
        if not self.redis_client:
            return 0
        
        try:
            key = self._get_session_key(user_id)
            return self.redis_client.llen(key)
        except Exception as e:
            logger.error(f"❌ Ошибка получения длины сессии {user_id}: {e}")
            return 0
    
    def is_connected(self) -> bool:
        """Проверить подключение к Redis"""
        if not self.redis_client:
            return False
        
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False


# Глобальный экземпляр буфера сессий
session_buffer = SessionBuffer()


def get_session_buffer() -> SessionBuffer:
    """Получить глобальный экземпляр буфера сессий"""
    return session_buffer


def add_message_to_session(user_id: str, role: str, content: str, **kwargs) -> bool:
    """
    Удобная функция для добавления сообщения в сессию
    
    Args:
        user_id: ID пользователя
        role: Роль сообщения ("user", "assistant", "system")
        content: Содержимое сообщения
        **kwargs: Дополнительные поля
    
    Returns:
        bool: True если успешно добавлено
    """
    import time
    
    message = {
        "role": role,
        "content": content,
        "timestamp": time.time(),
        **kwargs
    }
    
    return session_buffer.add_message(user_id, message)


def get_user_session(user_id: str) -> List[Dict[str, Any]]:
    """
    Удобная функция для получения сессии пользователя
    
    Args:
        user_id: ID пользователя
    
    Returns:
        List[Dict]: Список сообщений в сессии
    """
    return session_buffer.get_session(user_id) 