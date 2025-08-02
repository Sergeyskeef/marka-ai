"""
Тест Pydantic-валидированных функций
Проверяет, что функции корректно работают с Pydantic схемами
"""

import pytest
from langchain_api.utils.toolkit import run_code, search_memory, summarize_text
from langchain_api.core.tools.schemas import (
    CodeExecutionIn, CodeExecutionOut,
    MemoryRetrieveIn, MemoryRetrieveOut,
    SummarizeIn, SummarizeOut
)
from pydantic import ValidationError


def test_run_code_success():
    """Тест успешного выполнения кода"""
    input_data = CodeExecutionIn(code='print("Hello World")', timeout=10)
    result = run_code(input_data)
    
    assert isinstance(result, CodeExecutionOut)
    assert result.output == "Hello World"
    assert result.error is None
    assert result.exit_code == 0
    assert result.execution_time > 0


def test_run_code_invalid_input():
    """Тест валидации неправильного ввода"""
    with pytest.raises(ValidationError):
        # Передаем неправильный тип
        CodeExecutionIn(code=123, timeout="invalid")


def test_search_memory_success():
    """Тест успешного поиска в памяти"""
    input_data = MemoryRetrieveIn(query="test query", limit=5)
    result = search_memory(input_data)
    
    assert isinstance(result, MemoryRetrieveOut)
    assert len(result.memories) > 0
    assert result.total_found > 0
    assert result.search_time >= 0


def test_summarize_text_success():
    """Тест успешной суммаризации"""
    input_data = SummarizeIn(
        text="Это очень длинный текст для тестирования суммаризации. Он содержит много слов и должен быть сокращен до краткого резюме.",
        max_length=50
    )
    result = summarize_text(input_data)
    
    assert isinstance(result, SummarizeOut)
    assert len(result.summary) > 0
    assert result.original_length > 0
    assert result.summary_length > 0
    assert 0 <= result.compression_ratio <= 1


def test_summarize_text_validation():
    """Тест валидации суммаризации"""
    with pytest.raises(ValidationError):
        # Передаем слишком короткий текст
        SummarizeIn(text="short", max_length=50)


def test_tool_imports():
    """Тест импорта функций"""
    from langchain_api.utils.toolkit import (
        run_code, search_memory, web_search, 
        graph_search, summarize_text, read_file, write_file
    )
    
    assert callable(run_code)
    assert callable(search_memory)
    assert callable(web_search)
    assert callable(graph_search)
    assert callable(summarize_text)
    assert callable(read_file)
    assert callable(write_file) 