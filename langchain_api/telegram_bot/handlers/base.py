"""
Базовый класс для обработчиков команд
"""

import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

from telegram import Update
from telegram.ext import ContextTypes

from ..services import ChatService
from ..config import bot_config

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """
    Базовый класс для всех обработчиков
    """
    
    def __init__(self, chat_service: Optional[ChatService] = None):
        self.chat_service = chat_service
        self.config = bot_config
    
    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Основной метод обработки"""
        pass
    
    def get_user_data(self, context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
        """Получить данные пользователя из контекста"""
        return context.user_data
    
    def set_user_data(self, context: ContextTypes.DEFAULT_TYPE, key: str, value: Any) -> None:
        """Установить данные пользователя"""
        context.user_data[key] = value
    
    def get_chat_mode(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Получить текущий режим чата"""
        # По умолчанию режим задач
        return context.user_data.get("chat_mode", "task")
    
    def set_chat_mode(self, context: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
        """Установить режим чата"""
        context.user_data["chat_mode"] = mode
    
    async def send_typing_action(self, update: Update) -> None:
        """Отправить индикатор набора текста"""
        if update.effective_chat:
            await update.effective_chat.send_action("typing")
    
    def split_long_message(self, text: str, max_length: int = None) -> list[str]:
        """
        Разбить длинное сообщение на части
        
        Args:
            text: Текст для разбивки
            max_length: Максимальная длина части
            
        Returns:
            Список частей сообщения
        """
        max_length = max_length or self.config.MAX_MESSAGE_LENGTH
        
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        # Разбиваем по параграфам
        paragraphs = text.split("\n\n")
        
        for paragraph in paragraphs:
            # Если параграф сам по себе слишком длинный
            if len(paragraph) > max_length:
                # Разбиваем по предложениям
                sentences = paragraph.split(". ")
                for sentence in sentences:
                    if len(current_part) + len(sentence) + 2 < max_length:
                        if current_part:
                            current_part += ". " + sentence
                        else:
                            current_part = sentence
                    else:
                        if current_part:
                            parts.append(current_part)
                        current_part = sentence
            else:
                # Добавляем параграф целиком
                if len(current_part) + len(paragraph) + 2 < max_length:
                    if current_part:
                        current_part += "\n\n" + paragraph
                    else:
                        current_part = paragraph
                else:
                    if current_part:
                        parts.append(current_part)
                    current_part = paragraph
        
        # Добавляем последнюю часть
        if current_part:
            parts.append(current_part)
        
        return parts
    
    def escape_markdown(self, text: str) -> str:
        """Экранировать специальные символы Markdown"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text