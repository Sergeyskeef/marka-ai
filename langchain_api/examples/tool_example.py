"""
Пример использования декоратора @register_tool
"""
import sys
sys.path.insert(0, '/workspace')

from core.tools_registry import register_tool, get_tools_registry


@register_tool(
    name="calculate_sum",
    description="Вычисляет сумму двух чисел",
    tags=["math", "calculation"],
    priority=0.8
)
def calculate_sum(a: float, b: float) -> float:
    """Складывает два числа и возвращает результат"""
    return a + b


@register_tool(
    name="get_weather", 
    description="Получает текущую погоду для указанного города",
    tags=["weather", "api"],
    priority=0.9
)
def get_weather(city: str, units: str = "metric") -> dict:
    """
    Получает информацию о погоде.
    
    Args:
        city: Название города
        units: Единицы измерения (metric/imperial)
    
    Returns:
        Словарь с данными о погоде
    """
    # Заглушка для примера
    return {
        "city": city,
        "temperature": 22.5,
        "units": units,
        "description": "Солнечно"
    }


def main():
    # Получаем реестр
    registry = get_tools_registry()
    
    # Сканируем проект
    print("🔍 Сканирую проект...")
    registry.scan_project()
    
    # Выводим найденные инструменты
    print(f"\n📦 Найдено инструментов: {len(registry.tools)}")
    
    # Экспортируем в формате OpenAI
    openai_functions = registry.export_openai_functions()
    
    print("\n🤖 Инструменты в формате OpenAI Function Calling:")
    import json
    print(json.dumps(openai_functions[:2], indent=2, ensure_ascii=False))
    
    # Проверяем Markdown экранирование
    print("\n📝 Тест Markdown экранирования:")
    from core.tools_registry import escape_markdown
    
    test_text = "Это *жирный* текст с _курсивом_ и [ссылкой](url)"
    escaped = escape_markdown(test_text)
    print(f"Исходный: {test_text}")
    print(f"Экранированный: {escaped}")


if __name__ == "__main__":
    main()