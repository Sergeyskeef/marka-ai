from telegram import Update
from telegram.ext import ContextTypes
from langchain_api.sandbox import MarkSelfAwareness, SandboxIntegrator
from langchain_api.memory.memory_manager import MemoryManager
from langchain_api.sandbox.task_manager import TaskPriority
import json
from pathlib import Path
import asyncio

class SandboxHandler:
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.sandbox_integrator = SandboxIntegrator()
        self.mark_awareness = MarkSelfAwareness()
        
    async def handle_self_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /analyze_self"""
        await update.message.reply_text("Начинаю анализ своей структуры и возможностей...")
        
        try:
            # Получаем описание
            description = self.mark_awareness.get_self_description()
            
            # Сохраняем в память как Experience
            self.memory_manager.add_message(
                sender="self_analysis",
                message=description
            )
            
            # Разбиваем описание на части для отправки в Telegram
            parts = self._split_message(description)
            for part in parts:
                await update.message.reply_text(part)
                
            # Сохраняем структурированные данные как Insight
            structure = self.mark_awareness.analyze_project_structure()
            self.memory_manager.add_message(
                sender="self_analysis_structure",
                message=json.dumps(structure, ensure_ascii=False)
            )
            
            await update.message.reply_text(
                "✅ Анализ завершен. Результаты сохранены в памяти.\n"
                "Теперь я лучше понимаю свою структуру и возможности."
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при анализе: {str(e)}")
            
    async def handle_sandbox_experiment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /sandbox_experiment"""
        if not context.args:
            await update.message.reply_text(
                "Использование: /sandbox_experiment <название эксперимента>\n"
                "Например: /sandbox_experiment test_memory_analysis"
            )
            return
            
        experiment_name = " ".join(context.args)
        await update.message.reply_text(f"Начинаю эксперимент: {experiment_name}")
        
        try:
            # Создаем задачу
            task_id = self.sandbox_integrator.create_experiment_task(
                title=experiment_name,
                description=f"Эксперимент по анализу возможностей: {experiment_name}",
                priority=TaskPriority.HIGH
            )
            
            # Получаем структуру для анализа
            structure = self.mark_awareness.analyze_project_structure()
            
            # Запускаем эксперимент
            results = self.sandbox_integrator.run_experiment(
                task_id=task_id,
                experiment_data={
                    "analysis": structure,
                    "focus": experiment_name
                }
            )
            
            # Сохраняем результаты
            self.memory_manager.add_message(
                sender="sandbox_experiment",
                message=json.dumps(results, ensure_ascii=False)
            )
            
            await update.message.reply_text(
                f"✅ Эксперимент '{experiment_name}' завершен.\n"
                f"Результаты сохранены в памяти."
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при эксперименте: {str(e)}")
            
    def _split_message(self, text: str, max_length: int = 4000) -> list:
        """Разбивает длинное сообщение на части для Telegram"""
        if len(text) <= max_length:
            return [text]
            
        parts = []
        current_part = ""
        
        for line in text.split('\n'):
            if len(current_part) + len(line) + 1 <= max_length:
                current_part += line + '\n'
            else:
                parts.append(current_part)
                current_part = line + '\n'
                
        if current_part:
            parts.append(current_part)
            
        return parts 