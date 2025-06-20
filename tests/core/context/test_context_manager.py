"""
Тесты для ContextManager.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from langchain_api.core.context.context_manager import ContextManager
from langchain_api.core.memory.memory_manager import MemoryManager
import asyncio

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
        response = "Это тестовый ответ от LLM"
        query = "Тестовый запрос"
        
        analysis = asyncio.run(self.context_manager.analyze_llm_response(response, query))
        
        self.assertIn('relevance_score', analysis)
        self.assertIn('quality_score', analysis)
        self.assertIn('consistency_score', analysis)
        self.assertIn('semantic_analysis', analysis)
        self.assertIn('key_ideas', analysis)
        self.assertIn('sentiment', analysis)
        
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
        """Тест расширенного анализа LLM."""
        response = "Это сложный ответ с множеством концепций и идей"
        query = "Сложный запрос"
        
        analysis = asyncio.run(self.context_manager.analyze_llm_response(response, query))
        
        self.assertIn('semantic_analysis', analysis)
        semantic = analysis['semantic_analysis']
        
        # Проверяем наличие основных компонентов семантического анализа
        self.assertIn('topics', semantic)
        self.assertIn('entities', semantic)
        self.assertIn('relations', semantic)
        self.assertIn('complexity', semantic)
        
        # Проверяем, что темы извлечены
        self.assertIsInstance(semantic['topics'], list)
        
        # Проверяем, что сущности извлечены
        self.assertIsInstance(semantic['entities'], list)
        
        # Проверяем, что связи извлечены
        self.assertIsInstance(semantic['relations'], list)
        
    def test_update_context_from_analysis(self):
        """Тест обновления контекста на основе анализа."""
        analysis = {
            'key_ideas': [
                {'content': 'Важная идея 1', 'importance': 0.9},
                {'content': 'Важная идея 2', 'importance': 0.8}
            ],
            'semantic_analysis': {
                'topics': ['тема1', 'тема2'],
                'entities': [{'name': 'сущность1', 'type': 'concept'}]
            }
        }
        
        result = asyncio.run(self.context_manager.update_context_from_analysis(analysis))
        
        self.assertTrue(result)
        
        # Проверяем, что контекст обновлен
        context = self.context_manager.get_context()
        self.assertGreater(len(context['key_ideas']), 0)
        self.assertGreater(len(context['topics']), 0)
        self.assertGreater(len(context['entities']), 0)
        
    def test_link_related_ideas(self):
        """Тест связывания связанных идей."""
        # Добавляем ключевые идеи
        analysis = {
            'key_ideas': [
                {'content': 'Идея о машинном обучении', 'importance': 0.9},
                {'content': 'Идея о нейронных сетях', 'importance': 0.8},
                {'content': 'Идея о глубоком обучении', 'importance': 0.7}
            ]
        }
        
        asyncio.run(self.context_manager.update_context_from_analysis(analysis))
        
        # Связываем идеи
        self.context_manager.link_related_ideas()
        
        # Проверяем, что связи созданы
        context = self.context_manager.get_context()
        self.assertGreater(len(context['idea_links']), 0)
        
    def test_prioritize_information(self):
        """Тест приоритизации информации."""
        # Добавляем информацию для приоритизации
        analysis = {
            'key_ideas': [
                {'content': 'Критическая идея', 'importance': 0.95},
                {'content': 'Важная идея', 'importance': 0.8},
                {'content': 'Обычная идея', 'importance': 0.6}
            ]
        }
        
        asyncio.run(self.context_manager.update_context_from_analysis(analysis))
        
        # Приоритизируем информацию
        self.context_manager.prioritize_information()
        
        # Проверяем, что приоритеты установлены
        context = self.context_manager.get_context()
        self.assertGreater(len(context['priorities']), 0)
        
        # Проверяем, что приоритеты отсортированы по убыванию
        priorities = context['priorities']
        for i in range(len(priorities) - 1):
            self.assertGreaterEqual(priorities[i]['score'], priorities[i + 1]['score'])
        
    def test_get_context_summary(self):
        """Тест получения резюме контекста."""
        summary = asyncio.run(self.context_manager.get_context_summary())
        
        assert isinstance(summary, dict)
        assert 'session_id' in summary
        assert 'active_tasks' in summary
        assert 'recent_actions' in summary
        assert 'key_ideas' in summary
        assert 'llm_interactions' in summary
        assert 'context_age_seconds' in summary
        assert 'llm_quality_trend' in summary
        assert 'popular_topics' in summary
        assert 'suggestions_count' in summary
        
    def test_auto_update_context(self):
        """Тест автоматического обновления контекста."""
        result = asyncio.run(self.context_manager.auto_update_context())
        
        assert isinstance(result, dict)
        assert 'status' in result
        assert result['status'] in ['success', 'error']
        
        if result['status'] == 'success':
            assert 'updates_applied' in result
            assert 'trends_analyzed' in result
            assert 'priorities_updated' in result
            assert 'suggestions_generated' in result
            
    def test_analyze_llm_trends(self):
        """Тест анализа трендов LLM."""
        # Добавляем тестовые взаимодействия
        test_interaction = {
            'query': 'test query',
            'response': 'test response',
            'analysis': {
                'quality_score': 0.8,
                'relevance_score': 0.9,
                'semantic_analysis': {
                    'topics': ['test', 'analysis']
                }
            }
        }
        
        self.context_manager.current_context['llm_interactions'] = [test_interaction]
        
        trends = self.context_manager._analyze_llm_trends()
        
        assert isinstance(trends, dict)
        assert 'avg_quality_score' in trends
        assert 'avg_relevance_score' in trends
        assert 'popular_topics' in trends
        assert 'interactions_count' in trends
        assert 'trend_direction' in trends
        
    def test_generate_intelligent_suggestions(self):
        """Тест генерации интеллектуальных подсказок."""
        # Создаем контекст с большим количеством задач
        self.context_manager.current_context['active_tasks'] = [{} for _ in range(6)]
        
        suggestions = self.context_manager._generate_intelligent_suggestions()
        
        assert isinstance(suggestions, list)
        
        # Проверяем, что есть подсказка о приоритизации задач
        task_suggestions = [s for s in suggestions if s.get('type') == 'task_management']
        if task_suggestions:
            assert task_suggestions[0]['priority'] == 'high'
            assert 'приоритизация' in task_suggestions[0]['message']
            
    def test_update_priorities(self):
        """Тест обновления приоритетов."""
        # Добавляем ключевые идеи с важностью
        self.context_manager.current_context['key_ideas'] = [
            {'content': 'idea1', 'importance': 0.8},
            {'content': 'idea2', 'importance': 0.6},
            {'content': 'idea3', 'importance': 0.9}
        ]
        
        updates = self.context_manager._update_priorities()
        
        assert isinstance(updates, dict)
        if 'prioritized_ideas' in updates:
            assert len(updates['prioritized_ideas']) <= 5
            # Проверяем, что идеи отсортированы по важности
            importances = [idea.get('importance', 0) for idea in updates['prioritized_ideas']]
            assert importances == sorted(importances, reverse=True)
            
    def test_add_event_links(self):
        """Тест добавления связей между событиями."""
        event_id = "test_event_1"
        related_events = ["event_2", "event_3"]
        
        result = asyncio.run(self.context_manager.add_event_links(event_id, related_events))
        
        assert result is True
        assert 'event_links' in self.context_manager.current_context
        assert event_id in self.context_manager.current_context['event_links']
        assert self.context_manager.current_context['event_links'][event_id] == related_events 