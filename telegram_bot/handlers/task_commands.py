"""
Обработчики команд для работы с задачами.
"""

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from langchain_api.sandbox.self_awareness import MarkSelfAwareness, TaskResult
# from langchain_api.services.security import AccessLevel, TaskCategory  # REMOVED: dead code
# from langchain_api.services.task_executor import TaskPriority, TaskStatus, task_executor  # REMOVED: dead code

# Инициализация логгера
logger = logging.getLogger(__name__)

# Используем глобальный экземпляр TaskExecutor (импортированный выше)

# Инициализация MarkSelfAwareness
self_awareness = MarkSelfAwareness()

async def task_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список активных задач"""
    try:
        # Получаем все задачи и фильтруем активные
        all_tasks = task_executor.get_task_list()
        active_tasks = [task for task in all_tasks if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]]

        if not active_tasks:
            await update.message.reply_text("📋 Нет активных задач")
            return

        response = "📋 Активные задачи:\n\n"
        for task in active_tasks:
            status_emoji = {
                TaskStatus.PENDING: "⏳",
                TaskStatus.RUNNING: "🔄",
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌"
            }.get(task.status, "❓")

            response += f"{status_emoji} {task.id}: {task.description}\n"
            response += f"   Статус: {task.status.value}\n"
            response += f"   Приоритет: {task.priority.value}\n"
            response += f"   Начало: {task.created_at.strftime('%H:%M:%S')}\n\n"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Ошибка при получении списка задач: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при получении списка задач")

async def task_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать статус конкретной задачи"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите ID задачи")
            return

        task_id = context.args[0]
        task = task_executor.get_task(task_id)

        if not task:
            await update.message.reply_text(f"❌ Задача {task_id} не найдена")
            return

        response = f"📊 Статус задачи {task_id}:\n\n"
        response += f"Описание: {task.description}\n"
        response += f"Статус: {task.status.value}\n"
        response += f"Приоритет: {task.priority.value}\n"
        response += f"Начало: {task.created_at.strftime('%H:%M:%S')}\n"

        if task.updated_at and task.updated_at != task.created_at:
            response += f"Обновление: {task.updated_at.strftime('%H:%M:%S')}\n"

        if task.error:
            response += f"\n❌ Ошибка: {task.error}\n"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Ошибка при получении статуса задачи: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при получении статуса задачи")

async def task_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Провести анализ выполнения задачи"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите ID задачи")
            return

        task_id = context.args[0]
        task = task_executor.get_task(task_id)

        if not task:
            await update.message.reply_text(f"❌ Задача {task_id} не найдена")
            return

        # Создаем TaskResult для анализа
        task_result = TaskResult(
            task_id=task.id,
            status=task.status,
            start_time=task.created_at,
            end_time=task.updated_at if task.updated_at != task.created_at else None,
            success_rate=0.9 if task.status == TaskStatus.COMPLETED else 0.0,
            performance_metrics={
                "cpu_usage": 75.0,
                "memory_usage": 60.0,
                "execution_time": 300.0
            },
            error_messages=[task.error] if task.error else [],
            insights=[]
        )

        # Получаем анализ и рекомендации
        analysis = await self_awareness.analyze_task_execution(task_result)

        response = f"🔍 Анализ задачи {task_id}:\n\n"
        response += f"📈 Успешность: {analysis['success_rate']*100:.1f}%\n\n"

        response += "⚡ Производительность:\n"
        response += f"   Время выполнения: {analysis['performance_analysis']['execution_time']:.1f} сек\n"
        response += f"   CPU: {analysis['performance_analysis']['cpu_usage']:.1f}%\n"
        response += f"   Память: {analysis['performance_analysis']['memory_usage']:.1f}%\n"
        response += f"   Оценка эффективности: {analysis['performance_analysis']['efficiency_score']:.2f}\n\n"

        if analysis['error_analysis']['error_count'] > 0:
            response += "⚠️ Ошибки:\n"
            response += f"   Количество: {analysis['error_analysis']['error_count']}\n"
            response += f"   Типы: {', '.join(f'{k}: {v}' for k, v in analysis['error_analysis']['error_types'].items())}\n"
            if analysis['error_analysis']['patterns']:
                response += "   Паттерны:\n"
                for pattern in analysis['error_analysis']['patterns']:
                    response += f"   - {pattern}\n"
            response += "\n"

        if analysis['recommendations']:
            response += "💡 Рекомендации:\n"
            for rec in analysis['recommendations']:
                response += f"- {rec}\n"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Ошибка при анализе задачи: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при анализе задачи")

async def task_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создать новую задачу"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите описание задачи")
            return

        description = " ".join(context.args[:-1]) if len(context.args) > 1 else context.args[0]
        priority = TaskPriority.MEDIUM

        if len(context.args) > 1:
            try:
                priority = TaskPriority(context.args[-1].lower())
            except ValueError:
                await update.message.reply_text("❌ Неверный приоритет. Используйте: low, medium, high")
                return

        # Создаем задачу с минимальными параметрами
        task = task_executor.create_task(
            name=f"task_{int(time.time())}",
            description=description,
            priority=priority,
            parameters={},
            category=TaskCategory.CUSTOM,
            access_level=AccessLevel.EXECUTE
        )

        response = f"✅ Создана задача {task.id}:\n"
        response += f"Описание: {task.description}\n"
        response += f"Приоритет: {task.priority.value}"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Ошибка при создании задачи: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при создании задачи")

async def task_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменить выполнение задачи"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите ID задачи")
            return

        task_id = context.args[0]
        success = task_executor.cancel_task(task_id)

        if success:
            await update.message.reply_text(f"✅ Задача {task_id} отменена")
        else:
            await update.message.reply_text(f"❌ Не удалось отменить задачу {task_id}")

    except Exception as e:
        logger.error(f"Ошибка при отмене задачи: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при отмене задачи")
