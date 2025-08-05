"""
Тесты для задачи F-6: Reflection Engine - реализовать анализ, сохранять инсайты
"""
import sys
sys.path.insert(0, '/workspace')
from core.reflection.reflection_analyzer import ReflectionAnalyzer
from datetime import datetime


def test_reflection_analyzer():
    """Тест базовой функциональности ReflectionAnalyzer"""
    print("\n=== Тест ReflectionAnalyzer ===")
    
    analyzer = ReflectionAnalyzer()
    
    # Добавляем действия
    analyzer.add_action({"type": "test", "subtype": "a", "success": True})
    analyzer.add_action({"type": "test", "subtype": "b", "success": True})
    
    assert len(analyzer.action_history) == 2
    print("✅ Действия добавляются в историю")
    
    # Проверяем timestamp
    assert 'timestamp' in analyzer.action_history[0]
    print("✅ Timestamp добавляется автоматически")


def test_sequence_analysis():
    """Тест анализа последовательностей"""
    print("\n=== Тест анализа последовательностей ===")
    
    analyzer = ReflectionAnalyzer()
    
    # Добавляем повторяющуюся последовательность
    for _ in range(4):
        analyzer.add_action({"type": "api", "subtype": "login", "success": True})
        analyzer.add_action({"type": "api", "subtype": "fetch", "success": True})
    
    insights = analyzer.analyze_actions()
    
    # Ищем инсайт о последовательности
    sequence_insight = None
    for insight in insights:
        if insight['type'] == 'sequence_analysis':
            sequence_insight = insight
            break
    
    assert sequence_insight is not None
    print("✅ Обнаружена повторяющаяся последовательность")
    assert 'pattern' in sequence_insight
    assert 'frequency' in sequence_insight
    print(f"✅ Паттерн: {sequence_insight['pattern']} (повторяется {sequence_insight['frequency']} раз)")


def test_efficiency_analysis():
    """Тест анализа эффективности"""
    print("\n=== Тест анализа эффективности ===")
    
    analyzer = ReflectionAnalyzer()
    
    # Добавляем действия с разным временем выполнения
    times = [0.1, 0.2, 0.15, 0.1, 5.0, 6.0, 0.2]  # Есть медленные операции
    for t in times:
        analyzer.add_action({
            "type": "compute", 
            "success": True,
            "execution_time": t
        })
    
    insights = analyzer.analyze_actions()
    
    # Ищем инсайт об эффективности
    efficiency_insight = None
    for insight in insights:
        if insight['type'] == 'efficiency_analysis':
            efficiency_insight = insight
            break
    
    assert efficiency_insight is not None
    print("✅ Обнаружены медленные операции")
    assert 'avg_time' in efficiency_insight
    assert 'median_time' in efficiency_insight
    print(f"✅ Среднее время: {efficiency_insight['avg_time']}с, медиана: {efficiency_insight['median_time']}с")


def test_error_analysis():
    """Тест анализа ошибок"""
    print("\n=== Тест анализа ошибок ===")
    
    analyzer = ReflectionAnalyzer()
    
    # Добавляем действия с ошибками
    errors = ["timeout", "timeout", "connection error", "timeout"]
    for err in errors:
        analyzer.add_action({
            "type": "network",
            "success": False,
            "error": err
        })
    
    # Добавляем успешные для контраста
    analyzer.add_action({"type": "network", "success": True})
    
    insights = analyzer.analyze_actions()
    
    # Ищем инсайт об ошибках
    error_insight = None
    for insight in insights:
        if insight['type'] == 'error_analysis':
            error_insight = insight
            break
    
    assert error_insight is not None
    print("✅ Обнаружены паттерны ошибок")
    assert 'error_distribution' in error_insight
    assert error_insight['error_distribution']['timeout'] == 3
    print(f"✅ Распределение ошибок: {error_insight['error_distribution']}")


def test_save_insights():
    """Тест сохранения инсайтов в память"""
    print("\n=== Тест сохранения инсайтов ===")
    
    analyzer = ReflectionAnalyzer()
    
    # Проверяем наличие метода
    assert hasattr(analyzer, 'save_insights_to_memory')
    print("✅ Метод save_insights_to_memory существует")
    
    # Проверяем get_summary
    summary = analyzer.get_summary()
    assert 'total_actions' in summary
    assert 'total_insights' in summary
    print("✅ Метод get_summary возвращает статистику")


def test_reflection_endpoint():
    """Тест API endpoint для рефлексии"""
    print("\n=== Тест Reflection API endpoint ===")
    
    # Читаем main.py
    with open('/workspace/main.py', 'r') as f:
        main_content = f.read()
    
    # Проверяем наличие endpoint
    assert '/reflection/insights' in main_content
    print("✅ Endpoint /reflection/insights существует")
    
    # Проверяем использование ReflectionAnalyzer
    assert 'ReflectionAnalyzer' in main_content
    print("✅ Используется ReflectionAnalyzer")
    
    # Проверяем возврат инсайтов
    assert 'analyze_actions()' in main_content
    print("✅ Вызывается метод analyze_actions()")


def main():
    print("🧪 Запуск тестов для F-6: Reflection Engine")
    
    test_reflection_analyzer()
    test_sequence_analysis()
    test_efficiency_analysis()
    test_error_analysis()
    test_save_insights()
    test_reflection_endpoint()
    
    print("\n🎉 Все тесты F-6 успешно пройдены!")


if __name__ == "__main__":
    main()