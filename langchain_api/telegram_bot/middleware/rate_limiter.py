"""
Rate limiter для ограничения частоты запросов
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..config import bot_config

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter с поддержкой разных лимитов для разных типов пользователей
    """
    
    def __init__(
        self,
        default_limit: int = None,
        window_seconds: int = None,
        admin_multiplier: int = 3
    ):
        self.default_limit = default_limit or bot_config.RATE_LIMIT_REQUESTS
        self.window = timedelta(seconds=window_seconds or bot_config.RATE_LIMIT_WINDOW)
        self.admin_multiplier = admin_multiplier
        
        # Хранилище запросов: user_id -> list of timestamps
        self.requests: Dict[int, List[datetime]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    def get_limit_for_user(self, user_id: int) -> int:
        """Получить лимит для конкретного пользователя"""
        # В режиме разработки все получают админский лимит
        if bot_config.DEV_MODE:
            return self.default_limit * self.admin_multiplier
        
        # В production режиме проверяем список админов
        if user_id in bot_config.ADMIN_USERS:
            return self.default_limit * self.admin_multiplier
        return self.default_limit
    
    async def check_rate_limit(self, user_id: int) -> tuple[bool, Optional[int]]:
        """
        Проверить rate limit для пользователя
        
        Returns:
            (allowed, seconds_until_reset) - разрешен ли запрос и время до сброса
        """
        async with self._lock:
            now = datetime.now()
            user_requests = self.requests[user_id]
            
            # Удаляем старые запросы
            user_requests[:] = [
                req_time for req_time in user_requests 
                if now - req_time < self.window
            ]
            
            # Получаем лимит для пользователя
            limit = self.get_limit_for_user(user_id)
            
            # Проверяем лимит
            if len(user_requests) >= limit:
                # Вычисляем время до сброса
                oldest_request = min(user_requests)
                reset_time = oldest_request + self.window
                seconds_until_reset = int((reset_time - now).total_seconds())
                
                logger.warning(
                    f"Rate limit exceeded for user {user_id}: "
                    f"{len(user_requests)}/{limit} requests"
                )
                
                return False, seconds_until_reset
            
            # Добавляем текущий запрос
            user_requests.append(now)
            return True, None
    
    async def __call__(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        Middleware функция для python-telegram-bot
        
        Returns:
            True если запрос разрешен, False если превышен лимит
        """
        if not update.effective_user:
            return True
        
        user_id = update.effective_user.id
        allowed, seconds_until_reset = await self.check_rate_limit(user_id)
        
        if not allowed:
            # Отправляем сообщение о превышении лимита
            message = (
                f"⚠️ Превышен лимит запросов!\n\n"
                f"Попробуйте снова через {seconds_until_reset} секунд."
            )
            
            if update.message:
                await update.message.reply_text(message)
            elif update.callback_query:
                await update.callback_query.answer(message, show_alert=True)
            
            return False
        
        return True
    
    async def reset_user(self, user_id: int) -> None:
        """Сбросить счетчик для пользователя"""
        async with self._lock:
            self.requests[user_id].clear()
            logger.info(f"Rate limit reset for user {user_id}")
    
    async def get_user_stats(self, user_id: int) -> Dict[str, any]:
        """Получить статистику для пользователя"""
        async with self._lock:
            now = datetime.now()
            user_requests = self.requests[user_id]
            
            # Очищаем старые
            user_requests[:] = [
                req_time for req_time in user_requests 
                if now - req_time < self.window
            ]
            
            limit = self.get_limit_for_user(user_id)
            
            return {
                "current_requests": len(user_requests),
                "limit": limit,
                "remaining": max(0, limit - len(user_requests)),
                "is_admin": user_id in bot_config.ADMIN_USERS,
                "window_seconds": self.window.total_seconds()
            }