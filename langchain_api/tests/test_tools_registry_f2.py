"""
Тесты для задачи F-2: Tool Registry
- Декоратор
- Markdown-escape  
- Экспорт Function Calling JSON
"""
import sys
sys.path.insert(0, '/workspace')

from core.tools_registry import register_tool, get_tools_registry, escape_markdown


def test_decorator():
    """Тест декоратора @register_tool"""
    print("\n=== Тест декоратора ===")
    
    @register_tool(
        name="test_function",
        description="Тестовая функция",
        tags=["test"],
        priority=0.7
    )
    def test_func(x: int) -> int:
        return x * 2
    
    # Проверяем что функция работает
    assert test_func(5) == 10
    print("✅ Функция работает")
    
    # Проверяем метаданные
    assert hasattr(test_func, '_tool_metadata')
    assert test_func._tool_metadata['name'] == "test_function"
    assert test_func._tool_metadata['description'] == "Тестовая функция"
    assert test_func._tool_metadata['tags'] == ["test"]
    assert test_func._tool_metadata['priority'] == 0.7
    print("✅ Метаданные сохранены")
    
    print("✅ Декоратор работает правильно!")


def test_markdown_escape():
    """Тест экранирования Markdown"""
    print("\n=== Тест Markdown экранирования ===")
    
    test_cases = [
        ("*bold*", "\\*bold\\*"),
        ("_italic_", "\\_italic\\_"),
        ("[link](url)", "\\[link\\]\\(url\\)"),
        ("code `block`", "code \\`block\\`"),
        ("# Header", "\\# Header"),
        ("List - item", "List \\- item"),
        ("Equation: a + b = c", "Equation: a \\+ b \\= c"),
        ("Quote > text", "Quote \\> text"),
        ("Pipe | separator", "Pipe \\| separator"),
        ("Curly {braces}", "Curly \\{braces\\}"),
        ("Exclamation!", "Exclamation\\!"),
    ]
    
    for input_text, expected in test_cases:
        result = escape_markdown(input_text)
        assert result == expected, f"Failed: {input_text} -> {result} (expected {expected})"
        print(f"✅ '{input_text}' -> '{result}'")
    
    print("✅ Markdown экранирование работает правильно!")


def test_openai_export():
    """Тест экспорта в формате OpenAI Function Calling"""
    print("\n=== Тест экспорта OpenAI Functions ===")
    
    registry = get_tools_registry()
    
    # Добавляем тестовый инструмент вручную
    from core.tools_registry import ToolMetadata
    from datetime import datetime
    
    test_tool = ToolMetadata(
        name="test_calculator",
        type="function",
        description="Калькулятор для *простых* операций",
        file_path="test.py",
        parameters={
            "a": {"type": "float", "description": "Первое число", "required": True},
            "b": {"type": "float", "description": "Второе число", "required": True},
            "operation": {"type": "str", "description": "Операция: +, -, *, /", "required": False}
        },
        is_available=True,
        last_updated=datetime.now()
    )
    
    registry.tools["test_calculator"] = test_tool
    
    # Экспортируем
    functions = registry.export_openai_functions()
    
    # Находим наш инструмент
    calc_func = None
    for func in functions:
        if func["name"] == "test_calculator":
            calc_func = func
            break
    
    assert calc_func is not None, "Инструмент не найден в экспорте"
    print("✅ Инструмент найден в экспорте")
    
    # Проверяем структуру
    assert "name" in calc_func
    assert "description" in calc_func
    assert "parameters" in calc_func
    print("✅ Структура корректна")
    
    # Проверяем экранирование Markdown в описании
    assert calc_func["description"] == "Калькулятор для \\*простых\\* операций"
    print("✅ Markdown экранирован в описании")
    
    # Проверяем параметры
    params = calc_func["parameters"]
    assert params["type"] == "object"
    assert "properties" in params
    assert "required" in params
    print("✅ Параметры в правильном формате")
    
    # Проверяем свойства
    props = params["properties"]
    assert "a" in props
    assert props["a"]["type"] == "number"  # float -> number
    assert props["a"]["description"] == "Первое число"
    
    assert "b" in props
    assert props["b"]["type"] == "number"
    
    assert "operation" in props
    assert props["operation"]["type"] == "string"  # str -> string
    print("✅ Типы правильно сконвертированы")
    
    # Проверяем required
    assert "a" in params["required"]
    assert "b" in params["required"]
    assert "operation" not in params["required"]
    print("✅ Required параметры правильные")
    
    print("✅ Экспорт OpenAI Functions работает правильно!")


def main():
    print("🧪 Запуск тестов для F-2: Tool Registry")
    
    test_decorator()
    test_markdown_escape()
    test_openai_export()
    
    print("\n🎉 Все тесты F-2 успешно пройдены!")


if __name__ == "__main__":
    main()