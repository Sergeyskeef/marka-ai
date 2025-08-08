"""
Инструменты для тестирования кода
"""

import os
import json
import logging
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import re
import xml.etree.ElementTree as ET

from .tools import create_openai_tool
from ..config import settings

logger = logging.getLogger(__name__)

# Безопасные директории для тестирования
TEST_SAFE_DIRS = [
    "/workspace",
    "/app",
    "/sandbox"
]

# Максимальное время выполнения тестов (секунды)
MAX_TEST_DURATION = 300  # 5 минут

# Поддерживаемые тестовые фреймворки
SUPPORTED_FRAMEWORKS = {
    "pytest": {
        "command": ["python3", "-m", "pytest"],
        "config_files": ["pytest.ini", "pyproject.toml", "setup.cfg"],
        "test_patterns": ["test_*.py", "*_test.py", "tests/"]
    },
    "unittest": {
        "command": ["python3", "-m", "unittest"],
        "config_files": [],
        "test_patterns": ["test_*.py", "*_test.py"]
    }
}


def is_safe_test_path(path: str) -> bool:
    """Проверка безопасности пути для тестов"""
    try:
        abs_path = os.path.abspath(path)
        return any(abs_path.startswith(safe_dir) for safe_dir in TEST_SAFE_DIRS)
    except Exception:
        return False


