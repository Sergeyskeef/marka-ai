from langchain_api.core.reflection.reflection_system import (
    InsightType,
    ReflectionSystem,
)


def test_add_action():
    system = ReflectionSystem()
    action = {
        'type': 'test_action',
        'duration': 100,
        'success': True
    }
    system.add_action(action)
    assert len(system.action_history) == 1
    assert system.metrics['test_action']['total_count'] == 1
    assert system.metrics['test_action']['success_count'] == 1
    assert system.metrics['test_action']['avg_duration'] == 100

def test_analyze_efficiency():
    system = ReflectionSystem()

    # Добавляем несколько действий с разной эффективностью
    actions = [
        {'type': 'test_action', 'duration': 100, 'success': True},
        {'type': 'test_action', 'duration': 150, 'success': False},
        {'type': 'test_action', 'duration': 200, 'success': False},
        {'type': 'test_action', 'duration': 1200, 'success': True}  # Длительное действие
    ]

    for action in actions:
        system.add_action(action)

    insights = system._analyze_efficiency()

    # Проверяем, что найдены инсайты о низкой эффективности и длительном выполнении
    efficiency_insights = [i for i in insights if i.type == InsightType.EFFICIENCY]
    optimization_insights = [i for i in insights if i.type == InsightType.OPTIMIZATION]

    assert len(efficiency_insights) > 0
    assert len(optimization_insights) > 0

    # Проверяем содержимое инсайтов
    efficiency_insight = efficiency_insights[0]
    assert efficiency_insight.title.startswith("Низкая эффективность действий")
    assert len(efficiency_insight.recommendations) > 0

def test_analyze_patterns():
    system = ReflectionSystem()

    # Создаем повторяющуюся последовательность действий
    actions = [
        {'type': 'test_action', 'duration': 100, 'success': True},
        {'type': 'test_action', 'duration': 150, 'success': True},
        {'type': 'test_action', 'duration': 100, 'success': True},
        {'type': 'test_action', 'duration': 150, 'success': True}
    ]

    for action in actions:
        system.add_action(action)

    insights = system._analyze_patterns()

    # Проверяем, что найден инсайт о паттернах
    pattern_insights = [i for i in insights if i.type == InsightType.PATTERN]
    assert len(pattern_insights) > 0

    # Проверяем содержимое инсайта
    pattern_insight = pattern_insights[0]
    assert pattern_insight.title.startswith("Обнаружены повторяющиеся последовательности")
    assert len(pattern_insight.recommendations) > 0

def test_generate_recommendations():
    system = ReflectionSystem()

    # Добавляем действия с низкой успешностью
    actions = [
        {'type': 'test_action', 'duration': 100, 'success': False},
        {'type': 'test_action', 'duration': 150, 'success': False},
        {'type': 'test_action', 'duration': 200, 'success': True}
    ]

    for action in actions:
        system.add_action(action)

    insights = system._generate_recommendations()

    # Проверяем, что найдены рекомендации
    recommendation_insights = [i for i in insights if i.type == InsightType.RECOMMENDATION]
    assert len(recommendation_insights) > 0

    # Проверяем содержимое рекомендаций
    recommendation_insight = recommendation_insights[0]
    assert recommendation_insight.title.startswith("Рекомендации по улучшению")
    assert len(recommendation_insight.recommendations) > 0

def test_full_analysis():
    system = ReflectionSystem()

    # Добавляем разнообразные действия
    actions = [
        {'type': 'test_action', 'duration': 100, 'success': True},
        {'type': 'test_action', 'duration': 150, 'success': False},
        {'type': 'test_action', 'duration': 100, 'success': True},
        {'type': 'test_action', 'duration': 150, 'success': False},
        {'type': 'test_action', 'duration': 1200, 'success': True}
    ]

    for action in actions:
        system.add_action(action)

    insights = system.analyze_actions()

    # Проверяем, что найдены инсайты разных типов
    insight_types = {i.type for i in insights}
    assert InsightType.EFFICIENCY in insight_types
    assert InsightType.PATTERN in insight_types
    assert InsightType.RECOMMENDATION in insight_types
    assert InsightType.OPTIMIZATION in insight_types

    # Проверяем, что все инсайты сохранены в системе
    assert len(system.get_insights()) == len(insights)
