#!/usr/bin/env python3
"""
Демонстрационный скрипт для тестирования Tools Registry
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tools_registry import ToolsRegistry, scan_and_register_tools, get_available_tools, get_tools_for_llm
import json

def main():
    print("🔍 Сканирование проекта для обнаружения инструментов...")
    
    # Создаем реестр с правильным путем к проекту
    project_root = "/app/langchain_api"
    registry = ToolsRegistry(project_root=project_root)
    
    print(f"📁 Сканирую директорию: {project_root}")
    
    # Сканируем проект
    tools = registry.scan_project()
    
    print(f"✅ Обнаружено {len(tools)} инструментов")
    print("\n📋 Список всех инструментов:")
    
    for name, tool in tools.items():
        print(f"  • {name} ({tool.type}) - {tool.description[:50]}...")
    
    print("\n🔧 Инструменты по типам:")
    
    # Показываем инструменты по типам
    script_tools = registry.get_tools(tool_type="script")
    function_tools = registry.get_tools(tool_type="function")
    class_tools = registry.get_tools(tool_type="class")
    
    print(f"  📜 Скрипты: {len(script_tools)}")
    for tool in script_tools[:5]:  # Показываем первые 5
        print(f"    - {tool.name}")
    
    print(f"  ⚙️ Функции: {len(function_tools)}")
    for tool in function_tools[:5]:  # Показываем первые 5
        print(f"    - {tool.name}")
    
    print(f"  🏗️ Классы: {len(class_tools)}")
    for tool in class_tools[:5]:  # Показываем первые 5
        print(f"    - {tool.name}")
    
    print("\n🤖 Инструменты для LLM:")
    llm_tools = registry.get_tools_for_llm()
    print(f"  Доступно для LLM: {len(llm_tools)} инструментов")
    
    # Показываем первые 3 инструмента для LLM
    for i, tool in enumerate(llm_tools[:3]):
        print(f"  {i+1}. {tool['name']} ({tool['type']})")
        print(f"     Описание: {tool['description'][:60]}...")
        print(f"     Файл: {tool['file_path']}")
        print(f"     Приоритет: {tool['priority']}")
        print()
    
    print("✅ Демонстрация завершена!")

if __name__ == "__main__":
    main() 