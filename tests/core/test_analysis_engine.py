"""
Тесты для AnalysisEngine с интеграцией существующих компонентов.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
import tempfile
import os
from pathlib import Path

from core.analysis_engine import AnalysisEngine, AnalysisResult


class TestAnalysisEngineIntegration(unittest.TestCase):
    """Тесты интеграции AnalysisEngine с существующими компонентами"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        self.temp_dir = tempfile.mkdtemp()
        
        # Мокаем импорты перед созданием движка
        with patch('core.analysis_engine.CODE_ANALYSIS_AVAILABLE', False):
            self.engine = AnalysisEngine(project_path=self.temp_dir)
        
        # Создаем тестовые данные
        self.test_data = [
            {'timestamp': '2025-01-01T10:00:00', 'value': 10.5, 'category': 'A'},
            {'timestamp': '2025-01-02T10:00:00', 'value': 12.3, 'category': 'B'},
            {'timestamp': '2025-01-03T10:00:00', 'value': 11.8, 'category': 'A'},
            {'timestamp': '2025-01-04T10:00:00', 'value': 13.1, 'category': 'B'},
            {'timestamp': '2025-01-05T10:00:00', 'value': 12.9, 'category': 'A'}
        ]
        
        self.test_text = """
        Это тестовый текст для анализа. Он содержит несколько предложений.
        Мы будем анализировать его паттерны и структуру.
        Текст имеет позитивную тональность и хорошую читаемость.
        """
    
    def tearDown(self):
        """Очистка после тестов"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_analyze_text_patterns(self):
        """Тест анализа текстовых паттернов"""
        result = self.engine.analyze_text_patterns(self.test_text)
        
        self.assertIn('basic_metrics', result)
        self.assertIn('emotional_markers', result)
        self.assertIn('keywords', result)
        self.assertIn('complexity', result)
        self.assertIn('sentiment', result)
        
        # Проверяем базовые метрики
        metrics = result['basic_metrics']
        self.assertGreater(metrics['word_count'], 0)
        self.assertGreater(metrics['char_count'], 0)
        self.assertGreater(metrics['sentence_count'], 0)
    
    def test_analyze_time_series(self):
        """Тест анализа временных рядов"""
        result = self.engine.analyze_time_series(
            self.test_data, 
            'timestamp', 
            'value'
        )
        
        self.assertIn('basic_statistics', result)
        self.assertIn('trend_analysis', result)
        self.assertIn('data_points', result)
        self.assertIn('time_range', result)
        
        # Проверяем статистики
        stats = result['basic_statistics']
        self.assertEqual(stats['count'], 5)
        self.assertGreater(stats['mean'], 0)
        self.assertGreater(stats['max'], stats['min'])
    
    def test_analyze_correlations(self):
        """Тест корреляционного анализа"""
        # Создаем данные с корреляцией
        correlated_data = [
            {'x': 1, 'y': 2, 'z': 5},
            {'x': 2, 'y': 4, 'z': 3},
            {'x': 3, 'y': 6, 'z': 1},
            {'x': 4, 'y': 8, 'z': 2},
            {'x': 5, 'y': 10, 'z': 4}
        ]
        
        result = self.engine.analyze_correlations(correlated_data, ['x', 'y', 'z'])
        
        self.assertIn('correlations', result)
        self.assertIn('significant_correlations', result)
        self.assertIn('fields_analyzed', result)
        self.assertIn('insights', result)
        
        # Проверяем, что корреляция x-y должна быть высокой
        correlations = result['correlations']
        self.assertIn('x_vs_y', correlations)
    
    def test_cluster_analysis(self):
        """Тест кластерного анализа"""
        # Создаем данные для кластеризации
        cluster_data = [
            {'feature1': 1, 'feature2': 1},
            {'feature1': 2, 'feature2': 2},
            {'feature1': 10, 'feature2': 10},
            {'feature1': 11, 'feature2': 11},
            {'feature1': 20, 'feature2': 20},
            {'feature1': 21, 'feature2': 21}
        ]
        
        result = self.engine.cluster_analysis(
            cluster_data, 
            ['feature1', 'feature2'], 
            n_clusters=3
        )
        
        self.assertIn('clusters', result)
        self.assertIn('cluster_analysis', result)
        self.assertIn('features_used', result)
        self.assertIn('insights', result)
        
        # Проверяем количество кластеров
        clusters = result['clusters']
        self.assertEqual(len(clusters), 3)
    
    def test_analyze_codebase_integration(self):
        """Тест интеграции с CodeAnalyzer"""
        # Создаем движок без интеграции
        with patch('core.analysis_engine.CODE_ANALYSIS_AVAILABLE', False):
            engine = AnalysisEngine(project_path=self.temp_dir)
        
        # Тестируем без реальной интеграции
        result = engine.analyze_codebase()
        
        # Должен вернуть ошибку, так как CodeAnalyzer недоступен
        self.assertIn('error', result)
    
    def test_analyze_sandbox_experiments_integration(self):
        """Тест интеграции с SandboxSelfAnalysis"""
        # Создаем движок без интеграции
        with patch('core.analysis_engine.CODE_ANALYSIS_AVAILABLE', False):
            engine = AnalysisEngine()
        
        # Тестируем без реальной интеграции
        result = engine.analyze_sandbox_experiments()
        
        # Должен вернуть ошибку, так как SandboxSelfAnalysis недоступен
        self.assertIn('error', result)
    
    def test_analyze_task_performance_integration(self):
        """Тест интеграции с MarkSelfAwareness"""
        # Создаем движок без интеграции
        with patch('core.analysis_engine.CODE_ANALYSIS_AVAILABLE', False):
            engine = AnalysisEngine()
        
        # Создаем тестовые результаты задач
        from datetime import datetime
        task_results = []
        for i in range(3):
            task_result = Mock()
            task_result.task_id = f"task_{i}"
            task_result.start_time = datetime.now() - timedelta(hours=i)
            task_result.end_time = datetime.now()
            task_result.success_rate = 0.8 + i * 0.1
            task_result.performance_metrics = {'cpu_usage': 50 + i * 10}
            task_result.error_messages = []
            task_result.insights = [f"Insight {i}"]
            task_results.append(task_result)
        
        # Тестируем без реальной интеграции
        result = engine.analyze_task_performance(task_results)
        
        # Должен вернуть ошибку, так как MarkSelfAwareness недоступен
        self.assertIn('error', result)
    
    def test_comprehensive_analysis(self):
        """Тест комплексного анализа"""
        # Мокаем атрибуты движка и методы
        with patch.object(self.engine, 'code_analyzer', Mock()), \
             patch.object(self.engine, 'sandbox_analyzer', Mock()), \
             patch.object(self.engine, 'analyze_codebase') as mock_code, \
             patch.object(self.engine, 'analyze_sandbox_experiments') as mock_sandbox:
            
            mock_code.return_value = {'code_analysis': 'test'}
            mock_sandbox.return_value = {'sandbox_analysis': 'test'}
            
            result = self.engine.comprehensive_analysis(['code', 'sandbox'])
            
            self.assertIn('codebase', result)
            self.assertIn('sandbox', result)
            self.assertIn('insights', result)
            self.assertIn('recommendations', result)
            
            mock_code.assert_called_once()
            mock_sandbox.assert_called_once()
    
    def test_comprehensive_analysis_without_integrations(self):
        """Тест комплексного анализа без доступных интеграций"""
        # Тестируем без моков - должны быть пустые результаты
        result = self.engine.comprehensive_analysis(['code', 'sandbox'])
        
        # Проверяем, что возвращается структура с пустыми списками
        self.assertIn('insights', result)
        self.assertIn('recommendations', result)
        self.assertIsInstance(result['insights'], list)
        self.assertIsInstance(result['recommendations'], list)
    
    def test_enhance_code_analysis(self):
        """Тест улучшения анализа кода"""
        code_analysis = {
            'complexity_metrics': {
                'avg_methods_per_class': 12.0,
                'test_files': 2
            },
            'dependencies': {
                'max_dependencies': 15
            },
            'total_files': 10
        }
        
        enhanced = self.engine._enhance_code_analysis(code_analysis)
        
        self.assertIn('complexity_assessment', enhanced)
        self.assertIn('dependency_health', enhanced)
        
        complexity = enhanced['complexity_assessment']
        self.assertEqual(complexity['overall_complexity'], 'high')
        self.assertEqual(complexity['test_coverage_ratio'], 0.2)
    
    def test_enhance_experiment_analysis(self):
        """Тест улучшения анализа экспериментов"""
        experiment_analysis = {
            'success_rate': 0.95,
            'improvements': ['Критическая ошибка', 'Оптимизировать код']
        }
        
        enhanced = self.engine._enhance_experiment_analysis(experiment_analysis)
        
        self.assertIn('success_assessment', enhanced)
        self.assertIn('improvement_priority', enhanced)
        
        success = enhanced['success_assessment']
        self.assertEqual(success['level'], 'excellent')
        
        priority = enhanced['improvement_priority']
        self.assertIn('Критическая ошибка', priority['high_priority'])
        self.assertIn('Оптимизировать код', priority['medium_priority'])
    
    def test_generate_code_recommendations(self):
        """Тест генерации рекомендаций по коду"""
        code_analysis = {
            'complexity_metrics': {
                'avg_methods_per_class': 15.0,
                'avg_args_per_function': 6.0,
                'test_files': 2
            },
            'total_files': 10
        }
        
        recommendations = self.engine._generate_code_recommendations(code_analysis)
        
        self.assertIsInstance(recommendations, list)
        self.assertGreater(len(recommendations), 0)
        
        # Проверяем, что рекомендации содержат ожидаемые пункты
        recommendation_text = ' '.join(recommendations).lower()
        self.assertIn('метод', recommendation_text)
        self.assertIn('функц', recommendation_text)
        self.assertIn('тест', recommendation_text)
    
    def test_calculate_maintainability_score(self):
        """Тест расчета оценки поддерживаемости"""
        # Тест с хорошими метриками
        good_metrics = {
            'avg_methods_per_class': 5.0,
            'avg_args_per_function': 2.0
        }
        good_score = self.engine._calculate_maintainability_score(good_metrics)
        self.assertGreater(good_score, 0.8)
        
        # Тест с плохими метриками
        bad_metrics = {
            'avg_methods_per_class': 20.0,
            'avg_args_per_function': 8.0
        }
        bad_score = self.engine._calculate_maintainability_score(bad_metrics)
        self.assertLess(bad_score, 0.6)
    
    def test_calculate_modularity_score(self):
        """Тест расчета оценки модульности"""
        # Тест с хорошей модульностью
        good_deps = {'max_dependencies': 3}
        good_score = self.engine._calculate_modularity_score(good_deps)
        self.assertEqual(good_score, 1.0)
        
        # Тест с плохой модульностью
        bad_deps = {'max_dependencies': 25}
        bad_score = self.engine._calculate_modularity_score(bad_deps)
        self.assertEqual(bad_score, 0.3)
    
    def test_error_handling(self):
        """Тест обработки ошибок"""
        # Тест с пустыми данными
        result = self.engine.analyze_text_patterns("")
        self.assertIn('error', result)
        
        result = self.engine.analyze_time_series([], 'timestamp', 'value')
        self.assertIn('error', result)
        
        result = self.engine.analyze_correlations([], ['field1', 'field2'])
        self.assertIn('error', result)
    
    def test_cache_functionality(self):
        """Тест функциональности кэширования"""
        # Первый вызов
        result1 = self.engine.analyze_text_patterns(self.test_text)
        
        # Второй вызов (должен использовать кэш)
        result2 = self.engine.analyze_text_patterns(self.test_text)
        
        # Результаты должны быть одинаковыми
        self.assertEqual(result1, result2)
    
    def test_analysis_result_dataclass(self):
        """Тест dataclass AnalysisResult"""
        data = {'test': 'data'}
        insights = ['Insight 1', 'Insight 2']
        recommendations = ['Recommendation 1']
        
        result = AnalysisResult(
            analysis_type='test',
            timestamp=datetime.now(),
            data=data,
            confidence=0.85,
            insights=insights,
            recommendations=recommendations
        )
        
        self.assertEqual(result.analysis_type, 'test')
        self.assertEqual(result.data, data)
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.insights, insights)
        self.assertEqual(result.recommendations, recommendations)


if __name__ == '__main__':
    unittest.main() 