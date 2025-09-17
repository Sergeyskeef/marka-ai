"""
Обработчик чата - основная функциональность с интеграцией внутреннего диалога
"""

import logging
import asyncio
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from .base import BaseHandler
from ..keyboards import get_feedback_keyboard
from ..services.memory_service import MemoryService
from ..services import ChatService
from ..middleware.logging import log_error
from telegram.helpers import escape_markdown
from ..config import bot_config

# Импортируем систему внутреннего диалога
try:
    from app.internal_dialogue.manager import InternalDialogueManager
    from app.internal_dialogue.thinking_handler import ThinkingMessageHandler
    from app.internal_dialogue.auto_solver import AutoProblemSolver
    INTERNAL_DIALOGUE_AVAILABLE = True
except ImportError:
    INTERNAL_DIALOGUE_AVAILABLE = False
    InternalDialogueManager = None
    ThinkingMessageHandler = None
    AutoProblemSolver = None

logger = logging.getLogger(__name__)


class ChatHandler(BaseHandler):
    """Обработчик текстовых сообщений и чата с внутренним диалогом"""
    
    def __init__(self, chat_service: ChatService):
        super().__init__(chat_service)
        self.chat_service = chat_service
        
        # Инициализируем систему внутреннего диалога если доступна
        self.internal_dialogue = None
        if INTERNAL_DIALOGUE_AVAILABLE:
            try:
                # Получаем зависимости из контекста приложения
                self._setup_internal_dialogue()
            except Exception as e:
                logger.warning(f"⚠️ Не удалось инициализировать внутренний диалог: {e}")
    
    def _setup_internal_dialogue(self):
        """Настройка системы внутреннего диалога"""
        try:
            # Получаем зависимости из глобального контекста
            from app.agents.mark_agent import MarkAgent
            from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
            from openai import AsyncOpenAI

            # Реальные объекты вместо моков
            openai_client = AsyncOpenAI()
            mark_agent = MarkAgent(client=openai_client)
            memory_adapter = AdvancedMemoryAdapter()

            thinking_handler = ThinkingMessageHandler()
            auto_solver = AutoProblemSolver(mark_agent, memory_adapter)

            self.internal_dialogue = InternalDialogueManager(
                mark_agent=mark_agent,
                memory_adapter=memory_adapter,
                thinking_handler=thinking_handler,
                auto_solver=auto_solver
            )

            asyncio.create_task(thinking_handler.start())
            logger.info("🧠 Система внутреннего диалога инициализирована (реальные компоненты)")

        except Exception as e:
            logger.error(f"❌ Ошибка настройки внутреннего диалога: {e}")
            self.internal_dialogue = None
    
    @log_error
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка текстового сообщения с внутренним диалогом"""
        message = update.message
        if not message or not message.text:
            return
        
        user = update.effective_user
        text = message.text.strip()
        
        # Пропускаем команды
        if text.startswith('/'):
            return
        
        # Показываем индикатор набора
        await self.send_typing_action(update)
        
        # Получаем режим чата
        chat_mode = self.get_chat_mode(context)
        
        # Пытаемся использовать внутренний диалог
        if self.internal_dialogue and bot_config.USE_INTERNAL_DIALOGUE:
            try:
                # Поддержка принудительного включения инструментов: суффикс +tools
                force_tools = False
                if text and "+tools" in text.lower():
                    force_tools = True
                    text = text.replace("+tools", "").strip()
                await self._handle_with_internal_dialogue(update, context, text, user, chat_mode, force_tools)
                return
            except Exception as e:
                logger.error(f"❌ Ошибка внутреннего диалога, переключаемся на обычный режим: {e}")
        
        # Обычная обработка через ChatService
        await self._handle_with_chat_service(update, context, text, user, chat_mode)
    
    async def _handle_with_internal_dialogue(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        user,
        chat_mode: str,
        force_tools: bool = False
    ):
        """Обработка через внутренний диалог"""
        try:
            logger.info(f"🧠 Обрабатываю через внутренний диалог: {text[:50]}...")
            
            # Начинаем сессию внутреннего диалога
            session_id = self.internal_dialogue.dialogue_state.start_session(
                user_id=user.id,
                chat_id=update.message.chat_id
            )
            
            # Обрабатываем сообщение с показом процесса мышления
            # Собираем базовые персональные данные из Telegram (только имя, без фамилии)
            user_name = (
                (getattr(user, "first_name", None) or getattr(user, "username", ""))
            ).strip()

            result = await self.internal_dialogue.process_with_thinking(
                user_message=text,
                chat_id=update.message.chat_id,
                user_id=user.id,
                context={
                    "chat_mode": chat_mode,
                    "tg_context": context,
                    "chat_service": self.chat_service,
                    "user_id": str(user.id),
                    "chat_id": update.message.chat_id,
                    "user_name": user_name,
                    "force_tools": force_tools
                }
            )
            
            # Обновляем статистику сессии
            self.internal_dialogue.dialogue_state.update_session(
                session_id=session_id,
                message_processed=True,
                auto_solved=result.auto_solved,
                llm_processed=not result.auto_solved,
                success=result.success,
                duration=result.total_duration
            )
            
            # Отправляем финальный ответ
            if result.success:
                # Форматируем ответ и отправляем безопасно (экранирование + чанки)
                formatted_response = self._format_internal_dialogue_response(result)
                # Сохраняем последний ответ для /debug
                try:
                    context.user_data["last_response"] = {
                        "content": formatted_response,
                        "metadata": {
                            "total_duration": getattr(result, "total_duration", None),
                            "thinking_steps": len(getattr(result, "thinking_steps", []) or []),
                        },
                        "tool_calls": [],
                    }
                except Exception:
                    pass
                await self._send_safe_reply(update, formatted_response, get_feedback_keyboard(update.message.message_id))
                
                logger.info(f"✅ Внутренний диалог завершен успешно за {result.total_duration:.2f}с")
                
            else:
                # Если внутренний диалог не смог решить, переключаемся на обычный режим
                logger.info("🔄 Внутренний диалог не смог решить, переключаюсь на обычный режим")
                await self._handle_with_chat_service(update, context, text, user, chat_mode)
            
            # Завершаем сессию
            self.internal_dialogue.dialogue_state.end_session(session_id)
            
        except Exception as e:
            logger.error(f"❌ Ошибка внутреннего диалога: {e}")
            # Переключаемся на обычный режим
            await self._handle_with_chat_service(update, context, text, user, chat_mode)
    
    def _format_internal_dialogue_response(self, result) -> str:
        """Форматирует ответ внутреннего диалога"""
        try:
            response = result.final_response
            
            # Информация о методе решения не добавляем, чтобы избежать визуального шума
            
            # Добавляем статистику
            response += f"\n⏱️ Время обработки: {result.total_duration:.2f}с"
            response += f"\n📊 Шагов мышления: {len(result.thinking_steps)}"
            
            # Детали процесса мышления показываем только в DEV_MODE
            from ..config import bot_config
            if bot_config.DEV_MODE and result.thinking_steps:
                response += "\n\n🧠 *Процесс мышления:*"
                for i, step in enumerate(result.thinking_steps, 1):
                    status = "✅" if step.success else "❌"
                    response += f"\n{i}. {status} {step.description}"
                    if step.duration > 0:
                        response += f" ({step.duration:.2f}с)"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования ответа: {e}")
            return result.final_response
    
    async def _handle_with_chat_service(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        user,
        chat_mode: str
    ):
        """Обычная обработка через ChatService"""
        # Синхронный режим
        try:
            response = await self.chat_service.ask_question(
                question=text,
                user_id=str(user.id),
                chat_id=update.message.chat_id,
                mode=chat_mode
            )
            # Сохраняем последний ответ для /debug
            try:
                context.user_data["last_response"] = response
            except Exception:
                pass
            
            formatted = self.chat_service.format_response(response)
            await self._send_safe_reply(update, formatted, get_feedback_keyboard(update.message.message_id))
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке вашего сообщения. Попробуйте еще раз."
            )
    
    def get_chat_mode(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Получает режим чата из контекста"""
        return context.user_data.get("chat_mode", "chat")
    
    async def send_typing_action(self, update: Update):
        """Отправляет индикатор набора текста"""
        try:
            await update.message.chat.send_action("typing")
        except Exception as e:
            logger.debug(f"Не удалось отправить индикатор набора: {e}")

    async def _send_safe_reply(self, update: Update, text: str, reply_markup=None):
        """Отправляет длинные/форматированные ответы безопасно для Telegram.
        1) бьём на чанки <= MAX_MESSAGE_LENGTH
        2) сначала пробуем MarkdownV2 (экранируем), если падает — plain text.
        """
        if not text:
            await update.message.reply_text("…", reply_markup=reply_markup)
            return
        max_len = bot_config.MAX_MESSAGE_LENGTH
        for part in self._chunk_text(text, max_len - 200):
            sent = False
            try:
                safe = escape_markdown(part, version=2)
                await update.message.reply_text(safe or "…", parse_mode="MarkdownV2", reply_markup=reply_markup)
                sent = True
            except Exception:
                pass
            if not sent:
                try:
                    await update.message.reply_text(part, reply_markup=reply_markup)
                    sent = True
                except Exception:
                    # крайний случай — обрезаем и отправляем короткий фрагмент
                    await update.message.reply_text(part[:1000])

    def _chunk_text(self, text: str, size: int):
        # режем по строкам, чтобы не ломать форматирование
        if len(text) <= size:
            yield text
            return
        lines = text.splitlines(True)
        buf = ''
        for ln in lines:
            if len(buf) + len(ln) > size:
                if buf:
                    yield buf
                    buf = ''
                if len(ln) > size:
                    # очень длинная строка — режем грубо
                    for i in range(0, len(ln), size):
                        yield ln[i:i+size]
                else:
                    buf = ln
            else:
                buf += ln
        if buf:
            yield buf


