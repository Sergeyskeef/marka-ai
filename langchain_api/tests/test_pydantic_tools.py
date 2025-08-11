#!/usr/bin/env python3
"""
Тест для проверки работы function_tool с Pydantic схемами
"""

from agents.tool import function_tool
from pydantic import BaseModel


class TestInput(BaseModel):
    code: str
    timeout: int = 30


class TestOutput(BaseModel):
    output: str
    timeout: int


# Тест 1: Функция с отдельными параметрами
@function_tool
def test_tool_separate(code: str, timeout: int = 30) -> dict:
    """Test tool with separate parameters"""
    return {"output": code, "timeout": timeout}


# Тест 2: Функция с Pydantic объектом
@function_tool
def test_tool_pydantic(args: TestInput) -> TestOutput:
    """Test tool with Pydantic object"""
    return TestOutput(output=args.code, timeout=args.timeout)


if __name__ == "__main__":
    print("=== Тест 1: Отдельные параметры ===")
    try:
        result1 = test_tool_separate("print('test')", 10)
        print(f"✅ Результат: {result1}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print("\n=== Тест 2: Pydantic объект ===")
    try:
        args = TestInput(code="print('test')", timeout=10)
        result2 = test_tool_pydantic(args)
        print(f"✅ Результат: {result2}")
    except Exception as e:
        print(f"❌ Ошибка: {e}") 