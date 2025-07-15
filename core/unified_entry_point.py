"""
Unified Entry Point - Единая точка входа для всех сообщений
Часть архитектуры "Все через мозг" для достижения полной автономности Марка
"""

import logging
from datetime import datetime
from typing import Any

from .brain_processor import BrainProcessor

logger = logging.getLogger(__name__)


class UnifiedEntryPoint:
    """
    Единая точка входа для всех сообщений в системе.

    Цель: Устранить "раздвоение личности" - все сообщения идут одним путем через ИИ-мозг.
    """

    def __init__(self):
        """Инициализация с центральным процессором интеллекта"""
        self.brain_processor = BrainProcessor()
        self.processed_count = 0

        logger.info("🧠 UnifiedEntryPoint инициализирован")

    def process_message(self, message: str, chat_id: int, user_id: int | None = None) -> dict[str, Any]:
        """
        Синхронная обработка любого сообщения через единый pipeline (для Telegram)

        Args:
            message: Текст сообщения (команда или обычный текст)
            chat_id: ID чата Telegram
            user_id: ID пользователя (опционально)

        Returns:
            dict: Стандартизированный ответ с флагами context_used и memory_added
        """
        try:
            self.processed_count += 1

            logger.info(f"📨 Обработка сообщения #{self.processed_count} от chat_id={chat_id}")
            logger.debug(f"💬 Сообщение: {message[:100]}...")

            # ВСЕ сообщения идут через мозг - никаких исключений!
            result = self.brain_processor.process(
                message=message,
                chat_id=chat_id,
                user_id=user_id,
                timestamp=datetime.now()
            )

            logger.info(f"✅ Сообщение обработано успешно. Context: {result.get('context_used')}, Memory: {result.get('memory_added')}")

            return result

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {str(e)}", exc_info=True)

            # Даже ошибки возвращаем в стандартном формате
            return {
                "answer": f"Произошла ошибка при обработке сообщения: {str(e)}",
                "chat_id": chat_id,
                "context_used": False,
                "memory_added": False,
                "error": True,
                "error_message": str(e)
            }

    async def process_message_async(self, message: str, chat_id: int, user_id: int | None = None) -> dict[str, Any]:
        """
        🔄 АСИНХРОННАЯ обработка любого сообщения через единый pipeline (для HTTP API)

        Решает проблему "This event loop is already running" в FastAPI

        Args:
            message: Текст сообщения (команда или обычный текст)
            chat_id: ID чата
            user_id: ID пользователя (опционально)

        Returns:
            dict: Стандартизированный ответ с флагами context_used и memory_added
        """
        try:
            self.processed_count += 1

            logger.info(f"📨 Асинхронная обработка сообщения #{self.processed_count} от chat_id={chat_id}")
            logger.debug(f"💬 Сообщение: {message[:100]}...")

            # ВСЕ сообщения идут через мозг - асинхронно!
            result = await self.brain_processor._process_async(
                message=message,
                chat_id=chat_id,
                user_id=user_id,
                timestamp=datetime.now()
            )

            logger.info(f"✅ Асинхронное сообщение обработано успешно. Context: {result.get('context_used')}, Memory: {result.get('memory_added')}")

            return result

        except Exception as e:
            logger.error(f"❌ Ошибка асинхронной обработки сообщения: {str(e)}", exc_info=True)

            # Даже ошибки возвращаем в стандартном формате
            return {
                "answer": f"Произошла ошибка при обработке сообщения: {str(e)}",
                "chat_id": chat_id,
                "context_used": False,
                "memory_added": False,
                "error": True,
                "error_message": str(e)
            }

    def get_stats(self) -> dict[str, Any]:
        """Получить статистику работы единой точки входа"""
        return {
            "total_processed": self.processed_count,
            "brain_processor_stats": self.brain_processor.get_stats() if hasattr(self.brain_processor, 'get_stats') else {}
        }

    def health_check(self) -> dict[str, Any]:
        """Проверка здоровья системы"""
        try:
            # Проверяем доступность brain_processor
            brain_healthy = self.brain_processor.health_check() if hasattr(self.brain_processor, 'health_check') else True

            return {
                "status": "healthy" if brain_healthy else "unhealthy",
                "unified_entry_point": "operational",
                "brain_processor": "healthy" if brain_healthy else "unhealthy",
                "processed_messages": self.processed_count
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Глобальный экземпляр для использования в системе
unified_entry = UnifiedEntryPoint()
