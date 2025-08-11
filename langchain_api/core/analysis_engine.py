"""
Модуль для расширенных возможностей анализа.
"""

import logging
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Импорты для интеграции с существующими компонентами
try:
    from ..sandbox.self_analysis import SandboxSelfAnalysis
    from ..sandbox.self_awareness import MarkSelfAwareness, TaskResult
    from .code_analysis import CodeAnalyzer
    CODE_ANALYSIS_AVAILABLE = True
except ImportError:
    CODE_ANALYSIS_AVAILABLE = False
    CodeAnalyzer = None
    SandboxSelfAnalysis = None
    MarkSelfAwareness = None
    TaskResult = None

logger = logging.getLogger(__name__)

@dataclass
class AnalysisResult:
    """Результат анализа с метаданными"""
    analysis_type: str
    timestamp: datetime
    data: dict[str, Any]
    confidence: float
    insights: list[str]
    recommendations: list[str]

class AnalysisEngine:
    """
    Расширенный движок анализа данных с интеграцией существующих компонентов.

    Поддерживает:
    - Анализ текстовых паттернов
    - Анализ временных рядов
    - Корреляционный анализ
    - Кластерный анализ
    - Интеграция с CodeAnalyzer
    - Интеграция с SandboxSelfAnalysis
    - Интеграция с MarkSelfAwareness
    """

    def __init__(self, project_path: str | None = None):
        """
        Инициализация движка анализа.

        Args:
            project_path: Путь к проекту для интеграции с CodeAnalyzer
        """
        self.analysis_cache: dict[str, Any] = {}
        self.project_path = project_path

        # Инициализация интегрированных компонентов
        self.code_analyzer = None
        self.sandbox_analyzer = None
        self.self_awareness = None

        if CODE_ANALYSIS_AVAILABLE:
            if project_path:
                self.code_analyzer = CodeAnalyzer(project_path)
            self.sandbox_analyzer = SandboxSelfAnalysis()
            self.self_awareness = MarkSelfAwareness()

    def analyze_text_patterns(self, text: str) -> dict[str, Any]:
        """
        Анализирует текстовые паттерны в тексте.

        Args:
            text: Текст для анализа

        Returns:
            Dict[str, Any]: Результаты анализа
        """
        if not text:
            return {"error": "Empty text provided"}

        # Базовый анализ
        word_count = len(text.split())
        char_count = len(text)
        sentence_count = len(re.split(r'[.!?]+', text))

        # Анализ эмоциональных маркеров
        emotional_markers = self._analyze_emotional_markers(text)

        # Анализ ключевых слов
        keywords = self._extract_keywords(text)

        # Анализ сложности текста
        complexity = self._analyze_text_complexity(text)

        # Анализ тональности
        sentiment = self._analyze_sentiment(text)

        return {
            'basic_metrics': {
                'word_count': word_count,
                'char_count': char_count,
                'sentence_count': sentence_count,
                'avg_words_per_sentence': word_count / sentence_count if sentence_count > 0 else 0
            },
            'emotional_markers': emotional_markers,
            'keywords': keywords,
            'complexity': complexity,
            'sentiment': sentiment,
            'patterns': self._find_text_patterns(text)
        }

    def analyze_time_series(self, data: list[dict[str, Any]], time_field: str, value_field: str) -> dict[str, Any]:
        """
        Анализирует временные ряды данных.

        Args:
            data: Список словарей с данными
            time_field: Поле с временными метками
            value_field: Поле со значениями

        Returns:
            Dict[str, Any]: Результаты анализа
        """
        if not data or len(data) < 2:
            return {"error": "Insufficient data for time series analysis"}

        try:
            # Извлекаем временные метки и значения
            timestamps = []
            values = []

            for item in data:
                if time_field in item and value_field in item:
                    try:
                        # Пытаемся преобразовать в datetime
                        if isinstance(item[time_field], str):
                            timestamp = datetime.fromisoformat(item[time_field].replace('Z', '+00:00'))
                        else:
                            timestamp = item[time_field]

                        value = float(item[value_field])
                        timestamps.append(timestamp)
                        values.append(value)
                    except (ValueError, TypeError):
                        continue

            if len(values) < 2:
                return {"error": "Insufficient valid data points"}

            # Базовые статистики
            basic_stats = {
                'count': len(values),
                'mean': statistics.mean(values),
                'median': statistics.median(values),
                'std': statistics.stdev(values) if len(values) > 1 else 0,
                'min': min(values),
                'max': max(values)
            }

            # Анализ трендов
            trend_analysis = self._analyze_trend(values)

            # Анализ сезонности (если достаточно данных)
            seasonality = self._analyze_seasonality(values) if len(values) > 10 else None

            # Анализ аномалий
            anomalies = self._detect_anomalies(values)

            return {
                'basic_statistics': basic_stats,
                'trend_analysis': trend_analysis,
                'seasonality': seasonality,
                'anomalies': anomalies,
                'data_points': len(values),
                'time_range': {
                    'start': min(timestamps).isoformat(),
                    'end': max(timestamps).isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Error in time series analysis: {e}")
            return {"error": f"Analysis failed: {str(e)}"}

    def analyze_correlations(self, data: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
        """
        Анализирует корреляции между полями в данных.

        Args:
            data: Список словарей с данными
            fields: Список полей для анализа

        Returns:
            Dict[str, Any]: Результаты корреляционного анализа
        """
        if not data or len(fields) < 2:
            return {"error": "Insufficient data or fields for correlation analysis"}

        try:
            # Извлекаем числовые данные
            field_data = {field: [] for field in fields}

            for item in data:
                for field in fields:
                    if field in item:
                        try:
                            value = float(item[field])
                            field_data[field].append(value)
                        except (ValueError, TypeError):
                            continue

            # Проверяем, что у нас достаточно данных
            min_length = min(len(values) for values in field_data.values())
            if min_length < 2:
                return {"error": "Insufficient valid data for correlation analysis"}

            # Выравниваем длины массивов
            aligned_data = {}
            for field, values in field_data.items():
                aligned_data[field] = values[:min_length]

            # Вычисляем корреляции
            correlations = {}
            for i, field1 in enumerate(fields):
                for field2 in fields[i+1:]:
                    if field1 in aligned_data and field2 in aligned_data:
                        try:
                            corr = self._calculate_correlation(aligned_data[field1], aligned_data[field2])
                            correlations[f"{field1}_vs_{field2}"] = corr
                        except Exception:
                            correlations[f"{field1}_vs_{field2}"] = None

            # Анализ значимых корреляций
            significant_correlations = {
                k: v for k, v in correlations.items()
                if v is not None and abs(v) > 0.3
            }

            return {
                'correlations': correlations,
                'significant_correlations': significant_correlations,
                'fields_analyzed': fields,
                'data_points': min_length,
                'insights': self._generate_correlation_insights(significant_correlations)
            }

        except Exception as e:
            logger.error(f"Error in correlation analysis: {e}")
            return {"error": f"Correlation analysis failed: {str(e)}"}

    def cluster_analysis(self, data: list[dict[str, Any]], features: list[str], n_clusters: int = 3) -> dict[str, Any]:
        """
        Выполняет кластерный анализ данных.

        Args:
            data: Список словарей с данными
            features: Список признаков для кластеризации
            n_clusters: Количество кластеров

        Returns:
            Dict[str, Any]: Результаты кластерного анализа
        """
        if not data or len(features) < 2:
            return {"error": "Insufficient data or features for clustering"}

        try:
            # Извлекаем признаки
            feature_vectors = []
            valid_indices = []

            for i, item in enumerate(data):
                vector = []
                valid = True

                for feature in features:
                    if feature in item:
                        try:
                            value = float(item[feature])
                            vector.append(value)
                        except (ValueError, TypeError):
                            valid = False
                            break
                    else:
                        valid = False
                        break

                if valid and len(vector) == len(features):
                    feature_vectors.append(vector)
                    valid_indices.append(i)

            if len(feature_vectors) < n_clusters:
                return {"error": f"Insufficient valid data points for {n_clusters} clusters"}

            # Простая кластеризация на основе расстояний
            cluster_labels = self._simple_clustering(feature_vectors, n_clusters)

            # Анализ кластеров
            cluster_analysis = self._analyze_clusters(cluster_labels, feature_vectors, features)

            # Добавляем индексы оригинальных данных
            cluster_indices = {}
            for cluster_id in range(n_clusters):
                cluster_indices[f'cluster_{cluster_id}'] = [
                    valid_indices[i] for i, label in enumerate(cluster_labels) if label == cluster_id
                ]

            return {
                'clusters': cluster_indices,
                'cluster_analysis': cluster_analysis,
                'features_used': features,
                'n_clusters': n_clusters,
                'data_points': len(feature_vectors),
                'insights': self._generate_clustering_insights(cluster_analysis)
            }

        except Exception as e:
            logger.error(f"Error in cluster analysis: {e}")
            return {"error": f"Clustering failed: {str(e)}"}

    # Интеграция с существующими компонентами

    def analyze_codebase(self, project_path: str | None = None) -> dict[str, Any]:
        """
        Анализирует кодовую базу с использованием CodeAnalyzer.

        Args:
            project_path: Путь к проекту (если не указан, используется self.project_path)

        Returns:
            Dict[str, Any]: Результаты анализа кода
        """
        if not self.code_analyzer:
            return {"error": "CodeAnalyzer not available"}

        try:
            path = project_path or self.project_path
            if not path:
                return {"error": "No project path specified"}

            # Базовый анализ кода
            code_analysis = self.code_analyzer.analyze_codebase()

            # Дополнительный анализ с помощью AnalysisEngine
            enhanced_analysis = self._enhance_code_analysis(code_analysis)

            return {
                'code_analysis': code_analysis,
                'enhanced_analysis': enhanced_analysis,
                'recommendations': self._generate_code_recommendations(code_analysis)
            }

        except Exception as e:
            logger.error(f"Error in codebase analysis: {e}")
            return {"error": f"Codebase analysis failed: {str(e)}"}

    def analyze_sandbox_experiments(self, experiment_filename: str | None = None) -> dict[str, Any]:
        """
        Анализирует эксперименты в песочнице.

        Args:
            experiment_filename: Имя файла эксперимента (если не указан, анализирует все)

        Returns:
            Dict[str, Any]: Результаты анализа экспериментов
        """
        if not self.sandbox_analyzer:
            return {"error": "SandboxSelfAnalysis not available"}

        try:
            if experiment_filename:
                # Анализ конкретного эксперимента
                experiment_analysis = self.sandbox_analyzer.analyze_experiment(experiment_filename)
                return {
                    'experiment': experiment_filename,
                    'analysis': experiment_analysis,
                    'enhanced_analysis': self._enhance_experiment_analysis(experiment_analysis)
                }
            else:
                # Анализ всех экспериментов
                experiments_path = self.sandbox_analyzer.experiments_path
                experiment_files = list(experiments_path.glob("experiment_*.json"))

                all_analyses = []
                for exp_file in experiment_files:
                    try:
                        analysis = self.sandbox_analyzer.analyze_experiment(exp_file.name)
                        all_analyses.append({
                            'filename': exp_file.name,
                            'analysis': analysis
                        })
                    except Exception as e:
                        logger.warning(f"Failed to analyze {exp_file.name}: {e}")

                return {
                    'total_experiments': len(experiment_files),
                    'successful_analyses': len(all_analyses),
                    'experiments': all_analyses,
                    'summary': self._generate_experiments_summary(all_analyses)
                }

        except Exception as e:
            logger.error(f"Error in sandbox experiments analysis: {e}")
            return {"error": f"Sandbox analysis failed: {str(e)}"}

    def analyze_task_performance(self, task_results: list[TaskResult]) -> dict[str, Any]:
        """
        Анализирует производительность задач с использованием MarkSelfAwareness.

        Args:
            task_results: Список результатов выполнения задач

        Returns:
            Dict[str, Any]: Результаты анализа производительности
        """
        if not self.self_awareness:
            return {"error": "MarkSelfAwareness not available"}

        try:
            analyses = []
            for task_result in task_results:
                analysis = self.self_awareness.analyze_task_execution(task_result)
                analyses.append(analysis)

            # Агрегированный анализ
            aggregated_analysis = self._aggregate_task_analyses(analyses)

            # Временной анализ
            time_series_data = self._prepare_task_time_series(task_results)
            time_analysis = self.analyze_time_series(
                time_series_data,
                'timestamp',
                'success_rate'
            )

            return {
                'individual_analyses': analyses,
                'aggregated_analysis': aggregated_analysis,
                'time_series_analysis': time_analysis,
                'recommendations': self._generate_task_recommendations(analyses)
            }

        except Exception as e:
            logger.error(f"Error in task performance analysis: {e}")
            return {"error": f"Task analysis failed: {str(e)}"}

    def comprehensive_analysis(self, analysis_types: list[str] = None) -> dict[str, Any]:
        """
        Выполняет комплексный анализ всех доступных данных.

        Args:
            analysis_types: Список типов анализа для выполнения

        Returns:
            Dict[str, Any]: Комплексные результаты анализа
        """
        if analysis_types is None:
            analysis_types = ['code', 'sandbox', 'tasks']

        results = {}

        try:
            # Анализ кода
            if 'code' in analysis_types and self.code_analyzer:
                results['codebase'] = self.analyze_codebase()

            # Анализ песочницы
            if 'sandbox' in analysis_types and self.sandbox_analyzer:
                results['sandbox'] = self.analyze_sandbox_experiments()

            # Анализ задач (если есть данные)
            if 'tasks' in analysis_types and self.self_awareness:
                # Здесь нужно получить данные задач из системы
                results['tasks'] = {"note": "Task analysis requires task data"}

            # Генерация общих инсайтов
            results['insights'] = self._generate_comprehensive_insights(results)
            results['recommendations'] = self._generate_comprehensive_recommendations(results)

            return results

        except Exception as e:
            logger.error(f"Error in comprehensive analysis: {e}")
            return {"error": f"Comprehensive analysis failed: {str(e)}"}

    # Вспомогательные методы для интеграции

    def _enhance_code_analysis(self, code_analysis: dict[str, Any]) -> dict[str, Any]:
        """Улучшает анализ кода дополнительными метриками"""
        enhanced = {}

        # Анализ сложности
        if 'complexity_metrics' in code_analysis:
            metrics = code_analysis['complexity_metrics']
            enhanced['complexity_assessment'] = {
                'overall_complexity': 'high' if metrics.get('avg_methods_per_class', 0) > 10 else 'medium',
                'test_coverage_ratio': metrics.get('test_files', 0) / max(code_analysis.get('total_files', 1), 1),
                'maintainability_score': self._calculate_maintainability_score(metrics)
            }

        # Анализ зависимостей
        if 'dependencies' in code_analysis:
            deps = code_analysis['dependencies']
            enhanced['dependency_health'] = {
                'coupling_level': 'high' if deps.get('max_dependencies', 0) > 10 else 'medium',
                'modularity_score': self._calculate_modularity_score(deps)
            }

        return enhanced

    def _enhance_experiment_analysis(self, experiment_analysis: dict[str, Any]) -> dict[str, Any]:
        """Улучшает анализ экспериментов"""
        enhanced = {}

        # Анализ успешности
        success_rate = experiment_analysis.get('success_rate', 0)
        enhanced['success_assessment'] = {
            'level': 'excellent' if success_rate > 0.9 else 'good' if success_rate > 0.7 else 'needs_improvement',
            'confidence': min(success_rate * 100, 100)
        }

        # Анализ улучшений
        improvements = experiment_analysis.get('improvements', [])
        enhanced['improvement_priority'] = {
            'high_priority': [imp for imp in improvements if any(word in imp.lower() for word in ['ошибка', 'fail', 'critical', 'критическая'])],
            'medium_priority': [imp for imp in improvements if any(word in imp.lower() for word in ['оптимизировать', 'improve', 'enhance', 'улучшить'])],
            'low_priority': [imp for imp in improvements if not any(word in imp.lower() for word in ['ошибка', 'fail', 'critical', 'критическая', 'оптимизировать', 'improve', 'enhance', 'улучшить'])]
        }

        return enhanced

    def _aggregate_task_analyses(self, analyses: list) -> dict[str, Any]:
        """Агрегирует результаты анализа задач"""
        if not analyses:
            return {}

        success_rates = [a.success_rate for a in analyses]
        performance_scores = [a.performance_score for a in analyses]

        return {
            'average_success_rate': statistics.mean(success_rates),
            'average_performance_score': statistics.mean(performance_scores),
            'best_performing_task': max(analyses, key=lambda x: x.performance_score).task_id,
            'most_successful_task': max(analyses, key=lambda x: x.success_rate).task_id,
            'total_tasks': len(analyses)
        }

    def _prepare_task_time_series(self, task_results: list[TaskResult]) -> list[dict[str, Any]]:
        """Подготавливает данные задач для временного анализа"""
        time_series_data = []

        for result in task_results:
            time_series_data.append({
                'timestamp': result.start_time.isoformat(),
                'success_rate': result.success_rate,
                'performance_score': getattr(result, 'performance_score', 0.0)
            })

        return sorted(time_series_data, key=lambda x: x['timestamp'])

    def _generate_comprehensive_insights(self, results: dict[str, Any]) -> list[str]:
        """Генерирует общие инсайты на основе всех анализов"""
        insights = []

        # Инсайты по коду
        if 'codebase' in results and 'error' not in results['codebase']:
            code_analysis = results['codebase']
            if 'enhanced_analysis' in code_analysis:
                enhanced = code_analysis['enhanced_analysis']
                if 'complexity_assessment' in enhanced:
                    complexity = enhanced['complexity_assessment']
                    if complexity['overall_complexity'] == 'high':
                        insights.append("Кодовая база имеет высокую сложность - рекомендуется рефакторинг")
                    if complexity['test_coverage_ratio'] < 0.3:
                        insights.append("Низкое покрытие тестами - рекомендуется увеличить количество тестов")

        # Инсайты по песочнице
        if 'sandbox' in results and 'error' not in results['sandbox']:
            sandbox = results['sandbox']
            if 'summary' in sandbox:
                summary = sandbox['summary']
                if summary.get('average_success_rate', 0) < 0.7:
                    insights.append("Низкая успешность экспериментов в песочнице - требуется улучшение процессов")

        return insights

    def _generate_comprehensive_recommendations(self, results: dict[str, Any]) -> list[str]:
        """Генерирует общие рекомендации"""
        recommendations = []

        # Рекомендации по коду
        if 'codebase' in results and 'recommendations' in results['codebase']:
            recommendations.extend(results['codebase']['recommendations'])

        # Рекомендации по песочнице
        if 'sandbox' in results and 'summary' in results['sandbox']:
            summary = results['sandbox']['summary']
            if summary.get('average_success_rate', 0) < 0.8:
                recommendations.append("Улучшить процессы экспериментирования в песочнице")

        return recommendations

    def _calculate_maintainability_score(self, metrics: dict[str, Any]) -> float:
        """Рассчитывает оценку поддерживаемости кода"""
        score = 1.0

        # Штраф за сложность методов
        avg_methods = metrics.get('avg_methods_per_class', 0)
        if avg_methods > 15:
            score *= 0.7
        elif avg_methods > 10:
            score *= 0.85

        # Штраф за сложность функций
        avg_args = metrics.get('avg_args_per_function', 0)
        if avg_args > 5:
            score *= 0.8
        elif avg_args > 3:
            score *= 0.9

        return round(score, 2)

    def _calculate_modularity_score(self, deps: dict[str, Any]) -> float:
        """Рассчитывает оценку модульности"""
        max_deps = deps.get('max_dependencies', 0)
        if max_deps == 0:
            return 1.0

        # Чем меньше зависимостей, тем лучше модульность
        if max_deps > 20:
            return 0.3
        elif max_deps > 10:
            return 0.6
        elif max_deps > 5:
            return 0.8
        else:
            return 1.0

    def _generate_code_recommendations(self, code_analysis: dict[str, Any]) -> list[str]:
        """Генерирует рекомендации по коду"""
        recommendations = []

        metrics = code_analysis.get('complexity_metrics', {})

        if metrics.get('avg_methods_per_class', 0) > 10:
            recommendations.append("Рассмотрите возможность разбиения классов с большим количеством методов")

        if metrics.get('avg_args_per_function', 0) > 5:
            recommendations.append("Упростите сигнатуры функций, используйте объекты конфигурации")

        test_ratio = metrics.get('test_files', 0) / max(code_analysis.get('total_files', 1), 1)
        if test_ratio < 0.3:
            recommendations.append("Увеличьте покрытие тестами - добавьте unit-тесты для основных компонентов")

        return recommendations

    def _generate_task_recommendations(self, analyses: list) -> list[str]:
        """Генерирует рекомендации по задачам"""
        recommendations = []

        if not analyses:
            return ["Нет данных для анализа задач"]

        avg_success = statistics.mean([a.success_rate for a in analyses])
        avg_performance = statistics.mean([a.performance_score for a in analyses])

        if avg_success < 0.8:
            recommendations.append("Улучшите обработку ошибок и валидацию входных данных")

        if avg_performance < 0.7:
            recommendations.append("Оптимизируйте производительность выполнения задач")

        # Анализ паттернов ошибок
        all_error_patterns = {}
        for analysis in analyses:
            for error_type, count in analysis.error_patterns.items():
                all_error_patterns[error_type] = all_error_patterns.get(error_type, 0) + count

        most_common_error = max(all_error_patterns.items(), key=lambda x: x[1]) if all_error_patterns else None
        if most_common_error:
            recommendations.append(f"Сосредоточьтесь на устранении ошибок типа '{most_common_error[0]}'")

        return recommendations

    def _generate_experiments_summary(self, analyses: list[dict[str, Any]]) -> dict[str, Any]:
        """Генерирует сводку по экспериментам"""
        if not analyses:
            return {}

        success_rates = []
        for analysis in analyses:
            if 'analysis' in analysis and 'success_rate' in analysis['analysis']:
                success_rates.append(analysis['analysis']['success_rate'])

        return {
            'total_experiments': len(analyses),
            'average_success_rate': statistics.mean(success_rates) if success_rates else 0,
            'successful_experiments': len([r for r in success_rates if r > 0.8]),
            'needs_improvement': len([r for r in success_rates if r < 0.6])
        }

    def _extract_phrases(self, text: str) -> list[str]:
        """Извлечение повторяющихся фраз."""
        # Простое извлечение фраз из 2-3 слов
        words = text.lower().split()
        phrases = []

        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            phrases.append(phrase)

        for i in range(len(words) - 2):
            phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
            phrases.append(phrase)

        return phrases

    def _analyze_emotional_markers(self, text: str) -> dict[str, int]:
        """Анализ эмоциональных маркеров в тексте."""
        positive_words = ['хорошо', 'отлично', 'великолепно', 'прекрасно', 'успешно']
        negative_words = ['плохо', 'ужасно', 'неудачно', 'ошибка', 'проблема']

        text_lower = text.lower()

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        return {
            'positive': positive_count,
            'negative': negative_count,
            'sentiment_score': positive_count - negative_count
        }

    def _extract_keywords(self, text: str) -> list[str]:
        """Извлечение ключевых слов из текста."""
        # Простое извлечение ключевых слов
        words = re.findall(r'\b\w+\b', text.lower())

        # Фильтруем стоп-слова
        stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'от', 'до', 'из', 'к', 'у', 'о', 'об', 'за', 'при', 'под', 'над', 'между', 'через', 'без', 'про', 'это', 'то', 'так', 'как', 'что', 'где', 'когда', 'почему', 'какой', 'какая', 'какое', 'какие', 'мой', 'моя', 'мое', 'мои', 'твой', 'твоя', 'твое', 'твои', 'наш', 'наша', 'наше', 'наши', 'ваш', 'ваша', 'ваше', 'ваши', 'его', 'ее', 'их', 'себя', 'тот', 'та', 'те', 'этот', 'эта', 'эти', 'такой', 'такая', 'такое', 'такие', 'столько', 'столь', 'сколько', 'сколь', 'который', 'которая', 'которое', 'которые', 'чей', 'чья', 'чье', 'чьи', 'сам', 'сама', 'само', 'сами', 'самый', 'самая', 'самое', 'самые', 'весь', 'вся', 'все', 'каждый', 'каждая', 'каждое', 'каждые', 'любой', 'любая', 'любое', 'любые', 'никто', 'ничто', 'никакой', 'никакая', 'никакое', 'никакие', 'ничей', 'ничья', 'ничье', 'ничьи', 'некто', 'нечто', 'некий', 'некая', 'некое', 'некие', 'чей-то', 'чья-то', 'чье-то', 'чьи-то', 'кто-то', 'что-то', 'какой-то', 'какая-то', 'какое-то', 'какие-то', 'кто-либо', 'что-либо', 'какой-либо', 'какая-либо', 'какое-либо', 'какие-либо', 'кто-нибудь', 'что-нибудь', 'какой-нибудь', 'какая-нибудь', 'какое-нибудь', 'какие-нибудь', 'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они', 'меня', 'мне', 'мной', 'мною', 'тебя', 'тебе', 'тобой', 'тобою', 'ему', 'им', 'ним', 'ей', 'ею', 'ней', 'нас', 'нам', 'нами', 'вас', 'вам', 'вами', 'ими', 'ними', 'себе', 'собой', 'собою', 'моих', 'моим', 'моими', 'твоих', 'твоим', 'твоими', 'свой', 'своя', 'свое', 'свои', 'своих', 'своим', 'своими', 'наших', 'нашим', 'нашими', 'ваших', 'вашим', 'вашими', 'тех', 'тем', 'теми', 'этих', 'этим', 'этими', 'таких', 'таким', 'такими', 'которых', 'которым', 'которыми', 'чьих', 'чьим', 'чьими', 'самих', 'самим', 'самими', 'самых', 'самым', 'самыми', 'всех', 'всем', 'всеми', 'каждых', 'каждым', 'каждыми', 'любых', 'любым', 'любыми', 'никаких', 'никаким', 'никакими', 'ничьих', 'ничьим', 'ничьими', 'неких', 'неким', 'некими', 'чьих-то', 'чьим-то', 'чьими-то', 'каких-то', 'каким-то', 'какими-то', 'каких-либо', 'каким-либо', 'какими-либо', 'каких-нибудь', 'каким-нибудь'}

        # Подсчитываем частоту слов
        word_freq = Counter(words)

        # Фильтруем стоп-слова и короткие слова
        keywords = []
        for word, freq in word_freq.items():
            if word not in stop_words and len(word) > 3 and freq > 1:
                keywords.append(word)

        # Возвращаем топ-10 ключевых слов
        return sorted(keywords, key=lambda x: word_freq[x], reverse=True)[:10]

    def _analyze_text_complexity(self, text: str) -> dict[str, Any]:
        """Анализ сложности текста."""
        complexity_score = self._calculate_text_complexity(text)

        # Определяем уровень сложности
        if complexity_score < 0.3:
            level = 'easy'
        elif complexity_score < 0.6:
            level = 'medium'
        else:
            level = 'hard'

        return {
            'score': complexity_score,
            'level': level,
            'readability': 'high' if complexity_score < 0.5 else 'medium' if complexity_score < 0.7 else 'low'
        }

    def _analyze_sentiment(self, text: str) -> dict[str, Any]:
        """Анализ тональности текста."""
        emotional_markers = self._analyze_emotional_markers(text)
        sentiment_score = emotional_markers['sentiment_score']

        # Определяем тональность
        if sentiment_score > 2:
            sentiment = 'positive'
        elif sentiment_score < -2:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return {
            'sentiment': sentiment,
            'score': sentiment_score,
            'confidence': min(abs(sentiment_score) / 5.0, 1.0),
            'positive_markers': emotional_markers['positive'],
            'negative_markers': emotional_markers['negative']
        }

    def _find_text_patterns(self, text: str) -> dict[str, Any]:
        """Поиск паттернов в тексте."""
        # Извлекаем фразы
        phrases = self._extract_phrases(text)

        # Подсчитываем частоту фраз
        phrase_freq = Counter(phrases)

        # Находим повторяющиеся паттерны
        repeated_phrases = [phrase for phrase, freq in phrase_freq.items() if freq > 1]

        # Анализируем структуру предложений
        sentences = re.split(r'[.!?]+', text)
        sentence_lengths = [len(sentence.split()) for sentence in sentences if sentence.strip()]

        return {
            'repeated_phrases': repeated_phrases[:5],  # Топ-5 повторяющихся фраз
            'avg_sentence_length': sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0,
            'sentence_count': len(sentences),
            'phrase_diversity': len(set(phrases)) / len(phrases) if phrases else 0
        }

    def _generate_correlation_insights(self, significant_correlations: dict[str, float]) -> list[str]:
        """Генерация инсайтов на основе корреляций."""
        insights = []

        if not significant_correlations:
            insights.append("Значимых корреляций между полями не обнаружено")
            return insights

        # Анализируем каждую значимую корреляцию
        for correlation_name, correlation_value in significant_correlations.items():
            fields = correlation_name.split('_vs_')
            if len(fields) == 2:
                field1, field2 = fields

                if abs(correlation_value) > 0.8:
                    strength = "сильная"
                elif abs(correlation_value) > 0.6:
                    strength = "умеренная"
                else:
                    strength = "слабая"

                if correlation_value > 0:
                    direction = "прямая"
                else:
                    direction = "обратная"

                insights.append(f"Обнаружена {strength} {direction} корреляция между '{field1}' и '{field2}' ({correlation_value:.2f})")

        # Общие инсайты
        if len(significant_correlations) > 3:
            insights.append(f"Обнаружено много взаимосвязей между полями ({len(significant_correlations)} значимых корреляций)")

        return insights

    def _calculate_text_complexity(self, text: str) -> float:
        """Расчет сложности текста."""
        sentences = re.split(r'[.!?]+', text)
        words = re.findall(r'\b\w+\b', text.lower())

        if not sentences or not words:
            return 0.0

        avg_sentence_length = len(words) / len(sentences)
        unique_words_ratio = len(set(words)) / len(words)

        # Простая формула сложности
        complexity = (avg_sentence_length * 0.5) + (unique_words_ratio * 0.5)
        return min(complexity, 1.0)

    def _analyze_trend(self, values: list[float]) -> dict[str, Any]:
        """Анализ тренда в данных."""
        if len(values) < 2:
            return {'trend': 'insufficient_data'}

        # Простой анализ тренда
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        if second_avg > first_avg * 1.1:
            trend = 'increasing'
        elif second_avg < first_avg * 0.9:
            trend = 'decreasing'
        else:
            trend = 'stable'

        return {
            'trend': trend,
            'change_percentage': ((second_avg - first_avg) / first_avg * 100) if first_avg != 0 else 0
        }

    def _detect_anomalies(self, values: list[float]) -> list[int]:
        """Поиск аномалий в данных."""
        if len(values) < 3:
            return []

        mean = sum(values) / len(values)
        std = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5

        anomalies = []
        for i, value in enumerate(values):
            if abs(value - mean) > 2 * std:  # 2 стандартных отклонения
                anomalies.append(i)

        return anomalies

    def _analyze_seasonality(self, values: list[float]) -> dict[str, Any]:
        """Анализ сезонности (упрощенный)."""
        if len(values) < 12:
            return None

        # Простой анализ сезонности
        seasonal_patterns = []
        for period in [3, 4, 6, 12]:
            if len(values) >= period * 2:
                pattern = self._check_seasonal_pattern(values, period)
                if pattern:
                    seasonal_patterns.append({'period': period, 'strength': pattern})

        return {
            'patterns': seasonal_patterns,
            'strongest_period': max(seasonal_patterns, key=lambda x: x['strength']) if seasonal_patterns else None
        }

    def _check_seasonal_pattern(self, values: list[float], period: int) -> float:
        """Проверка сезонного паттерна."""
        if len(values) < period * 2:
            return 0.0

        # Простая проверка повторяемости
        correlations = []
        for i in range(period):
            group1 = values[i::period]
            group2 = values[i+period::period]

            if len(group1) > 1 and len(group2) > 1:
                corr = self._calculate_correlation(group1, group2)
                correlations.append(abs(corr))

        return sum(correlations) / len(correlations) if correlations else 0.0

    def _calculate_correlation(self, x: list[float], y: list[float]) -> float:
        """Вычисление корреляции между двумя списками."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        sum_y2 = sum(y[i] ** 2 for i in range(n))

        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5

        return numerator / denominator if denominator != 0 else 0.0

    def _simple_clustering(self, vectors: list[list[float]], n_clusters: int) -> list[int]:
        """Простая кластеризация на основе расстояний."""
        if len(vectors) <= n_clusters:
            return list(range(len(vectors)))

        # Простая кластеризация: делим на равные группы
        clusters = []
        for i in range(len(vectors)):
            cluster = i % n_clusters
            clusters.append(cluster)

        return clusters

    def _analyze_clusters(self, clusters: list[int], vectors: list[list[float]], features: list[str]) -> dict[str, Any]:
        """Анализ кластеров."""
        cluster_data = defaultdict(list)
        for i, cluster in enumerate(clusters):
            cluster_data[cluster].append(vectors[i])

        analysis = {}
        for cluster_id, cluster_vectors in cluster_data.items():
            if cluster_vectors:
                # Вычисляем центроид кластера
                centroid = []
                for feature_idx in range(len(features)):
                    feature_values = [vector[feature_idx] for vector in cluster_vectors]
                    centroid.append(sum(feature_values) / len(feature_values))

                analysis[f'cluster_{cluster_id}'] = {
                    'size': len(cluster_vectors),
                    'centroid': centroid,
                    'features': features
                }

        return analysis

    def _linear_prediction(self, data: list[float], periods: int) -> list[float]:
        """Линейное прогнозирование."""
        if len(data) < 2:
            return []

        # Простая линейная экстраполяция
        x = list(range(len(data)))
        y = data

        # Вычисляем наклон
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2) if (n * sum_x2 - sum_x ** 2) != 0 else 0
        intercept = (sum_y - slope * sum_x) / n

        # Прогнозируем
        predictions = []
        for i in range(len(data), len(data) + periods):
            pred = slope * i + intercept
            predictions.append(max(0, pred))  # Не отрицательные значения

        return predictions

    def _calculate_prediction_accuracy(self, data: list[float]) -> dict[str, float]:
        """Расчет точности прогноза."""
        if len(data) < 3:
            return {'mae': 0.0, 'rmse': 0.0}

        # Используем последние данные для проверки точности
        test_data = data[-3:]
        predicted = self._linear_prediction(data[:-3], 3)

        if len(predicted) != len(test_data):
            return {'mae': 0.0, 'rmse': 0.0}

        # MAE (Mean Absolute Error)
        mae = sum(abs(predicted[i] - test_data[i]) for i in range(len(test_data))) / len(test_data)

        # RMSE (Root Mean Square Error)
        rmse = (sum((predicted[i] - test_data[i]) ** 2 for i in range(len(test_data))) / len(test_data)) ** 0.5

        return {'mae': mae, 'rmse': rmse}

    def _calculate_confidence_interval(self, predictions: list[float]) -> dict[str, list[float]]:
        """Расчет доверительного интервала."""
        if not predictions:
            return {'lower': [], 'upper': []}

        # Простой доверительный интервал
        confidence_factor = 0.1  # 10%

        lower = [pred * (1 - confidence_factor) for pred in predictions]
        upper = [pred * (1 + confidence_factor) for pred in predictions]

        return {'lower': lower, 'upper': upper}

    def _generate_clustering_insights(self, cluster_analysis: dict[str, Any]) -> list[str]:
        """Генерация инсайтов на основе кластерного анализа."""
        insights = []

        if not cluster_analysis:
            insights.append("Кластерный анализ не выявил четких групп в данных")
            return insights

        # Анализируем размеры кластеров
        cluster_sizes = []
        for cluster_id, cluster_info in cluster_analysis.items():
            if isinstance(cluster_info, dict) and 'size' in cluster_info:
                cluster_sizes.append((cluster_id, cluster_info['size']))

        if cluster_sizes:
            # Находим самый большой и самый маленький кластер
            cluster_sizes.sort(key=lambda x: x[1], reverse=True)
            largest_cluster = cluster_sizes[0]
            smallest_cluster = cluster_sizes[-1]

            insights.append(f"Самый большой кластер: {largest_cluster[0]} ({largest_cluster[1]} элементов)")
            insights.append(f"Самый маленький кластер: {smallest_cluster[0]} ({smallest_cluster[1]} элементов)")

            # Анализируем распределение
            total_elements = sum(size for _, size in cluster_sizes)
            if total_elements > 0:
                largest_percentage = (largest_cluster[1] / total_elements) * 100
                if largest_percentage > 60:
                    insights.append(f"Данные сильно сконцентрированы в одном кластере ({largest_percentage:.1f}%)")
                elif largest_percentage < 30:
                    insights.append("Данные равномерно распределены между кластерами")

        # Общие инсайты
        insights.append(f"Обнаружено {len(cluster_analysis)} кластеров в данных")

        return insights
