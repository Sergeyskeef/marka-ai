"""
Тесты для расширенной системы памяти.
"""

import unittest
from datetime import datetime, timedelta

from langchain_api.core.memory.enhanced_memory import EnhancedMemory, InsightType


class TestEnhancedMemory(unittest.TestCase):
    """Тесты для класса EnhancedMemory."""

    def setUp(self):
        """Подготовка тестового окружения."""
        self.memory = EnhancedMemory()

    def test_insert_and_search(self):
        """Тест вставки и поиска данных."""
        # Подготовка данных
        data = {
            'content': 'Test memory content',
            'type': 'test',
            'meta': {'source': 'test'}
        }

        # Вставка данных
        self.memory.insert(data)

        # Проверка поиска
        results = self.memory.search({'type': 'test'})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], 'Test memory content')

    def test_pattern_analysis(self):
        """Тест анализа паттернов."""
        # Подготовка данных
        data = {
            'content': 'Test memory content with important words',
            'type': 'test'
        }

        # Вставка данных
        self.memory.insert(data)

        # Проверка паттернов
        patterns = self.memory.get_patterns()
        self.assertIn('test', patterns)
        self.assertIn('memory', patterns)
        self.assertIn('content', patterns)

    def test_categorization(self):
        """Тест категоризации."""
        # Подготовка данных
        data = {
            'content': 'Test memory content',
            'type': 'test_category'
        }

        # Вставка данных
        self.memory.insert(data)

        # Проверка категорий
        categories = self.memory.get_categories()
        self.assertIn('test_category', categories)
        self.assertEqual(len(categories['test_category']), 1)

    def test_importance_scoring(self):
        """Тест оценки важности."""
        # Подготовка данных
        data = {
            'content': 'Test memory content',
            'type': 'test',
            'meta': {'source': 'test'}
        }

        # Вставка данных
        self.memory.insert(data)

        # Проверка оценок важности
        scores = self.memory.get_importance_scores()
        self.assertEqual(len(scores), 1)
        self.assertGreater(list(scores.values())[0], 0.5)

    def test_search_by_patterns(self):
        """Тест поиска по паттернам."""
        # Подготовка данных
        data1 = {
            'content': 'First test memory',
            'type': 'test'
        }
        data2 = {
            'content': 'Second test memory',
            'type': 'test'
        }

        # Вставка данных
        self.memory.insert(data1)
        self.memory.insert(data2)

        # Поиск по паттернам
        results = self.memory.search({'content': 'test memory'}, include_patterns=True)
        self.assertEqual(len(results), 2)

    def test_search_with_importance_filter(self):
        """Тест поиска с фильтром по важности."""
        # Подготовка данных
        data1 = {
            'content': 'Short content',
            'type': 'test'
        }
        data2 = {
            'content': 'Long content ' * 100,  # Длинный контент для большей важности
            'type': 'test'
        }

        # Вставка данных
        self.memory.insert(data1)
        self.memory.insert(data2)

        # Поиск с фильтром по важности
        results = self.memory.search({'type': 'test'}, min_importance=0.8)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], data2['content'])

    def test_add_insight(self):
        """Тест добавления инсайта."""
        # Добавляем инсайт
        insight_id = self.memory.add_insight(
            InsightType.EFFICIENCY,
            "Оптимизация производительности",
            {"metric": "response_time", "value": 0.5}
        )

        # Проверяем, что инсайт добавлен
        self.assertIn(insight_id, self.memory.insights)

        # Проверяем содержимое инсайта
        insight = self.memory.insights[insight_id]
        self.assertEqual(insight['type'], InsightType.EFFICIENCY.value)
        self.assertEqual(insight['content'], "Оптимизация производительности")
        self.assertEqual(insight['metadata']['metric'], "response_time")

    def test_get_insights(self):
        """Тест получения инсайтов."""
        # Добавляем инсайты разных типов
        self.memory.add_insight(InsightType.EFFICIENCY, "Эффективность 1")
        self.memory.add_insight(InsightType.PATTERN, "Паттерн 1")
        self.memory.add_insight(InsightType.EFFICIENCY, "Эффективность 2")

        # Получаем все инсайты
        all_insights = self.memory.get_insights()
        self.assertEqual(len(all_insights), 3)

        # Получаем инсайты определенного типа
        efficiency_insights = self.memory.get_insights(InsightType.EFFICIENCY)
        self.assertEqual(len(efficiency_insights), 2)

    def test_analyze_historical_data(self):
        """Тест анализа исторических данных."""
        # Добавляем тестовые данные
        for i in range(5):
            self.memory.add_insight(
                InsightType.EFFICIENCY,
                f"Тест {i}",
                {"value": i}
            )

        # Анализируем данные
        analysis = self.memory.analyze_historical_data('insights')

        # Проверяем результаты
        self.assertEqual(analysis['total_count'], 5)
        self.assertEqual(analysis['category'], 'insights')
        self.assertIn('type_distribution', analysis)
        self.assertIn('trends', analysis)

        # Проверяем анализ за период
        analysis_period = self.memory.analyze_historical_data(
            'insights',
            timedelta(hours=1)
        )
        self.assertLessEqual(analysis_period['total_count'], 5)

    def test_get_historical_summary(self):
        """Тест получения исторической сводки."""
        # Добавляем данные в разные категории
        self.memory.add_insight(InsightType.EFFICIENCY, "Тест 1")
        self.memory.add_insight(InsightType.PATTERN, "Тест 2")

        # Получаем сводку
        summary = self.memory.get_historical_summary()

        # Проверяем результаты
        self.assertIn('insights', summary)
        self.assertEqual(summary['insights']['total_count'], 2)
        self.assertIn('last_update', summary['insights'])
        self.assertIn('trend', summary['insights'])

    def test_trend_analysis(self):
        """Тест анализа трендов."""
        # Добавляем данные с разными интервалами
        now = datetime.utcnow()

        # Добавляем данные с интервалом в 30 минут
        for i in range(3):
            self.memory.add_insight(
                InsightType.EFFICIENCY,
                f"Частый тест {i}",
                {"timestamp": (now - timedelta(minutes=30*i)).isoformat()}
            )

        # Добавляем данные с интервалом в 2 дня
        for i in range(2):
            self.memory.add_insight(
                InsightType.PATTERN,
                f"Редкий тест {i}",
                {"timestamp": (now - timedelta(days=2*i)).isoformat()}
            )

        # Проверяем тренды
        summary = self.memory.get_historical_summary()
        self.assertEqual(summary['insights']['trend'], "increasing")

    def test_insight_metadata(self):
        """Тест работы с метаданными инсайтов."""
        # Добавляем инсайт с метаданными
        metadata = {
            "source": "test",
            "priority": "high",
            "tags": ["performance", "optimization"]
        }

        insight_id = self.memory.add_insight(
            InsightType.OPTIMIZATION,
            "Тест метаданных",
            metadata
        )

        # Проверяем сохранение метаданных
        insight = self.memory.insights[insight_id]
        self.assertEqual(insight['metadata'], metadata)

        # Проверяем поиск по метаданным
        found_insights = [
            i for i in self.memory.get_insights()
            if i['metadata'].get('source') == 'test'
        ]
        self.assertEqual(len(found_insights), 1)

if __name__ == '__main__':
    unittest.main()
