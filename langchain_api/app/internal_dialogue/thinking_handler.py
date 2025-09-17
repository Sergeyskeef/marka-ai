"""
Обработчик исчезающих сообщений для показа процесса мышления Марка

Показывает пользователю процесс мышления через временные сообщения,
которые автоматически исчезают через заданное время
"""

import asyncio
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ThinkingMessage:
    """Сообщение процесса мышления"""
    message_id: int
    chat_id: int
    text: str
    timestamp: datetime
    lifetime: int  # секунды
    is_deleted: bool = False
    tg_context: Any | None = None


class ThinkingMessageHandler:
    """
    Обработчик исчезающих сообщений
    
    Основные возможности:
    - Отправляет временные сообщения о процессе мышления
    - Автоматически удаляет сообщения через заданное время
    - Управляет очередью сообщений
    - Показывает прогресс выполнения
    """
    
    def __init__(self):
        self.active_messages: Dict[int, ThinkingMessage] = {}
        self.message_queue: List[ThinkingMessage] = []
        self.is_running = False
        # Персистентные статус‑сообщения по чатам (не удаляются по таймеру)
        self._status_by_chat: Dict[int, int] = {}
        
        # Настройки
        self.max_concurrent_messages = 3
        self.default_lifetime = 30  # секунды
        self.cleanup_interval = 5   # секунды
        
        logger.info("💭 ThinkingMessageHandler инициализирован")
    
    async def start(self):
        """Запускает обработчик сообщений"""
        if self.is_running:
            return
        
        self.is_running = True
        asyncio.create_task(self._cleanup_loop())
        logger.info("🚀 ThinkingMessageHandler запущен")
    
    async def stop(self):
        """Останавливает обработчик сообщений"""
        self.is_running = False
        
        # Удаляем все активные сообщения
        for message in self.active_messages.values():
            await self._delete_message(message)
        
        self.active_messages.clear()
        self.message_queue.clear()
        logger.info("🛑 ThinkingMessageHandler остановлен")
    
    async def show_thinking_step(
        self, 
        chat_id: int, 
        text: str, 
        lifetime: Optional[int] = None,
        tg_context: Any | None = None
    ) -> Optional[int]:
        """
        Показывает шаг процесса мышления
        
        Args:
            chat_id: ID чата в Telegram
            text: Текст сообщения
            lifetime: Время жизни сообщения в секундах
            
        Returns:
            ID сообщения или None в случае ошибки
        """
        try:
            lifetime = lifetime or self.default_lifetime
            
            # Создаем сообщение
            thinking_message = ThinkingMessage(
                message_id=0,  # Будет установлено после отправки
                chat_id=chat_id,
                text=text,
                timestamp=datetime.now(),
                lifetime=lifetime,
                tg_context=tg_context
            )
            
            # Добавляем в очередь
            self.message_queue.append(thinking_message)
            
            # Запускаем обработку очереди
            asyncio.create_task(self._process_message_queue())
            
            logger.info(f"💭 Добавлен шаг мышления в очередь: {text[:50]}...")
            
            return thinking_message.message_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления шага мышления: {e}")
            return None
    
    async def show_progress(
        self, 
        chat_id: int, 
        current_step: int, 
        total_steps: int, 
        description: str,
        lifetime: Optional[int] = None,
        tg_context: Any | None = None
    ) -> Optional[int]:
        """
        Показывает прогресс выполнения задачи
        
        Args:
            chat_id: ID чата в Telegram
            current_step: Текущий шаг
            total_steps: Общее количество шагов
            description: Описание текущего шага
            lifetime: Время жизни сообщения
            
        Returns:
            ID сообщения или None в случае ошибки
        """
        try:
            lifetime = lifetime or self.default_lifetime
            
            # Создаем прогресс-бар
            progress_bar = self._create_progress_bar(current_step, total_steps)
            
            text = f"🔄 Прогресс: {progress_bar}\n{current_step}/{total_steps} - {description}"
            
            return await self.show_thinking_step(chat_id, text, lifetime, tg_context)
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа прогресса: {e}")
            return None
    
    async def show_error(
        self, 
        chat_id: int, 
        error_text: str, 
        lifetime: Optional[int] = None,
        tg_context: Any | None = None
    ) -> Optional[int]:
        """
        Показывает ошибку процесса мышления
        
        Args:
            chat_id: ID чата в Telegram
            error_text: Текст ошибки
            lifetime: Время жизни сообщения
            
        Returns:
            ID сообщения или None в случае ошибки
        """
        try:
            lifetime = lifetime or self.default_lifetime
            
            text = f"❌ Ошибка: {error_text}"
            
            return await self.show_thinking_step(chat_id, text, lifetime, tg_context)
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа ошибки: {e}")
            return None
    
    async def show_success(
        self, 
        chat_id: int, 
        success_text: str, 
        lifetime: Optional[int] = None,
        tg_context: Any | None = None
    ) -> Optional[int]:
        """
        Показывает успешное завершение шага
        
        Args:
            chat_id: ID чата в Telegram
            success_text: Текст успеха
            lifetime: Время жизни сообщения
            
        Returns:
            ID сообщения или None в случае ошибки
        """
        try:
            lifetime = lifetime or self.default_lifetime
            
            text = f"✅ {success_text}"
            
            return await self.show_thinking_step(chat_id, text, lifetime, tg_context)
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа успеха: {e}")
            return None
    
    async def _process_message_queue(self):
        """Обрабатывает очередь сообщений"""
        try:
            while self.message_queue and len(self.active_messages) < self.max_concurrent_messages:
                message = self.message_queue.pop(0)
                
                # Отправляем сообщение
                message_id = await self._send_message(message)
                if message_id:
                    message.message_id = message_id
                    self.active_messages[message_id] = message
                    
                    # Запускаем таймер удаления
                    asyncio.create_task(self._schedule_deletion(message))
                    
                    logger.info(f"📤 Отправлено сообщение мышления: {message_id}")
                
                # Небольшая пауза между сообщениями
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки очереди сообщений: {e}")
    
    async def _send_message(self, message: ThinkingMessage) -> Optional[int]:
        """
        Отправляет сообщение в Telegram
        
        Args:
            message: Сообщение для отправки
            
        Returns:
            ID отправленного сообщения или None в случае ошибки
        """
        try:
            # Если доступен Telegram context — отправляем реальное сообщение
            if message.tg_context and getattr(message.tg_context, "bot", None):
                sent = await message.tg_context.bot.send_message(
                    chat_id=message.chat_id,
                    text=message.text
                )
                logger.info(f"📤 Отправлено TG сообщение: {sent.message_id}")
                return sent.message_id
            else:
                # Fallback: заглушка
                import random
                message_id = random.randint(1000, 9999)
                logger.info(f"📤 (mock) Отправлено сообщение: {message.text[:50]}...")
                return message_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
            return None
    
    async def _schedule_deletion(self, message: ThinkingMessage):
        """Планирует удаление сообщения через заданное время"""
        try:
            await asyncio.sleep(message.lifetime)
            
            if message.message_id in self.active_messages:
                await self._delete_message(message)
                
        except Exception as e:
            logger.error(f"❌ Ошибка планирования удаления: {e}")
    
    async def _delete_message(self, message: ThinkingMessage):
        """
        Удаляет сообщение
        
        Args:
            message: Сообщение для удаления
        """
        try:
            if message.message_id in self.active_messages:
                del self.active_messages[message.message_id]
                message.is_deleted = True
                
                # Удаляем реальное сообщение, если есть контекст
                if message.tg_context and getattr(message.tg_context, "bot", None):
                    try:
                        await message.tg_context.bot.delete_message(
                            chat_id=message.chat_id,
                            message_id=message.message_id
                        )
                        logger.info(f"🗑️ Удалено TG сообщение: {message.message_id}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить TG сообщение {message.message_id}: {e}")
                else:
                    logger.info(f"🗑️ (mock) Удалено сообщение: {message.message_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка удаления сообщения: {e}")
    
    async def _cleanup_loop(self):
        """Цикл очистки устаревших сообщений"""
        while self.is_running:
            try:
                current_time = datetime.now()
                
                # Удаляем сообщения, которые должны были исчезнуть
                messages_to_remove = []
                for message_id, message in self.active_messages.items():
                    if current_time - message.timestamp > timedelta(seconds=message.lifetime):
                        messages_to_remove.append(message_id)
                
                for message_id in messages_to_remove:
                    if message_id in self.active_messages:
                        message = self.active_messages[message_id]
                        await self._delete_message(message)
                
                await asyncio.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле очистки: {e}")
                await asyncio.sleep(self.cleanup_interval)

    async def update_status(
        self,
        chat_id: int,
        text: str,
        tg_context: Any | None = None,
        create_if_missing: bool = True,
    ) -> Optional[int]:
        """
        Создаёт или обновляет персистентное статус‑сообщение в Telegram.
        Сообщение не удаляется автоматически, пока явно не очищено.
        """
        try:
            if not tg_context or not getattr(tg_context, "bot", None):
                return None
            bot = tg_context.bot
            msg_id = self._status_by_chat.get(chat_id)
            if msg_id:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text)
                    return msg_id
                except Exception as e:
                    logger.warning(f"Не удалось обновить статусное сообщение {msg_id}: {e}. Переотправляю…")
                    # Попробуем заново отправить
                    msg_id = None
            if msg_id is None and create_if_missing:
                sent = await bot.send_message(chat_id=chat_id, text=text)
                self._status_by_chat[chat_id] = sent.message_id
                return sent.message_id
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статусного сообщения: {e}")
            return None

    async def clear_status(self, chat_id: int, tg_context: Any | None = None) -> None:
        """Удаляет статус‑сообщение, если оно есть (использовать по желанию)."""
        try:
            msg_id = self._status_by_chat.get(chat_id)
            if not msg_id:
                return
            if tg_context and getattr(tg_context, "bot", None):
                try:
                    await tg_context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    logger.warning(f"Не удалось удалить статусное сообщение {msg_id}: {e}")
            self._status_by_chat.pop(chat_id, None)
        except Exception:
            pass
    
    def _create_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """
        Создает текстовый прогресс-бар
        
        Args:
            current: Текущий шаг
            total: Общее количество шагов
            width: Ширина прогресс-бара
            
        Returns:
            Строка прогресс-бара
        """
        try:
            if total == 0:
                return "█" * width
            
            progress = current / total
            filled_width = int(width * progress)
            
            bar = "█" * filled_width + "░" * (width - filled_width)
            
            return bar
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания прогресс-бара: {e}")
            return "░" * width
    
    def get_active_messages_count(self) -> int:
        """Возвращает количество активных сообщений"""
        return len(self.active_messages)
    
    def get_queue_length(self) -> int:
        """Возвращает длину очереди сообщений"""
        return len(self.message_queue)
    
    async def clear_all_messages(self):
        """Очищает все активные сообщения"""
        try:
            for message in list(self.active_messages.values()):
                await self._delete_message(message)
            
            self.message_queue.clear()
            logger.info("🧹 Все сообщения очищены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки сообщений: {e}")
