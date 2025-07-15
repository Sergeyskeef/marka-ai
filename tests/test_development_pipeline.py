#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для development pipeline
"""

import pytest
import json
import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.append(str(Path(__file__).parent.parent))

from sandbox.development_pipeline import develop_tool, DevelopmentPipeline

def test_development_pipeline_import():
    """Тест импорта модуля."""
    from sandbox.development_pipeline import DevelopmentPipeline, develop_tool
    assert DevelopmentPipeline is not None
    assert develop_tool is not None

def test_analyze_task_requirements():
    """Тест анализа требований."""
    pipeline = DevelopmentPipeline()
    requirements = pipeline.analyze_task_requirements("echo tool")
    
    assert requirements is not None
    assert "task_description" in requirements
    assert "complexity" in requirements
    assert "components" in requirements

def test_create_implementation_plan():
    """Тест создания плана реализации."""
    pipeline = DevelopmentPipeline()
    requirements = pipeline.analyze_task_requirements("echo tool")
    plan = pipeline.create_implementation_plan(requirements)
    
    assert plan is not None
    assert "phases" in plan
    assert "files_to_create" in plan
    assert len(plan["phases"]) > 0

def test_generate_tool_name():
    """Тест генерации имени инструмента."""
    pipeline = DevelopmentPipeline()
    
    # Тест для echo tool
    name1 = pipeline._generate_tool_name("echo tool")
    assert name1 == "echo_tool"
    
    # Тест для calculator
    name2 = pipeline._generate_tool_name("calculator tool")
    assert name2 == "calculator_tool"
    
    # Тест для общего случая
    name3 = pipeline._generate_tool_name("custom tool")
    assert "tool" in name3

def test_develop_tool_full_cycle():
    """Тест полного цикла разработки инструмента."""
    result = develop_tool("echo tool")
    
    # Проверяем, что результат - валидный JSON
    parsed_result = json.loads(result)
    
    assert parsed_result is not None
    assert "task_description" in parsed_result
    assert "tool_name" in parsed_result
    assert "requirements_analysis" in parsed_result
    assert "implementation_plan" in parsed_result
    assert "code_generation" in parsed_result
    assert "testing" in parsed_result
    assert "diff_report" in parsed_result
    
    # Проверяем, что инструмент создан
    assert parsed_result["tool_name"] == "echo_tool"
    
    # Проверяем успешность операций
    assert parsed_result["requirements_analysis"].get("success", True)
    assert parsed_result["implementation_plan"].get("success", True)
    assert parsed_result["code_generation"].get("success", True)

def test_generate_main_file():
    """Тест генерации основного файла."""
    pipeline = DevelopmentPipeline()
    requirements = pipeline.analyze_task_requirements("echo tool")
    
    content = pipeline._generate_main_file("echo_tool", requirements)
    
    assert content is not None
    assert "def echo_tool" in content
    assert "import json" in content
    assert "return json.dumps" in content

def test_generate_test_file():
    """Тест генерации файла тестов."""
    pipeline = DevelopmentPipeline()
    requirements = pipeline.analyze_task_requirements("echo tool")
    
    content = pipeline._generate_test_file("echo_tool", requirements)
    
    assert content is not None
    assert "def test_echo_tool" in content
    assert "import pytest" in content
    assert "from echo_tool import echo_tool" in content

def test_generate_documentation():
    """Тест генерации документации."""
    pipeline = DevelopmentPipeline()
    requirements = pipeline.analyze_task_requirements("echo tool")
    
    content = pipeline._generate_documentation("echo_tool", requirements)
    
    assert content is not None
    assert "# echo_tool" in content
    assert "## Описание" in content
    assert "## Использование" in content

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 