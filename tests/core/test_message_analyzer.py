#!/usr/bin/env python3
"""
Тесты для MessageAnalyzer.
"""

import pytest

from core.message_analyzer import MessageAnalyzer


class TestMessageAnalyzer:
    """Тесты для MessageAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Создает экземпляр MessageAnalyzer для тестов."""
        return MessageAnalyzer()

    def test_analyze_message_empty(self, analyzer):
        """Тест анализа пустого сообщения."""
        result = analyzer.analyze_message("")
        assert result['importance'] == 'low'
        assert result['sentiment'] == 'neutral'
        assert result['length'] == 0
        assert result['has_question'] is False
        assert result['has_command'] is False

    def test_analyze_message_importance_high(self, analyzer):
        """Тест определения высокой важности."""
        result = analyzer.analyze_message("Помоги, у меня проблема с кодом!")
        assert result['importance'] == 'high'
        assert 'проблем' in result['keywords']

    def test_analyze_message_importance_medium(self, analyzer):
        """Тест определения средней важности."""
        result = analyzer.analyze_message("Расскажи, как настроить систему")
        assert result['importance'] == 'medium'
        assert 'расскаж' in result['keywords']

    def test_analyze_message_importance_low(self, analyzer):
        """Тест определения низкой важности."""
        result = analyzer.analyze_message("Спасибо, понятно")
        assert result['importance'] == 'low'

    def test_analyze_message_sentiment_positive(self, analyzer):
        """Тест определения позитивной тональности."""
        result = analyzer.analyze_message("Спасибо, отлично работает! 😊")
        assert result['sentiment'] == 'positive'

    def test_analyze_message_sentiment_negative(self, analyzer):
        """Тест определения негативной тональности."""
        result = analyzer.analyze_message("Плохо работает, злит 😡")
        assert result['sentiment'] == 'negative'

    def test_analyze_message_sentiment_neutral(self, analyzer):
        """Тест определения нейтральной тональности."""
        result = analyzer.analyze_message("Как дела?")
        assert result['sentiment'] == 'neutral'

    def test_analyze_message_has_question(self, analyzer):
        """Тест определения вопроса."""
        result = analyzer.analyze_message("Что делать дальше?")
        assert result['has_question'] is True

    def test_analyze_message_has_command(self, analyzer):
        """Тест определения команды."""
        result = analyzer.analyze_message("/help")
        assert result['has_command'] is True

    def test_analyze_message_keywords(self, analyzer):
        """Тест извлечения ключевых слов."""
        result = analyzer.analyze_message("Как настроить систему мониторинга?")
        assert len(result['keywords']) > 0
        assert 'систем' in result['keywords']

    def test_analyze_conversation_context_empty(self, analyzer):
        """Тест анализа пустого контекста."""
        result = analyzer.analyze_conversation_context([])
        assert result['overall_sentiment'] == 'neutral'
        assert result['conversation_importance'] == 'medium'
        assert result['user_engagement'] == 'low'

    def test_analyze_conversation_context_simple(self, analyzer):
        """Тест анализа простого контекста."""
        messages = [
            {'role': 'user', 'content': 'Привет'},
            {'role': 'assistant', 'content': 'Привет! Как дела?'},
            {'role': 'user', 'content': 'Хорошо, спасибо'}
        ]
        result = analyzer.analyze_conversation_context(messages)
        assert result['conversation_length'] == 3
        assert result['overall_sentiment'] in ['positive', 'neutral']

    def test_analyze_conversation_context_important(self, analyzer):
        """Тест анализа важного контекста."""
        messages = [
            {'role': 'user', 'content': 'Помоги, критичная проблема!'},
            {'role': 'assistant', 'content': 'Конечно, давайте разберемся'},
            {'role': 'user', 'content': 'Система не работает, срочно нужно исправить'}
        ]
        result = analyzer.analyze_conversation_context(messages)
        assert result['conversation_importance'] == 'high'
        assert result['user_engagement'] == 'high'

    def test_analyze_conversation_context_negative(self, analyzer):
        """Тест анализа негативного контекста."""
        messages = [
            {'role': 'user', 'content': 'Все плохо 😞'},
            {'role': 'assistant', 'content': 'Понимаю, давайте найдем решение'},
            {'role': 'user', 'content': 'Ничего не получается 😡'}
        ]
        result = analyzer.analyze_conversation_context(messages)
        assert result['overall_sentiment'] == 'negative'

    def test_analyze_message_length(self, analyzer):
        """Тест анализа длины сообщения."""
        long_message = "Это очень длинное сообщение с множеством слов для тестирования анализа длины"
        result = analyzer.analyze_message(long_message)
        assert result['length'] == len(long_message)
        assert result['word_count'] > 5

    def test_analyze_message_stop_words(self, analyzer):
        """Тест фильтрации стоп-слов."""
        result = analyzer.analyze_message("И в во не что он на я с со как")
        # Стоп-слова должны быть отфильтрованы
        assert len(result['keywords']) == 0

    def test_analyze_message_emoji_sentiment(self, analyzer):
        """Тест определения тональности по эмодзи."""
        result = analyzer.analyze_message("Отлично! ❤️")
        assert result['sentiment'] == 'positive'

        result = analyzer.analyze_message("Плохо 😢")
        assert result['sentiment'] == 'negative'

        result = analyzer.analyze_message("Хм 🤔")
        assert result['sentiment'] == 'neutral'
