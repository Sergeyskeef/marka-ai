"""
Тесты для системы регистрации инструментов (Tools Registry)
"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.tools_registry import (
    ToolMetadata,
    ToolsRegistry,
    get_available_tools,
    get_tools_for_llm,
    get_tools_registry,
    scan_and_register_tools,
)


class TestToolMetadata:
    """Тесты для класса ToolMetadata"""

    def test_tool_metadata_creation(self):
        """Тест создания метаданных инструмента"""
        tool = ToolMetadata(
            name="test_tool",
            type="function",
            description="Test function",
            file_path="/path/to/file.py",
            line_number=10,
            parameters={"param1": "str"},
            tags=["test", "function"],
            priority=0.8
        )

        assert tool.name == "test_tool"
        assert tool.type == "function"
        assert tool.description == "Test function"
        assert tool.file_path == "/path/to/file.py"
        assert tool.line_number == 10
        assert tool.parameters == {"param1": "str"}
        assert tool.tags == ["test", "function"]
        assert tool.priority == 0.8
        assert tool.is_available is True


class TestToolsRegistry:
    """Тесты для класса ToolsRegistry"""

    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.temp_dir = tempfile.mkdtemp()
        self.registry = ToolsRegistry(project_root=self.temp_dir)

        # Создаем тестовую структуру директорий
        self.scripts_dir = os.path.join(self.temp_dir, "scripts")
        self.utils_dir = os.path.join(self.temp_dir, "utils")
        self.services_dir = os.path.join(self.temp_dir, "services")

        os.makedirs(self.scripts_dir, exist_ok=True)
        os.makedirs(self.utils_dir, exist_ok=True)
        os.makedirs(self.services_dir, exist_ok=True)

    def teardown_method(self):
        """Очистка после каждого теста"""
        shutil.rmtree(self.temp_dir)

    def test_init(self):
        """Тест инициализации реестра"""
        assert self.registry.project_root == self.temp_dir
        assert isinstance(self.registry.tools, dict)
        assert len(self.registry.tools) == 0

        expected_dirs = ['scripts', 'utils', 'services', 'core', 'sandbox']
        assert self.registry.scan_directories == expected_dirs

    def test_scan_project_empty(self):
        """Тест сканирования пустого проекта"""
        tools = self.registry.scan_project()
        assert isinstance(tools, dict)
        assert len(tools) == 0

    def test_scan_project_with_files(self):
        """Тест сканирования проекта с файлами"""
        # Создаем тестовый Python файл
        test_file = os.path.join(self.scripts_dir, "test_script.py")
        with open(test_file, 'w') as f:
            f.write('''
"""
Test script for tools registry
"""

def test_function():
    """Test function docstring"""
    pass

class TestClass:
    """Test class docstring"""
    pass

if __name__ == "__main__":
    pass
''')

        tools = self.registry.scan_project()
        assert len(tools) >= 2  # Функция и класс

        # Проверяем, что найдена функция
        function_found = any(tool.name == "test_function" for tool in tools.values())
        assert function_found

        # Проверяем, что найден класс
        class_found = any(tool.name == "TestClass" for tool in tools.values())
        assert class_found

    def test_extract_function_metadata(self):
        """Тест извлечения метаданных функции"""
        import ast

        # Создаем AST для функции
        code = '''
def test_function(param1, param2):
    """Test function description"""
    pass
'''
        tree = ast.parse(code)
        func_node = tree.body[0]

        tool = self.registry._extract_function_metadata(
            func_node, "/path/to/file.py", "scripts"
        )

        assert tool.name == "test_function"
        assert tool.type == "script_function"
        assert tool.description == "Test function description"
        assert tool.file_path == "/path/to/file.py"
        assert tool.line_number == 2
        assert "param1" in tool.parameters
        assert "param2" in tool.parameters
        assert tool.tags == ["scripts", "function"]

    def test_extract_class_metadata(self):
        """Тест извлечения метаданных класса"""
        import ast

        # Создаем AST для класса
        code = '''
class TestClass:
    """Test class description"""
    pass
'''
        tree = ast.parse(code)
        class_node = tree.body[0]

        tool = self.registry._extract_class_metadata(
            class_node, "/path/to/file.py", "services"
        )

        assert tool.name == "TestClass"
        assert tool.type == "service_class"
        assert tool.description == "Test class description"
        assert tool.file_path == "/path/to/file.py"
        assert tool.line_number == 2
        assert tool.tags == ["services", "class"]

    def test_is_script_file(self):
        """Тест определения скрипта"""
        # Тест с shebang
        content1 = "#!/usr/bin/env python\nprint('hello')"
        result1 = self.registry._is_script_file("/path/scripts/test.py", content1)
        print(f"Test 1 - shebang: {result1}")
        assert result1 is True

        # Тест с main блоком - исправляем логику
        content2 = "print('hello')\nif __name__ == '__main__':\n    pass"
        result2 = self.registry._is_script_file("/path/scripts/test.py", content2)
        print(f"Test 2 - main block: {result2}")
        print(f"Content2: {repr(content2)}")
        has_main = 'if __name__ == "__main__"' in content2
        print(f"Has main: {has_main}")
        is_in_scripts = 'scripts' in '/path/scripts/test.py'
        print(f"Is in scripts: {is_in_scripts}")
        # Файл должен быть в директории scripts И содержать main блок
        assert result2 is True

        # Тест не скрипта - файл не в scripts директории
        content3 = "print('hello')\nif __name__ == '__main__':\n    pass"
        result3 = self.registry._is_script_file("/path/utils/test.py", content3)
        print(f"Test 3 - not in scripts: {result3}")
        assert result3 is False

    def test_get_tools_filtering(self):
        """Тест фильтрации инструментов"""
        # Добавляем тестовые инструменты
        tool1 = ToolMetadata(
            name="script_tool",
            type="script",
            description="Script tool",
            file_path="/path/script.py",
            tags=["scripts", "script"]
        )

        tool2 = ToolMetadata(
            name="function_tool",
            type="function",
            description="Function tool",
            file_path="/path/function.py",
            tags=["utils", "function"]
        )

        self.registry.tools = {
            "script_tool": tool1,
            "function_tool": tool2
        }

        # Тест фильтрации по типу
        script_tools = self.registry.get_tools(tool_type="script")
        assert len(script_tools) == 1
        assert script_tools[0].name == "script_tool"

        # Тест фильтрации по тегам
        utils_tools = self.registry.get_tools(tags=["utils"])
        assert len(utils_tools) == 1
        assert utils_tools[0].name == "function_tool"

    def test_get_tool(self):
        """Тест получения конкретного инструмента"""
        tool = ToolMetadata(
            name="test_tool",
            type="function",
            description="Test tool",
            file_path="/path/tool.py"
        )

        self.registry.tools["test_tool"] = tool

        found_tool = self.registry.get_tool("test_tool")
        assert found_tool == tool

        not_found = self.registry.get_tool("nonexistent")
        assert not_found is None

    def test_update_tool(self):
        """Тест обновления инструмента"""
        tool = ToolMetadata(
            name="test_tool",
            type="function",
            description="Old description",
            file_path="/path/tool.py"
        )

        self.registry.tools["test_tool"] = tool

        # Обновляем описание
        success = self.registry.update_tool("test_tool", description="New description")
        assert success is True

        updated_tool = self.registry.tools["test_tool"]
        assert updated_tool.description == "New description"
        assert updated_tool.last_updated is not None

        # Попытка обновить несуществующий инструмент
        success = self.registry.update_tool("nonexistent", description="New")
        assert success is False

    def test_add_and_remove_tool(self):
        """Тест добавления и удаления инструмента"""
        tool = ToolMetadata(
            name="test_tool",
            type="function",
            description="Test tool",
            file_path="/path/tool.py"
        )

        # Добавляем инструмент
        self.registry.add_tool(tool)
        assert "test_tool" in self.registry.tools
        assert self.registry.tools["test_tool"] == tool

        # Удаляем инструмент
        success = self.registry.remove_tool("test_tool")
        assert success is True
        assert "test_tool" not in self.registry.tools

        # Попытка удалить несуществующий инструмент
        success = self.registry.remove_tool("nonexistent")
        assert success is False

    def test_export_tools(self):
        """Тест экспорта инструментов"""
        tool = ToolMetadata(
            name="test_tool",
            type="function",
            description="Test tool",
            file_path="/path/tool.py"
        )

        self.registry.tools["test_tool"] = tool

        export = self.registry.export_tools()

        assert "tools" in export
        assert "total_count" in export
        assert "last_scan" in export
        assert export["total_count"] == 1
        assert "test_tool" in export["tools"]

    def test_get_tools_for_llm(self):
        """Тест получения инструментов для LLM"""
        tool1 = ToolMetadata(
            name="available_tool",
            type="function",
            description="Available tool",
            file_path="/path/tool.py",
            is_available=True,
            priority=0.8
        )

        tool2 = ToolMetadata(
            name="unavailable_tool",
            type="function",
            description="Unavailable tool",
            file_path="/path/tool.py",
            is_available=False,
            priority=0.9
        )

        self.registry.tools = {
            "available_tool": tool1,
            "unavailable_tool": tool2
        }

        llm_tools = self.registry.get_tools_for_llm()

        assert len(llm_tools) == 1
        assert llm_tools[0]["name"] == "available_tool"
        assert "type" in llm_tools[0]
        assert "description" in llm_tools[0]
        assert "file_path" in llm_tools[0]
        assert "tags" in llm_tools[0]
        assert "priority" in llm_tools[0]


class TestToolsRegistryFunctions:
    """Тесты для функций модуля"""

    def test_get_tools_registry(self):
        """Тест получения глобального реестра"""
        registry = get_tools_registry()
        assert isinstance(registry, ToolsRegistry)

    @patch('langchain_api.core.tools_registry.get_tools_registry')
    def test_scan_and_register_tools(self, mock_get_registry):
        """Тест сканирования и регистрации инструментов"""
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_registry.scan_project.return_value = {"tool1": mock_tool}
        mock_get_registry.return_value = mock_registry

        result = scan_and_register_tools()

        # Проверяем, что результат содержит ожидаемый ключ
        assert "tool1" in result
        mock_registry.scan_project.assert_called_once()

    @patch('langchain_api.core.tools_registry.get_tools_registry')
    def test_get_available_tools(self, mock_get_registry):
        """Тест получения доступных инструментов"""
        mock_registry = MagicMock()
        mock_registry.get_tools.return_value = [MagicMock()]
        mock_get_registry.return_value = mock_registry

        tools = get_available_tools(tool_type="function", tags=["test"])

        assert len(tools) == 1
        # Исправляем проверку параметров - используем позиционные аргументы
        mock_registry.get_tools.assert_called_once_with("function", ["test"])

    @patch('langchain_api.core.tools_registry.get_tools_registry')
    def test_get_tools_for_llm(self, mock_get_registry):
        """Тест получения инструментов для LLM"""
        mock_registry = MagicMock()
        mock_registry.get_tools_for_llm.return_value = [{"name": "tool1"}]
        mock_get_registry.return_value = mock_registry

        tools = get_tools_for_llm()

        assert len(tools) == 1
        assert tools[0]["name"] == "tool1"
        mock_registry.get_tools_for_llm.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