@create_openai_tool
async def run_tests(
    test_path: str = ".",
    framework: str = "pytest",
    args: Optional[str] = None,
    coverage: bool = False,
    verbose: bool = True,
    timeout: int = MAX_TEST_DURATION
) -> str:
    """
    Запускает тесты в указанной директории или файле.
    
    Args:
        test_path: Путь к тестам (файл или директория)
        framework: Тестовый фреймворк (pytest, unittest)
        args: Дополнительные аргументы для тестового фреймворка
        coverage: Включить измерение покрытия кода
        verbose: Подробный вывод
        timeout: Максимальное время выполнения в секундах
        
    Returns:
        Результаты выполнения тестов в формате JSON
    """
    try:
        # Нормализация пути
        if not os.path.isabs(test_path):
            test_path = os.path.join("/workspace", test_path)
        
        # Проверка безопасности
        if not is_safe_test_path(test_path):
            return json.dumps({
                "success": False,
                "error": f"Небезопасный путь: {test_path}"
            })
        
        # Проверка существования
        if not os.path.exists(test_path):
            return json.dumps({
                "success": False,
                "error": f"Путь не найден: {test_path}"
            })
        
        # Проверка фреймворка
        if framework not in SUPPORTED_FRAMEWORKS:
            return json.dumps({
                "success": False,
                "error": f"Неподдерживаемый фреймворк: {framework}. Доступны: {list(SUPPORTED_FRAMEWORKS.keys())}"
            })
        
        # Формирование команды
        framework_info = SUPPORTED_FRAMEWORKS[framework]
        cmd_parts = list(framework_info["command"])  # Копируем список команды
        
        # Добавляем путь
        cmd_parts.append(test_path)
        
        # Добавляем флаги
        if framework == "pytest":
            if verbose:
                cmd_parts.append("-v")
            cmd_parts.append("--tb=short")
            cmd_parts.append("--no-header")
            
            # Покрытие кода
            if coverage:
                cmd_parts.extend(["--cov", "--cov-report=json", "--cov-report=term"])
            
            # JSON отчет для парсинга
            cmd_parts.append("--json-report")
            cmd_parts.append("--json-report-file=/tmp/pytest_report.json")
        
        # Дополнительные аргументы
        if args:
            cmd_parts.extend(args.split())
        
        # Выполнение команды
        logger.info(f"🧪 Запуск тестов: {' '.join(cmd_parts)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(test_path) if os.path.isfile(test_path) else test_path
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return json.dumps({
                "success": False,
                "error": f"Тесты превысили лимит времени ({timeout} сек)"
            })
        
        # Декодируем вывод
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')
        
        # Парсим результаты
        result = {
            "success": process.returncode == 0,
            "return_code": process.returncode,
            "framework": framework,
            "test_path": test_path,
            "stdout": stdout_text[-5000:],  # Последние 5000 символов
            "stderr": stderr_text[-1000:] if stderr_text else None
        }
        
        # Пытаемся распарсить pytest JSON отчет
        if framework == "pytest" and os.path.exists("/tmp/pytest_report.json"):
            try:
                with open("/tmp/pytest_report.json", 'r') as f:
                    pytest_data = json.load(f)
                
                result["summary"] = {
                    "total": pytest_data.get("summary", {}).get("total", 0),
                    "passed": pytest_data.get("summary", {}).get("passed", 0),
                    "failed": pytest_data.get("summary", {}).get("failed", 0),
                    "skipped": pytest_data.get("summary", {}).get("skipped", 0),
                    "duration": pytest_data.get("duration", 0)
                }
                
                # Добавляем информацию о неудачных тестах
                if pytest_data.get("tests"):
                    failed_tests = [
                        {
                            "name": test["nodeid"],
                            "outcome": test["outcome"],
                            "duration": test.get("duration", 0)
                        }
                        for test in pytest_data["tests"]
                        if test["outcome"] == "failed"
                    ]
                    if failed_tests:
                        result["failed_tests"] = failed_tests[:10]  # Максимум 10
                
                try:
                    os.remove("/tmp/pytest_report.json")
                except FileNotFoundError:
                    pass
            except Exception as e:
                logger.error(f"Ошибка парсинга pytest отчета: {e}")
        
        # Парсим покрытие если есть
        if coverage and os.path.exists("coverage.json"):
            try:
                with open("coverage.json", 'r') as f:
                    cov_data = json.load(f)
                
                result["coverage"] = {
                    "percent": cov_data.get("totals", {}).get("percent_covered", 0),
                    "lines_covered": cov_data.get("totals", {}).get("num_executed_lines", 0),
                    "lines_total": cov_data.get("totals", {}).get("num_statements", 0)
                }
            except Exception as e:
                logger.error(f"Ошибка парсинга coverage: {e}")
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка запуска тестов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def create_test(
    source_file: str,
    test_file: Optional[str] = None,
    framework: str = "pytest",
    test_class: bool = True
) -> str:
    """
    Создает шаблон теста для указанного файла.
    
    Args:
        source_file: Путь к файлу для которого создается тест
        test_file: Путь к файлу теста (если не указан, генерируется автоматически)
        framework: Тестовый фреймворк
        test_class: Использовать класс для группировки тестов
        
    Returns:
        Сообщение о создании теста
    """
    try:
        # Импортируем file_tools для работы с файлами
        from .file_tools import read_file, write_file, is_safe_path
        
        # Нормализация пути
        if not os.path.isabs(source_file):
            source_file = os.path.join("/workspace", source_file)
        
        # Проверка безопасности
        if not is_safe_path(source_file):
            return f"❌ Небезопасный путь: {source_file}"
        
        # Читаем исходный файл
        source_content = await read_file(source_file)
        if source_content.startswith("❌"):
            return source_content
        
        # Парсим AST для анализа
        import ast
        try:
            tree = ast.parse(source_content)
        except SyntaxError as e:
            return f"❌ Ошибка синтаксиса в {source_file}: {e}"
        
        # Находим функции и классы
        functions = []
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Пропускаем приватные и защищенные методы
                if not node.name.startswith('_'):
                    functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        
        # Генерируем путь к тесту если не указан
        if not test_file:
            source_path = Path(source_file)
            test_dir = source_path.parent / "tests"
            test_name = f"test_{source_path.stem}.py"
            test_file = str(test_dir / test_name)
        
        # Генерируем содержимое теста
        module_name = Path(source_file).stem
        test_content = []
        
        # Заголовок
        test_content.append('"""')
        test_content.append(f'Тесты для {module_name}')
        test_content.append('"""')
        test_content.append('')
        
        # Импорты
        if framework == "pytest":
            test_content.append('import pytest')
        else:
            test_content.append('import unittest')
        
        test_content.append(f'from {module_name} import *')
        test_content.append('')
        test_content.append('')
        
        # Генерация тестов
        if framework == "pytest":
            if test_class and (functions or classes):
                test_content.append(f'class Test{module_name.title()}:')
                test_content.append('    """Тесты для модуля"""')
                test_content.append('')
                
                # Тесты для функций
                for func in functions[:5]:  # Максимум 5 функций
                    test_content.append(f'    def test_{func}(self):')
                    test_content.append(f'        """Тест для {func}"""')
                    test_content.append('        # TODO: Реализовать тест')
                    test_content.append(f'        # result = {func}()')
                    test_content.append('        # assert result is not None')
                    test_content.append('        pass')
                    test_content.append('')
                
                # Тесты для классов
                for cls in classes[:3]:  # Максимум 3 класса
                    test_content.append(f'    def test_{cls.lower()}_creation(self):')
                    test_content.append(f'        """Тест создания {cls}"""')
                    test_content.append('        # TODO: Реализовать тест')
                    test_content.append(f'        # obj = {cls}()')
                    test_content.append('        # assert obj is not None')
                    test_content.append('        pass')
                    test_content.append('')
            else:
                # Простые функции без класса
                for func in functions[:5]:
                    test_content.append(f'def test_{func}():')
                    test_content.append(f'    """Тест для {func}"""')
                    test_content.append('    # TODO: Реализовать тест')
                    test_content.append('    pass')
                    test_content.append('')
        else:
            # unittest
            test_content.append(f'class Test{module_name.title()}(unittest.TestCase):')
            test_content.append('    """Тесты для модуля"""')
            test_content.append('')
            
            test_content.append('    def setUp(self):')
            test_content.append('        """Подготовка к тестам"""')
            test_content.append('        pass')
            test_content.append('')
            
            for func in functions[:5]:
                test_content.append(f'    def test_{func}(self):')
                test_content.append(f'        """Тест для {func}"""')
                test_content.append('        # TODO: Реализовать тест')
                test_content.append('        self.assertTrue(True)')
                test_content.append('')
            
            test_content.append('')
            test_content.append('if __name__ == "__main__":')
            test_content.append('    unittest.main()')
        
        # Записываем файл
        result = await write_file(test_file, '\n'.join(test_content))
        
        if result.startswith("✅"):
            return (f"✅ Создан шаблон теста: {test_file}\n"
                   f"   Найдено функций: {len(functions)}\n"
                   f"   Найдено классов: {len(classes)}\n"
                   f"   Фреймворк: {framework}")
        else:
            return result
            
    except Exception as e:
        logger.error(f"Ошибка создания теста: {e}")
        return f"❌ Ошибка создания теста: {str(e)}"


@create_openai_tool
async def analyze_test_coverage(
    path: str = ".",
    min_coverage: float = 80.0,
    format: str = "json"
) -> str:
    """
    Анализирует покрытие кода тестами.
    
    Args:
        path: Путь к проекту
        min_coverage: Минимальный процент покрытия
        format: Формат отчета (json, html, xml)
        
    Returns:
        Отчет о покрытии в указанном формате
    """
    try:
        # Нормализация пути
        if not os.path.isabs(path):
            path = os.path.join("/workspace", path)
        
        # Проверка безопасности
        if not is_safe_test_path(path):
            return json.dumps({
                "success": False,
                "error": f"Небезопасный путь: {path}"
            })
        
        # Формируем команду coverage
        cmd_parts = ["python3", "-m", "coverage", "run", "-m", "pytest", path]
        
        # Запуск тестов с coverage
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=path
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            # Тесты не прошли, но coverage все равно может быть
            logger.warning(f"Тесты завершились с ошибкой: {process.returncode}")
        
        # Генерация отчета
        report_cmd = ["python3", "-m", "coverage", "report", "--format=json"]
        
        if format == "html":
            report_cmd = ["python3", "-m", "coverage", "html", "-d", "/tmp/coverage_html"]
        elif format == "xml":
            report_cmd = ["python3", "-m", "coverage", "xml", "-o", "/tmp/coverage.xml"]
        
        report_process = await asyncio.create_subprocess_exec(
            *report_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=path
        )
        
        report_stdout, report_stderr = await report_process.communicate()
        
        # Парсим результаты
        if format == "json":
            try:
                coverage_data = json.loads(report_stdout.decode())
                
                total_percent = coverage_data.get("totals", {}).get("percent_covered", 0)
                
                result = {
                    "success": True,
                    "total_coverage": round(total_percent, 2),
                    "meets_minimum": total_percent >= min_coverage,
                    "minimum_required": min_coverage,
                    "summary": {
                        "files": coverage_data.get("totals", {}).get("num_files", 0),
                        "lines": coverage_data.get("totals", {}).get("num_statements", 0),
                        "covered": coverage_data.get("totals", {}).get("num_executed_lines", 0),
                        "missing": coverage_data.get("totals", {}).get("num_missing_lines", 0)
                    }
                }
                
                # Файлы с низким покрытием
                if coverage_data.get("files"):
                    low_coverage_files = []
                    for file_path, file_data in coverage_data["files"].items():
                        file_percent = file_data.get("summary", {}).get("percent_covered", 0)
                        if file_percent < min_coverage:
                            low_coverage_files.append({
                                "file": file_path,
                                "coverage": round(file_percent, 2),
                                "missing_lines": file_data.get("missing_lines", [])[:10]
                            })
                    
                    if low_coverage_files:
                        result["low_coverage_files"] = sorted(
                            low_coverage_files,
                            key=lambda x: x["coverage"]
                        )[:10]
                
                return json.dumps(result, ensure_ascii=False, indent=2)
                
            except json.JSONDecodeError as e:
                return json.dumps({
                    "success": False,
                    "error": f"Ошибка парсинга coverage JSON: {e}"
                })
        else:
            return json.dumps({
                "success": True,
                "format": format,
                "message": f"Отчет сгенерирован в формате {format}",
                "location": f"/tmp/coverage.{format}" if format != "html" else "/tmp/coverage_html/index.html"
            })
            
    except Exception as e:
        logger.error(f"Ошибка анализа покрытия: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def find_tests(
    directory: str = ".",
    pattern: str = "test_*.py",
    framework: Optional[str] = None
) -> str:
    """
    Находит все тестовые файлы в проекте.
    
    Args:
        directory: Директория для поиска
        pattern: Паттерн имен тестовых файлов
        framework: Фильтр по фреймворку (если указан)
        
    Returns:
        Список найденных тестовых файлов
    """
    try:
        from .file_tools import list_files
        
        # Получаем список файлов
        files_json = await list_files(
            directory=directory,
            pattern=pattern,
            recursive=True,
            max_files=200
        )
        
        files_data = json.loads(files_json)
        
        if "error" in files_data:
            return json.dumps({
                "success": False,
                "error": files_data["error"]
            })
        
        test_files = []
        
        # Нормализуем путь директории один раз
        if not os.path.isabs(directory):
            directory = os.path.join("/workspace", directory)
        
        # Анализируем каждый найденный файл
        for file_info in files_data.get("files", []):
            file_path = os.path.join(directory, file_info["path"])
            
            # Определяем фреймворк
            detected_framework = None
            
            try:
                # Читаем первые строки файла для определения фреймворка
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(500)  # Первые 500 символов
                    
                if "import pytest" in content or "pytest" in content:
                    detected_framework = "pytest"
                elif "import unittest" in content or "unittest.TestCase" in content:
                    detected_framework = "unittest"
            except:
                pass
            
            # Фильтруем по фреймворку если указан
            if framework and detected_framework != framework:
                continue
            
            test_files.append({
                "path": file_info["path"],
                "size": file_info["size"],
                "framework": detected_framework or "unknown"
            })
        
        # Группируем по директориям
        by_directory = {}
        for test_file in test_files:
            dir_name = os.path.dirname(test_file["path"]) or "."
            if dir_name not in by_directory:
                by_directory[dir_name] = []
            by_directory[dir_name].append(test_file)
        
        result = {
            "success": True,
            "total_files": len(test_files),
            "pattern": pattern,
            "by_framework": {},
            "by_directory": by_directory
        }
        
        # Подсчет по фреймворкам
        for test_file in test_files:
            fw = test_file["framework"]
            if fw not in result["by_framework"]:
                result["by_framework"][fw] = 0
            result["by_framework"][fw] += 1
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка поиска тестов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def test_single_function(
    function_name: str,
    module_path: str,
    test_cases: List[Dict[str, Any]],
    timeout: int = 30
) -> str:
    """
    Тестирует отдельную функцию с заданными тест-кейсами.
    
    Args:
        function_name: Имя функции для тестирования  
        module_path: Путь к модулю с функцией
        test_cases: Список тест-кейсов [{args: [], kwargs: {}, expected: Any}]
        timeout: Таймаут выполнения каждого теста
        
    Returns:
        Результаты тестирования функции
    """
    try:
        # Создаем временный тестовый файл
        test_content = [
            "import sys",
            "import json",
            f"sys.path.insert(0, '{os.path.dirname(module_path)}')",
            "",
            "try:",
            f"    from {Path(module_path).stem} import {function_name}",
            "except ImportError as e:",
            "    print(json.dumps({'success': False, 'error': f'Import error: {e}'}))",
            "    sys.exit(1)",
            "",
            "results = []",
            f"test_cases = {json.dumps(test_cases)}",
            "",
            "for i, test_case in enumerate(test_cases):",
            "    try:",
            f"        result = {function_name}(*test_case.get('args', []), **test_case.get('kwargs', {{}}))",
            "        expected = test_case.get('expected')",
            "        passed = result == expected if expected is not None else True",
            "        results.append({",
            "            'test_id': i,",
            "            'passed': passed,",
            "            'result': result,",
            "            'expected': expected",
            "        })",
            "    except Exception as e:",
            "        results.append({",
            "            'test_id': i,",
            "            'passed': False,",
            "            'error': str(e),",
            "            'expected': test_case.get('expected')",
            "        })",
            "",
            "print(json.dumps({",
            "    'success': True,",
            "    'function': " + json.dumps(function_name) + ",",
            "    'total_tests': len(test_cases),",
            "    'passed': sum(1 for r in results if r.get('passed')),",
            "    'results': results",
            "}))"
        ]
        
        # Записываем временный файл
        test_file = "/tmp/test_function_temp.py"
        with open(test_file, 'w') as f:
            f.write('\n'.join(test_content))
        
        # Выполняем тест
        process = await asyncio.create_subprocess_exec(
            "python3", test_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return json.dumps({
                "success": False,
                "error": f"Тест превысил таймаут ({timeout} сек)"
            })
        
        # Парсим результат
        try:
            result = json.loads(stdout.decode())
            
            # Добавляем краткую сводку
            if result.get("success"):
                total = result.get("total_tests", 0)
                passed = result.get("passed", 0)
                result["summary"] = {
                    "success_rate": round((passed / total * 100) if total > 0 else 0, 2),
                    "failed": total - passed
                }
            
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except json.JSONDecodeError:
            return json.dumps({
                "success": False,
                "error": "Ошибка парсинга результата",
                "stdout": stdout.decode()[:1000],
                "stderr": stderr.decode()[:1000]
            })
        
    except Exception as e:
        logger.error(f"Ошибка тестирования функции: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        # Удаляем временный файл
        if os.path.exists(test_file):
            os.remove(test_file)


# Экспортируем инструменты
TEST_TOOLS = [
    run_tests,
    create_test,
    analyze_test_coverage,
    find_tests,
    test_single_function
]