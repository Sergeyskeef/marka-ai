"""
Тесты для ContextManager.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from langchain_api.core.context.context_manager import ContextManager
from langchain_api.core.memory.memory_manager import MemoryManager

class TestContextManager(unittest.TestCase):
    """Тесты для ContextManager."""
    
    def setUp(self):
        """Подготовка тестового окружения."""
        self.memory_manager = MagicMock(spec=MemoryManager)
        self.memory_manager.memory_registry = {
            'Experience': MagicMock()
        }
        self.context_manager = ContextManager(self.memory_manager)
        
    def test_analyze_llm_response(self):
        """Тест анализа ответа LLM."""
        query = "Как работает Python?"
        response = "Python - это интерпретируемый язык программирования. Он поддерживает множество парадигм программирования."
        
        analysis = self.context_manager.analyze_llm_response(response, query)
        
        # Проверяем структуру анализа
        self.assertIn('relevance_score', analysis)
        self.assertIn('quality_score', analysis)
        self.assertIn('consistency_score', analysis)
        self.assertIn('timestamp', analysis)
        
        # Проверяем значения
        self.assertGreaterEqual(analysis['relevance_score'], 0.0)
        self.assertLessEqual(analysis['relevance_score'], 1.0)
        self.assertGreaterEqual(analysis['quality_score'], 0.0)
        self.assertLessEqual(analysis['quality_score'], 1.0)
        self.assertGreaterEqual(analysis['consistency_score'], 0.0)
        self.assertLessEqual(analysis['consistency_score'], 1.0)
        
        # Проверяем сохранение в контекст
        self.assertEqual(len(self.context_manager.current_context['llm_interactions']), 1)
        interaction = self.context_manager.current_context['llm_interactions'][0]
        self.assertEqual(interaction['query'], query)
        self.assertEqual(interaction['response'], response)
        
    def test_calculate_relevance(self):
        """Тест расчета релевантности."""
        # Тест с релевантным ответом
        query = "Python programming"
        response = "Python is a programming language"
        relevance = self.context_manager._calculate_relevance(response, query)
        self.assertGreater(relevance, 0.5)
        
        # Тест с нерелевантным ответом
        query = "Python programming"
        response = "Java is a different language"
        relevance = self.context_manager._calculate_relevance(response, query)
        self.assertLess(relevance, 0.5)
        
        # Тест с пустым запросом
        query = ""
        response = "Some response"
        relevance = self.context_manager._calculate_relevance(response, query)
        self.assertEqual(relevance, 0.0)
        
    def test_calculate_quality(self):
        """Тест расчета качества."""
        # Тест с качественным ответом
        response = "# Заголовок\n\n- Пункт 1\n- Пункт 2\n\nПодробное описание."
        quality = self.context_manager._calculate_quality(response)
        self.assertGreater(quality, 0.5)
        
        # Тест с коротким ответом
        response = "Короткий ответ"
        quality = self.context_manager._calculate_quality(response)
        self.assertLess(quality, 0.5)
        
        # Тест с пустым ответом
        response = ""
        quality = self.context_manager._calculate_quality(response)
        self.assertEqual(quality, 0.0)
        
    def test_check_consistency(self):
        """Тест проверки консистентности."""
        # Тест с консистентным ответом
        response = "Python - это язык программирования. Он поддерживает ООП."
        consistency = self.context_manager._check_consistency(response)
        self.assertEqual(consistency, 1.0)
        
        # Тест с противоречивым ответом
        response = "Python - это язык программирования. Python - это не язык программирования."
        consistency = self.context_manager._check_consistency(response)
        self.assertEqual(consistency, 0.0)
        
        # Тест с пустым ответом
        response = ""
        consistency = self.context_manager._check_consistency(response)
        self.assertEqual(consistency, 0.0)
        
    def test_save_llm_interaction(self):
        """Тест сохранения взаимодействия с LLM."""
        interaction = {
            'query': "Test query",
            'response': "Test response",
            'analysis': {
                'relevance_score': 0.8,
                'quality_score': 0.7,
                'consistency_score': 1.0
            }
        }
        
        self.context_manager._save_llm_interaction(interaction)
        
        # Проверяем вызов метода insert
        self.memory_manager.memory_registry['Experience'].insert.assert_called_once()
        call_args = self.memory_manager.memory_registry['Experience'].insert.call_args[0][0]
        
        # Проверяем структуру сохраненных данных
        self.assertIn('summary', call_args)
        self.assertIn('content', call_args)
        self.assertIn('timestamp', call_args)
        self.assertIn('session_id', call_args)
        self.assertIn('type', call_args)
        self.assertEqual(call_args['type'], 'llm_interaction')
        
    def test_analyze_semantics(self):
        """Тест семантического анализа."""
        # Тест с техническим текстом
        text = "Python - это язык программирования. API позволяет взаимодействовать с системой. LLM обрабатывает контекст."
        analysis = self.context_manager._analyze_semantics(text)
        
        # Проверяем структуру анализа
        self.assertIn('topics', analysis)
        self.assertIn('entities', analysis)
        self.assertIn('relations', analysis)
        self.assertIn('complexity', analysis)
        
        # Проверяем результаты
        self.assertGreater(len(analysis['topics']), 0)
        self.assertGreater(len(analysis['entities']), 0)
        self.assertGreater(len(analysis['relations']), 0)
        self.assertGreater(analysis['complexity'], 0.0)
        
        # Тест с пустым текстом
        analysis = self.context_manager._analyze_semantics("")
        self.assertEqual(len(analysis['topics']), 0)
        self.assertEqual(len(analysis['entities']), 0)
        self.assertEqual(len(analysis['relations']), 0)
        self.assertEqual(analysis['complexity'], 0.0)
        
    def test_extract_key_ideas(self):
        """Тест извлечения ключевых идей."""
        # Тест с текстом, содержащим ключевые идеи
        text = "Важно понимать основы Python. API является ключевым компонентом. LLM обрабатывает данные."
        ideas = self.context_manager._extract_key_ideas(text)
        
        # Проверяем результаты
        self.assertGreater(len(ideas), 0)
        for idea in ideas:
            self.assertIn('text', idea)
            self.assertIn('importance', idea)
            self.assertIn('type', idea)
            
        # Проверяем типы идей
        types = [idea['type'] for idea in ideas]
        self.assertIn('key_point', types)
        self.assertIn('technical_info', types)
        
        # Тест с пустым текстом
        ideas = self.context_manager._extract_key_ideas("")
        self.assertEqual(len(ideas), 0)
        
    def test_analyze_sentiment(self):
        """Тест анализа тональности."""
        # Тест с позитивным текстом
        text = "Хорошо работает система. Отлично обрабатываются данные."
        sentiment = self.context_manager._analyze_sentiment(text)
        
        # Проверяем структуру
        self.assertIn('positive', sentiment)
        self.assertIn('negative', sentiment)
        self.assertIn('neutral', sentiment)
        
        # Проверяем значения
        self.assertGreater(sentiment['positive'], 0.0)
        self.assertEqual(sentiment['negative'], 0.0)
        
        # Тест с негативным текстом
        text = "Плохо работает система. Ошибка в обработке данных."
        sentiment = self.context_manager._analyze_sentiment(text)
        self.assertGreater(sentiment['negative'], 0.0)
        self.assertEqual(sentiment['positive'], 0.0)
        
        # Тест с нейтральным текстом
        text = "Система обрабатывает данные."
        sentiment = self.context_manager._analyze_sentiment(text)
        self.assertEqual(sentiment['positive'], 0.0)
        self.assertEqual(sentiment['negative'], 0.0)
        self.assertEqual(sentiment['neutral'], 1.0)
        
        # Тест с пустым текстом
        sentiment = self.context_manager._analyze_sentiment("")
        self.assertEqual(sentiment['positive'], 0.0)
        self.assertEqual(sentiment['negative'], 0.0)
        self.assertEqual(sentiment['neutral'], 1.0)
        
    def test_extended_llm_analysis(self):
        """Тест расширенного анализа ответа LLM."""
        query = "Как работает Python?"
        response = "Python - это интерпретируемый язык программирования. Он эффективно обрабатывает данные. Важно понимать основы языка."
        
        analysis = self.context_manager.analyze_llm_response(response, query)
        
        # Проверяем расширенные поля анализа
        self.assertIn('semantic_analysis', analysis)
        self.assertIn('key_ideas', analysis)
        self.assertIn('sentiment', analysis)
        
        # Проверяем семантический анализ
        semantic = analysis['semantic_analysis']
        self.assertIn('topics', semantic)
        self.assertIn('entities', semantic)
        self.assertIn('relations', semantic)
        self.assertIn('complexity', semantic)
        
        # Проверяем ключевые идеи
        self.assertGreater(len(analysis['key_ideas']), 0)
        
        # Проверяем тональность
        sentiment = analysis['sentiment']
        self.assertIn('positive', sentiment)
        self.assertIn('negative', sentiment)
        self.assertIn('neutral', sentiment)
        
    def test_update_context_from_analysis(self):
        """Тест автоматического обновления контекста на основе анализа."""
        # Подготавливаем тестовые данные
        query = "Как работает Python?"
        response = "Python - это интерпретируемый язык программирования. Он эффективно обрабатывает данные. Важно понимать основы языка."
        
        # Получаем анализ
        analysis = self.context_manager.analyze_llm_response(response, query)
        
        # Обновляем контекст
        self.context_manager.update_context_from_analysis(analysis)
        
        # Проверяем обновление контекста
        context = self.context_manager.get_context()
        
        # Проверяем наличие ключевых идей в контексте
        self.assertIn('key_ideas', context)
        self.assertGreater(len(context['key_ideas']), 0)
        
        # Проверяем наличие тем в контексте
        self.assertIn('topics', context)
        self.assertGreater(len(context['topics']), 0)
        
        # Проверяем наличие сущностей в контексте
        self.assertIn('entities', context)
        self.assertGreater(len(context['entities']), 0)
        
        # Проверяем наличие связей в контексте
        self.assertIn('relations', context)
        self.assertGreater(len(context['relations']), 0)
        
        # Проверяем обновление временной метки
        self.assertIn('last_update', context)
        self.assertIsInstance(datetime.fromisoformat(context['last_update']), datetime)
        
    def test_link_related_ideas(self):
        """Тест связывания связанных идей в контексте."""
        # Подготавливаем тестовые данные
        query = "Как работает Python?"
        response = "Python - это интерпретируемый язык программирования. Он эффективно обрабатывает данные. Важно понимать основы языка."
        
        # Получаем анализ
        analysis = self.context_manager.analyze_llm_response(response, query)
        
        # Обновляем контекст
        self.context_manager.update_context_from_analysis(analysis)
        
        # Связываем идеи
        self.context_manager.link_related_ideas()
        
        # Проверяем наличие связей
        context = self.context_manager.get_context()
        self.assertIn('idea_links', context)
        self.assertGreater(len(context['idea_links']), 0)
        
        # Проверяем структуру связей
        for link in context['idea_links']:
            self.assertIn('source', link)
            self.assertIn('target', link)
            self.assertIn('type', link)
            self.assertIn('strength', link)
            
    def test_prioritize_information(self):
        """Тест приоритизации информации в контексте."""
        # Подготавливаем тестовые данные
        query = "Как работает Python?"
        response = "Python - это интерпретируемый язык программирования. Он эффективно обрабатывает данные. Важно понимать основы языка."
        
        # Получаем анализ
        analysis = self.context_manager.analyze_llm_response(response, query)
        
        # Обновляем контекст
        self.context_manager.update_context_from_analysis(analysis)
        
        # Приоритизируем информацию
        self.context_manager.prioritize_information()
        
        # Проверяем наличие приоритетов
        context = self.context_manager.get_context()
        self.assertIn('priorities', context)
        self.assertGreater(len(context['priorities']), 0)
        
        # Проверяем структуру приоритетов
        for priority in context['priorities']:
            self.assertIn('item', priority)
            self.assertIn('score', priority)
            self.assertIn('reason', priority)
            
        # Проверяем сортировку по приоритету
        priorities = context['priorities']
        for i in range(len(priorities) - 1):
            self.assertGreaterEqual(priorities[i]['score'], priorities[i + 1]['score']) 