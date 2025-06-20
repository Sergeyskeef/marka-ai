#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для анализа тональности и важности сообщений.
Используется для улучшения контекста общения в Telegram-боте.
"""

import logging
import re
from typing import Dict, Any, List, Tuple
from langchain_api.utils.openai_proxy_client import openai_client

class MessageAnalyzer:
    """
    Анализатор сообщений для определения тональности и важности.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Ключевые слова для определения важности
        self.importance_keywords = {
            'high': [
                'важно', 'срочно', 'критично', 'необходимо', 'нужно', 'требуется',
                'помоги', 'спаси', 'проблема', 'ошибка', 'не работает', 'сломалось',
                'зависло', 'упало', 'не могу', 'не получается', 'помощь'
            ],
            'medium': [
                'хочу', 'нужно', 'интересно', 'расскажи', 'объясни', 'покажи',
                'как сделать', 'как настроить', 'что делать', 'подскажи'
            ],
            'low': [
                'привет', 'пока', 'спасибо', 'хорошо', 'понятно', 'да', 'нет',
                'ок', 'ладно', 'угу', 'ага'
            ]
        }
        
        # Эмодзи для определения тональности
        self.sentiment_emojis = {
            'positive': ['😊', '😄', '😃', '😁', '😆', '😍', '🥰', '😘', '👍', '❤️', '💕', '✨', '🌟'],
            'negative': ['😞', '😔', '😢', '😭', '😡', '😠', '😤', '😩', '😫', '😰', '😨', '😱', '💔', '😤'],
            'neutral': ['😐', '😑', '😶', '🤔', '🤨', '😏', '😒', '😕', '🙄', '😬', '😅', '😓']
        }
    
    def analyze_message(self, message: str, role: str = "user") -> Dict[str, Any]:
        """
        Анализирует сообщение и возвращает метаданные.
        
        Args:
            message: Текст сообщения
            role: Роль отправителя (user/assistant)
            
        Returns:
            Словарь с метаданными анализа
        """
        if not message or not message.strip():
            return {
                'importance': 'low',
                'sentiment': 'neutral',
                'length': 0,
                'has_question': False,
                'has_command': False,
                'keywords': []
            }
        
        message_lower = message.lower().strip()
        
        # Определяем важность
        importance = self._determine_importance(message_lower)
        
        # Определяем тональность
        sentiment = self._determine_sentiment(message)
        
        # Дополнительные характеристики
        has_question = self._has_question(message)
        has_command = self._has_command(message_lower)
        keywords = self._extract_keywords(message_lower)
        
        return {
            'importance': importance,
            'sentiment': sentiment,
            'length': len(message),
            'has_question': has_question,
            'has_command': has_command,
            'keywords': keywords,
            'word_count': len(message.split())
        }
    
    def _determine_importance(self, message: str) -> str:
        """Определяет важность сообщения на основе ключевых слов."""
        # Сначала проверяем низкую важность (приоритет)
        for keyword in self.importance_keywords['low']:
            if keyword in message:
                return 'low'
        
        # Затем проверяем высокую важность
        for keyword in self.importance_keywords['high']:
            if keyword in message:
                return 'high'
        
        # Затем среднюю важность
        for keyword in self.importance_keywords['medium']:
            if keyword in message:
                return 'medium'
        
        return 'medium'  # По умолчанию средняя важность
    
    def _determine_sentiment(self, message: str) -> str:
        """Определяет тональность сообщения на основе эмодзи и ключевых слов."""
        # Проверяем эмодзи
        for sentiment, emojis in self.sentiment_emojis.items():
            for emoji in emojis:
                if emoji in message:
                    return sentiment
        
        # Проверяем ключевые слова тональности
        positive_words = ['спасибо', 'хорошо', 'отлично', 'супер', 'класс', 'люблю', 'нравится', 'рад', 'доволен']
        negative_words = ['плохо', 'ужасно', 'ненавижу', 'не нравится', 'злит', 'бесит', 'раздражает', 'устал', 'устала']
        
        message_lower = message.lower()
        
        positive_count = sum(1 for word in positive_words if word in message_lower)
        negative_count = sum(1 for word in negative_words if word in message_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    def _has_question(self, message: str) -> bool:
        """Проверяет, содержит ли сообщение вопрос."""
        question_patterns = [
            r'\?$',  # Заканчивается на знак вопроса
            r'\b(что|как|где|когда|почему|зачем|кто|какой|какая|какие|сколько|куда|откуда)\b',
            r'\b(расскажи|объясни|покажи|помоги|подскажи)\b'
        ]
        
        for pattern in question_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def _has_command(self, message: str) -> bool:
        """Проверяет, содержит ли сообщение команду."""
        command_patterns = [
            r'^/',  # Начинается с /
            r'\b(выполни|сделай|создай|удали|измени|настрой|запусти|останови)\b'
        ]
        
        for pattern in command_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def _extract_keywords(self, message: str) -> List[str]:
        """Извлекает ключевые слова из сообщения."""
        # Убираем стоп-слова
        stop_words = {
            'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она',
            'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее',
            'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 'ему', 'теперь', 'когда',
            'даже', 'ну', 'вдруг', 'ли', 'если', 'уже', 'или', 'ни', 'быть', 'был', 'него', 'до',
            'вас', 'нибудь', 'опять', 'уж', 'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей',
            'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для', 'мы', 'тебя', 'их', 'чем',
            'была', 'сам', 'чтоб', 'без', 'будто', 'чего', 'раз', 'тоже', 'себе', 'под', 'будет',
            'ж', 'тогда', 'кто', 'этот', 'того', 'потому', 'этого', 'какой', 'совсем', 'ним', 'здесь',
            'этом', 'один', 'почти', 'мой', 'тем', 'чтобы', 'нее', 'сейчас', 'были', 'куда', 'зачем',
            'всех', 'никогда', 'можно', 'при', 'наконец', 'два', 'об', 'другой', 'хоть', 'после',
            'над', 'больше', 'тот', 'через', 'эти', 'нас', 'про', 'всего', 'них', 'какая', 'много',
            'разве', 'три', 'эту', 'моя', 'впрочем', 'хорошо', 'свою', 'этой', 'перед', 'иногда',
            'лучше', 'чуть', 'том', 'нельзя', 'такой', 'им', 'более', 'всегда', 'притом', 'будет',
            'очень', 'мы', 'вместо', 'оно', 'впрочем', 'хорошо', 'свою', 'этой', 'перед', 'иногда',
            'лучше', 'чуть', 'том', 'нельзя', 'такой', 'им', 'более', 'всегда', 'притом', 'будет',
            'очень', 'мы', 'вместо', 'оно', 'впрочем', 'хорошо', 'свою', 'этой', 'перед', 'иногда'
        }
        
        # Извлекаем слова, убирая знаки препинания
        words = re.findall(r'\b[а-яёa-z]+\b', message.lower())
        
        # Фильтруем стоп-слова и короткие слова
        keywords = []
        for word in words:
            # Проверяем базовую форму слова (убираем окончания)
            base_word = self._get_base_form(word)
            if (base_word not in stop_words and 
                len(base_word) > 2 and 
                base_word not in keywords):
                keywords.append(base_word)
        
        return keywords[:10]  # Возвращаем топ-10 ключевых слов
    
    def _get_base_form(self, word: str) -> str:
        """Получает базовую форму слова (убирает окончания)."""
        # Простая лемматизация для русских слов
        if len(word) <= 3:
            return word
        
        # Убираем типичные окончания
        endings = ['а', 'я', 'о', 'е', 'и', 'ы', 'у', 'ю', 'ом', 'ем', 'ой', 'ей', 'ой', 'ей', 'ых', 'их']
        for ending in endings:
            if word.endswith(ending) and len(word) > len(ending) + 2:
                base = word[:-len(ending)]
                if len(base) >= 3:
                    return base
        
        return word
    
    def analyze_conversation_context(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Анализирует контекст разговора на основе нескольких сообщений.
        
        Args:
            messages: Список сообщений в формате [{'role': 'user', 'content': '...'}, ...]
            
        Returns:
            Словарь с анализом контекста
        """
        if not messages:
            return {
                'overall_sentiment': 'neutral',
                'conversation_importance': 'medium',
                'topic_keywords': [],
                'user_engagement': 'low',
                'conversation_length': 0
            }
        
        # Анализируем каждое сообщение
        analyses = []
        for msg in messages:
            if 'content' in msg and msg['content']:
                analysis = self.analyze_message(msg['content'], msg.get('role', 'user'))
                analyses.append(analysis)
        
        if not analyses:
            return {
                'overall_sentiment': 'neutral',
                'conversation_importance': 'medium',
                'topic_keywords': [],
                'user_engagement': 'low',
                'conversation_length': len(messages)
            }
        
        # Определяем общую тональность
        sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        importance_counts = {'high': 0, 'medium': 0, 'low': 0}
        
        all_keywords = []
        total_length = 0
        
        for analysis in analyses:
            sentiment_counts[analysis['sentiment']] += 1
            importance_counts[analysis['importance']] += 1
            all_keywords.extend(analysis['keywords'])
            total_length += analysis['length']
        
        # Определяем преобладающую тональность
        overall_sentiment = max(sentiment_counts, key=sentiment_counts.get)
        
        # Определяем важность разговора
        conversation_importance = max(importance_counts, key=importance_counts.get)
        
        # Определяем вовлеченность пользователя
        user_messages = [msg for msg in messages if msg.get('role') == 'user']
        avg_user_length = total_length / len(analyses) if analyses else 0
        
        if avg_user_length > 30:
            user_engagement = 'high'
        elif avg_user_length > 15:
            user_engagement = 'medium'
        else:
            user_engagement = 'low'
        
        # Находим наиболее частые ключевые слова
        from collections import Counter
        keyword_counts = Counter(all_keywords)
        topic_keywords = [word for word, count in keyword_counts.most_common(5)]
        
        return {
            'overall_sentiment': overall_sentiment,
            'conversation_importance': conversation_importance,
            'topic_keywords': topic_keywords,
            'user_engagement': user_engagement,
            'conversation_length': len(messages),
            'average_message_length': avg_user_length
        } 