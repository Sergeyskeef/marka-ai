
import pytest

from core.reflection.reflection_analyzer import ReflectionAnalyzer


@pytest.fixture
def reflection_analyzer():
    return ReflectionAnalyzer()

@pytest.fixture
def sample_actions():
    return [
        {
            'type': 'code_analysis',
            'target': 'test_file.py',
            'result': 'success',
            'duration': 1.5
        },
        {
            'type': 'code_analysis',
            'target': 'another_file.py',
            'result': 'success',
            'duration': 2.0
        },
        {
            'type': 'test_execution',
            'target': 'test_file.py',
            'result': 'failure',
            'duration': 3.0
        }
    ]

def test_add_action(reflection_analyzer):
    action = {
        'type': 'test_action',
        'target': 'test_target',
        'result': 'success'
    }

    reflection_analyzer.add_action(action)
    assert len(reflection_analyzer.action_history) == 1
    assert 'timestamp' in reflection_analyzer.action_history[0]
    assert reflection_analyzer.action_history[0]['type'] == 'test_action'

def test_analyze_actions_empty_history(reflection_analyzer):
    insights = reflection_analyzer.analyze_actions()
    assert len(insights) == 0

def test_analyze_actions_single_action(reflection_analyzer, sample_actions):
    reflection_analyzer.add_action(sample_actions[0])
    insights = reflection_analyzer.analyze_actions()
    assert len(insights) == 0

def test_analyze_actions_multiple_actions(reflection_analyzer, sample_actions):
    for action in sample_actions:
        reflection_analyzer.add_action(action)

    insights = reflection_analyzer.analyze_actions()
    assert len(insights) > 0

    # Проверяем наличие инсайтов для каждого типа действия
    action_types = {action['type'] for action in sample_actions}
    insight_types = {insight['action_type'] for insight in insights}
    assert insight_types.issubset(action_types)

def test_get_insights(reflection_analyzer, sample_actions):
    for action in sample_actions:
        reflection_analyzer.add_action(action)

    reflection_analyzer.analyze_actions()
    insights = reflection_analyzer.get_insights()

    assert len(insights) > 0
    for insight in insights:
        assert 'type' in insight
        assert 'action_type' in insight
        assert 'insight' in insight
        assert 'timestamp' in insight

def test_analyze_sequence(reflection_analyzer, sample_actions):
    # Добавляем только действия типа code_analysis
    code_analysis_actions = [action for action in sample_actions if action['type'] == 'code_analysis']
    for action in code_analysis_actions:
        reflection_analyzer.add_action(action)

    insights = reflection_analyzer.analyze_actions()
    sequence_insights = [insight for insight in insights if insight['type'] == 'sequence_analysis']

    assert len(sequence_insights) > 0
    assert all(insight['action_type'] == 'code_analysis' for insight in sequence_insights)

def test_analyze_efficiency(reflection_analyzer, sample_actions):
    # Добавляем только действия типа code_analysis
    code_analysis_actions = [action for action in sample_actions if action['type'] == 'code_analysis']
    for action in code_analysis_actions:
        reflection_analyzer.add_action(action)

    insights = reflection_analyzer.analyze_actions()
    efficiency_insights = [insight for insight in insights if insight['type'] == 'efficiency_analysis']

    assert len(efficiency_insights) > 0
    assert all(insight['action_type'] == 'code_analysis' for insight in efficiency_insights)
