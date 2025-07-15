#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для расширенных инструментов разработки.
"""

import pytest
import json
import os
import tempfile
import shutil
from unittest.mock import patch, mock_open
from pathlib import Path

# Добавляем путь к модулям
import sys
sys.path.append('/app/langchain_api')

from sandbox.development_tools import (
    create_python_file,
    edit_file,
    analyze_task_requirements,
    create_implementation_plan,
    create_diff_report,
    _is_safe_path
)

class TestDevelopmentTools:
    """Тесты для инструментов разработки."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.test_dir = tempfile.mkdtemp()
        self.safe_test_dir = os.path.join(self.test_dir, "sandbox")
        os.makedirs(self.safe_test_dir, exist_ok=True)
        
    def teardown_method(self):
        """Очистка после каждого теста."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_is_safe_path(self):
        """Тест проверки безопасных путей."""
        # Безопасные пути
        assert _is_safe_path("/app/langchain_api/sandbox/test.py")
        assert _is_safe_path("/app/langchain_api/tests/test_file.py")
        assert _is_safe_path("/app/langchain_api/scripts/script.py")
        
        # Небезопасные пути
        assert not _is_safe_path("/etc/passwd")
        assert not _is_safe_path("/root/.bashrc")
        assert not _is_safe_path("/var/log/syslog")
    
    def test_create_python_file_success(self):
        """Тест успешного создания Python файла."""
        test_path = os.path.join(self.safe_test_dir, "test_file.py")
        test_content = '''#!/usr/bin/env python3
def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
'''
        
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            result = create_python_file(test_path, test_content)
        
        assert "✅ ФАЙЛ СОЗДАН" in result
        assert "test_file.py" in result
        assert "Синтаксис Python корректен" in result
        assert os.path.exists(test_path)
        
        # Проверяем содержимое файла
        with open(test_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert content == test_content
    
    def test_create_python_file_unsafe_path(self):
        """Тест создания файла с небезопасным путем."""
        result = create_python_file("/etc/test.py", "print('test')")
        assert "❌ НЕБЕЗОПАСНЫЙ ПУТЬ" in result
    
    def test_create_python_file_syntax_error(self):
        """Тест создания файла с синтаксической ошибкой."""
        test_path = os.path.join(self.safe_test_dir, "syntax_error.py")
        invalid_content = "def test(:\n    print('invalid syntax'"
        
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            result = create_python_file(test_path, invalid_content)
        
        assert "⚠️ ОШИБКА СИНТАКСИСА" in result
        assert os.path.exists(test_path)  # Файл все равно создается
    
    def test_edit_file_success(self):
        """Тест успешного редактирования файла."""
        test_path = os.path.join(self.safe_test_dir, "edit_test.py")
        original_content = '''#!/usr/bin/env python3
def hello():
    print("Hello")

def world():
    print("World")
'''
        
        # Создаем исходный файл
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            create_python_file(test_path, original_content)
        
        # Редактируем файл
        changes = json.dumps({
            "add_lines": [{"line": 2, "content": "    # Добавленный комментарий"}],
            "replace_lines": [{"line": 1, "content": "def hello_updated():"}],
            "delete_lines": [5]  # После добавления строки на позицию 2, строка 4 становится строкой 5
        })
        
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            result = edit_file(test_path, changes)
        
        assert "✅ ФАЙЛ ОТРЕДАКТИРОВАН" in result
        assert "Добавлена строка" in result
        assert "Заменена строка" in result
        assert "Удалена строка" in result
        
        # Проверяем результат
        with open(test_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "hello_updated" in content
        assert "# Добавленный комментарий" in content
        assert "def world():" not in content
    
    def test_edit_file_file_not_exists(self):
        """Тест редактирования несуществующего файла."""
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            result = edit_file("/nonexistent/file.py", '{"add_lines": []}')
        assert "❌ ФАЙЛ НЕ СУЩЕСТВУЕТ" in result
    
    def test_edit_file_invalid_json(self):
        """Тест редактирования с некорректным JSON."""
        test_path = os.path.join(self.safe_test_dir, "test.py")
        with open(test_path, 'w') as f:
            f.write("print('test')")
        
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            result = edit_file(test_path, "invalid json")
        assert "❌ НЕКОРРЕКТНЫЙ JSON" in result
    
    def test_analyze_task_requirements(self):
        """Тест анализа требований к задаче."""
        task = "Создать API endpoint для работы с файлами и добавить тесты"
        result = analyze_task_requirements(task)
        
        assert "📋 АНАЛИЗ ТРЕБОВАНИЙ К ЗАДАЧЕ" in result
        assert "Создать API endpoint для работы с файлами" in result
        assert "api" in result.lower() or "файл" in result.lower()
        assert "📊 Оценка сложности" in result
    
    def test_create_implementation_plan(self):
        """Тест создания плана реализации."""
        requirements = "Создать API endpoint для работы с файлами"
        result = create_implementation_plan(requirements)
        
        assert "📋 ПЛАН РЕАЛИЗАЦИИ" in result
        assert "Создать API endpoint для работы с файлами" in result
        assert "🚀 Фазы реализации" in result
        assert "✅ Критерии успеха" in result
    
    def test_create_diff_report_code_comparison(self):
        """Тест создания diff отчета для сравнения кода."""
        before_code = "def hello():\n    print('Hello')"
        after_code = "def hello():\n    print('Hello, World!')"
        description = "Обновлен вывод функции"
        
        result = create_diff_report(before_code, after_code, description)
        
        assert "📊 ОТЧЕТ ОБ ИЗМЕНЕНИЯХ" in result
        assert "Обновлен вывод функции" in result
        assert "Измененных строк: 1" in result or "Измененных строк:" in result
    
    def test_create_diff_report_file_comparison(self):
        """Тест создания diff отчета для сравнения файлов."""
        before_file = os.path.join(self.safe_test_dir, "before.py")
        after_file = os.path.join(self.safe_test_dir, "after.py")
        
        # Создаем тестовые файлы
        with open(before_file, 'w') as f:
            f.write("def old():\n    pass")
        
        with open(after_file, 'w') as f:
            f.write("def new():\n    pass")
        
        result = create_diff_report(before_file, after_file, "Переименована функция")
        
        assert "📊 ОТЧЕТ ОБ ИЗМЕНЕНИЯХ" in result
        assert "Переименована функция" in result
    
    def test_create_diff_report_with_additions(self):
        """Тест создания diff отчета с добавлениями."""
        before_code = "def test():\n    pass"
        after_code = "def test():\n    pass\n\ndef new_function():\n    pass"
        description = "Добавлена новая функция"
        
        result = create_diff_report(before_code, after_code, description)
        
        assert "Добавленных строк: 2" in result or "Добавленных строк:" in result
        assert "new_function" in result
    
    def test_create_diff_report_with_deletions(self):
        """Тест создания diff отчета с удалениями."""
        before_code = "def test():\n    pass\n\ndef old_function():\n    pass"
        after_code = "def test():\n    pass"
        description = "Удалена старая функция"
        
        result = create_diff_report(before_code, after_code, description)
        
        assert "Удаленных строк: 2" in result or "Удаленных строк:" in result
        assert "old_function" in result
    
    def test_error_handling(self):
        """Тест обработки ошибок."""
        # Тест с несуществующим путем
        result = create_python_file("", "test")
        assert "❌" in result
        
        # Тест с некорректными данными
        result = analyze_task_requirements("")
        assert "📋 АНАЛИЗ ТРЕБОВАНИЙ К ЗАДАЧЕ" in result  # Должен работать с пустой строкой

def test_integration_workflow():
    """Интеграционный тест полного рабочего процесса."""
    with tempfile.TemporaryDirectory() as temp_dir:
        safe_dir = os.path.join(temp_dir, "sandbox")
        os.makedirs(safe_dir, exist_ok=True)
        
        # 1. Анализируем требования
        task = "Создать утилиту для работы с JSON файлами"
        requirements = analyze_task_requirements(task)
        assert "📋 АНАЛИЗ ТРЕБОВАНИЙ" in requirements
        
        # 2. Создаем план
        plan = create_implementation_plan(task)
        assert "📋 ПЛАН РЕАЛИЗАЦИИ" in plan
        
        # 3. Создаем файл
        test_file = os.path.join(safe_dir, "json_utils.py")
        content = '''#!/usr/bin/env python3
import json

def read_json(file_path):
    """Читает JSON файл."""
    with open(file_path, 'r') as f:
        return json.load(f)

def write_json(file_path, data):
    """Записывает данные в JSON файл."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
'''
        
        with patch('sandbox.development_tools._is_safe_path', return_value=True):
            result = create_python_file(test_file, content)
            assert "✅ ФАЙЛ СОЗДАН" in result
            
            # 4. Редактируем файл
            changes = json.dumps({
                "add_lines": [{"line": 1, "content": "# JSON utilities module"}]
            })
            edit_result = edit_file(test_file, changes)
            assert "✅ ФАЙЛ ОТРЕДАКТИРОВАН" in edit_result
            
            # 5. Создаем diff отчет
            diff_result = create_diff_report(
                content,
                "# JSON utilities module\n" + content,
                "Добавлен заголовок модуля"
            )
            assert "📊 ОТЧЕТ ОБ ИЗМЕНЕНИЯХ" in diff_result

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 