# Функция для обработки текстовых сообщений (для совместимости)
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    chat_service = context.bot_data.get('chat_service')
    if not chat_service:
        await update.message.reply_text("❌ Сервис чата недоступен")
        return
    
    handler = ChatHandler(chat_service)
    await handler.handle(update, context)


# Функция для обработки режимов чата (для совместимости)
async def handle_chat_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора режима чата"""
    query = update.callback_query
    if not query:
        return
    
    try:
        # Извлекаем режим из callback data
        parts = query.data.split(":")
        mode = parts[2] if len(parts) >= 3 else "chat"
        
        # Сохраняем в контексте пользователя
        context.user_data["chat_mode"] = mode
        
        # Отправляем подтверждение
        mode_names = {
            "chat": "💬 Обычный чат",
            "task": "📝 Режим задач", 
            "analysis": "🔍 Аналитический режим"
        }
        
        await query.answer(f"Режим изменен на: {mode_names.get(mode, mode)}")
        
        # Обновляем сообщение
        await query.edit_message_text(
            f"✅ Режим чата изменен на: {mode_names.get(mode, mode)}\n\n"
            "Теперь отправьте сообщение для начала диалога в выбранном режиме."
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка изменения режима чата: {e}")
        await query.answer("❌ Ошибка изменения режима")
        await query.edit_message_text("❌ Произошла ошибка при изменении режима чата")


# Мок для тестирования
class Mock:
    """Простой мок для тестирования"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __getattr__(self, name):
        return Mock()
    
    async def __call__(self, *args, **kwargs):
        return Mock()