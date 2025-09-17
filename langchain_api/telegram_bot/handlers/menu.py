from telegram import Update
from telegram.ext import ContextTypes
from .base import BaseHandler
from ..keyboards import get_main_menu_keyboard, get_memory_menu_keyboard
from ..keyboards.main_menu import get_chat_mode_keyboard
from ..middleware.logging import log_error

class MenuHandler(BaseHandler):
    """Обработчик главного меню и общих кнопок."""

    @log_error
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = (query.data or "").split(":")  # menu:...
        action = data[1] if len(data) > 1 else "main"

        # Логируем клик как эпизод (минимально)
        try:
            if hasattr(context.bot_data, 'chat_service'):
                await context.bot_data['chat_service'].ask_question(
                    question=f"Пользователь нажал кнопку меню: {action}",
                    user_id=str(query.from_user.id),
                    chat_id=query.message.chat_id if query.message else None,
                    mode="analysis"
                )
        except Exception:
            pass

        if action in ("main", "help"):
            await query.edit_message_text(
                "Выберите действие:",
                reply_markup=get_main_menu_keyboard(query.from_user.id)
            )
            return

        if action == "chat" and len(data) >= 3 and data[2] == "new":
            await query.edit_message_text(
                "💬 Новый диалог начат. Напишите сообщение.",
                reply_markup=get_main_menu_keyboard(query.from_user.id)
            )
            # Сбросить локальную историю/флаги (минимально)
            context.user_data.clear()
            return

        if action == "mode":
            current = context.user_data.get("chat_mode", "task")
            await query.edit_message_text(
                f"Выберите режим (текущий: {current})",
                reply_markup=get_chat_mode_keyboard(current)
            )
            return

        if action == "memory":
            await query.edit_message_text(
                "🧠 Управление памятью",
                reply_markup=get_memory_menu_keyboard()
            )
            return

        if action == "learning":
            # Запускаем REAP цикл обучения в фоне и показываем прогресс
            try:
                await query.edit_message_text(
                    "📚 Запускаю обучение (REAP). Это может занять 1–2 минуты…",
                )
                chat_id = query.message.chat_id if query.message else None
                message_id = query.message.message_id if query.message else None

                async def _run_reap():
                    try:
                        from app.learning.reap_cycle import reap_cycle
                        res = await reap_cycle.run_learning_cycle(auto_mode=False)
                        if chat_id and message_id:
                            # Краткий отчёт
                            ref = res.get("reflection", {})
                            kn = res.get("knowledge", {})
                            app = res.get("application", {})
                            txt = (
                                "✅ Обучение завершено\n"
                                f"Эпизод: {res.get('episode_id','—')}\n"
                                f"Инсайтов: {ref.get('insights', 0)}; Паттернов: {ref.get('patterns_found', 0)}\n"
                                f"Фактов: {kn.get('facts_extracted', 0)}; Навыков к обновлению: {kn.get('skills_to_update', 0)}; Уроков: {kn.get('lessons_learned', 0)}\n"
                                f"Применение: {app if isinstance(app, str) else app.get('facts_saved',0)} фактов сохранено"
                            )
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=txt,
                                reply_markup=get_main_menu_keyboard(query.from_user.id)
                            )
                    except Exception as e:
                        if chat_id and message_id:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=message_id,
                                text=f"❌ Ошибка обучения: {e}",
                                reply_markup=get_main_menu_keyboard(query.from_user.id)
                            )
                import asyncio
                asyncio.create_task(_run_reap())
            except Exception:
                await query.edit_message_text(
                    "❌ Не удалось запустить обучение.",
                    reply_markup=get_main_menu_keyboard(query.from_user.id)
                )
            return

        if action == "settings":
            await query.edit_message_text(
                "⚙️ Настройки пока минимальны. Будут расширены позже.",
                reply_markup=get_main_menu_keyboard(query.from_user.id)
            )
            return

        if action == "help":
            await query.edit_message_text(
                "❓ Помощь: напишите свой вопрос, я подскажу.",
                reply_markup=get_main_menu_keyboard(query.from_user.id)
            )
            return

        # fallback
        await query.edit_message_text(
            "Меню обновлено. Выберите действие:",
            reply_markup=get_main_menu_keyboard(query.from_user.id)
        )

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    handler = MenuHandler()
    await handler.handle(update, context)
