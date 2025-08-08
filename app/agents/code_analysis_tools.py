"""
Инструменты для анализа кода и зависимостей
"""

import ast
import os
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
import importlib.util
import tokenize
import io
from collections import defaultdict, Counter

from .tools import create_openai_tool
from ..config import settings

logger = logging.getLogger(__name__)


@create_openai_tool
async def analyze_python_code(
    file_path: str,
    include_metrics: bool = True,
    include_dependencies: bool = True,
    include_complexity: bool = True
) -> str:
    """
    Анализирует Python код и возвращает детальную информацию.
    
    Args:
        file_path: Путь к Python файлу
        include_metrics: Включить метрики кода
        include_dependencies: Включить анализ зависимостей
        include_complexity: Включить анализ сложности
        
    Returns:
        Детальный анализ кода в формате JSON
    """
    try:
        from .file_tools import read_file, is_safe_path
        
        # Нормализация пути
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        # Проверка безопасности
        if not is_safe_path(file_path):
            return json.dumps({
                "success": False,
                "error": f"Небезопасный путь: {file_path}"
            })
        
        # Читаем файл
        content = await read_file(file_path)
        if content.startswith("❌"):
            return json.dumps({
                "success": False,
                "error": content
            })
        
        # Парсим AST
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as e:
            return json.dumps({
                "success": False,
                "error": f"Синтаксическая ошибка: {e}",
                "line": e.lineno,
                "offset": e.offset
            })
        
        analysis = {
            "success": True,
            "file": file_path,
            "size": len(content),
            "lines": content.count('\n') + 1
        }
        
        # Базовый анализ структуры
        structure = analyze_structure(tree)
        analysis["structure"] = structure
        
        # Метрики кода
        if include_metrics:
            metrics = calculate_metrics(content, tree)
            analysis["metrics"] = metrics
        
        # Анализ зависимостей
        if include_dependencies:
            deps = analyze_dependencies(tree)
            analysis["dependencies"] = deps
        
        # Анализ сложности
        if include_complexity:
            complexity = analyze_complexity(tree, content)
            analysis["complexity"] = complexity
        
        return json.dumps(analysis, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка анализа кода: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def analyze_structure(tree: ast.AST) -> Dict[str, Any]:
    """Анализ структуры кода"""
    structure = {
        "classes": [],
        "functions": [],
        "async_functions": [],
        "decorators": [],
        "global_vars": []
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_info = {
                "name": node.name,
                "line": node.lineno,
                "methods": [],
                "bases": [get_node_name(base) for base in node.bases],
                "decorators": [get_node_name(d) for d in node.decorator_list]
            }
            
            # Анализ методов класса
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_info = {
                        "name": item.name,
                        "line": item.lineno,
                        "async": isinstance(item, ast.AsyncFunctionDef),
                        "args": len(item.args.args),
                        "decorators": [get_node_name(d) for d in item.decorator_list]
                    }
                    class_info["methods"].append(method_info)
            
            structure["classes"].append(class_info)
            
        elif isinstance(node, ast.FunctionDef) and not is_nested(node, tree):
            func_info = {
                "name": node.name,
                "line": node.lineno,
                "args": len(node.args.args),
                "decorators": [get_node_name(d) for d in node.decorator_list],
                "docstring": ast.get_docstring(node) is not None
            }
            structure["functions"].append(func_info)
            
        elif isinstance(node, ast.AsyncFunctionDef) and not is_nested(node, tree):
            func_info = {
                "name": node.name,
                "line": node.lineno,
                "args": len(node.args.args),
                "decorators": [get_node_name(d) for d in node.decorator_list],
                "docstring": ast.get_docstring(node) is not None
            }
            structure["async_functions"].append(func_info)
            
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            # Глобальные переменные
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    structure["global_vars"].append({
                        "name": target.id,
                        "line": node.lineno,
                        "value": node.value.value if hasattr(node.value, 'value') else None
                    })
    
    return structure


def calculate_metrics(content: str, tree: ast.AST) -> Dict[str, Any]:
    """Расчет метрик кода"""
    metrics = {
        "total_lines": content.count('\n') + 1,
        "code_lines": 0,
        "comment_lines": 0,
        "blank_lines": 0,
        "docstring_lines": 0
    }
    
    # Подсчет строк
    lines = content.split('\n')
    for line in lines:
        stripped = line.strip()
        if not stripped:
            metrics["blank_lines"] += 1
        elif stripped.startswith('#'):
            metrics["comment_lines"] += 1
        else:
            metrics["code_lines"] += 1
    
    # Подсчет docstrings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node)
            if docstring:
                metrics["docstring_lines"] += docstring.count('\n') + 1
    
    # Дополнительные метрики
    metrics["functions_count"] = sum(1 for _ in ast.walk(tree) if isinstance(_, ast.FunctionDef))
    metrics["classes_count"] = sum(1 for _ in ast.walk(tree) if isinstance(_, ast.ClassDef))
    metrics["imports_count"] = sum(1 for _ in ast.walk(tree) if isinstance(_, (ast.Import, ast.ImportFrom)))
    
    return metrics


def analyze_dependencies(tree: ast.AST) -> Dict[str, Any]:
    """Анализ зависимостей"""
    dependencies = {
        "imports": [],
        "from_imports": [],
        "stdlib": [],
        "third_party": [],
        "local": []
    }
    
    stdlib_modules = get_stdlib_modules()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_info = {
                    "module": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno
                }
                dependencies["imports"].append(import_info)
                categorize_import(alias.name, dependencies, stdlib_modules)
                
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                import_info = {
                    "module": node.module,
                    "names": [(n.name, n.asname) for n in node.names],
                    "level": node.level,
                    "line": node.lineno
                }
                dependencies["from_imports"].append(import_info)
                categorize_import(node.module, dependencies, stdlib_modules)
    
    return dependencies


def analyze_complexity(tree: ast.AST, content: str) -> Dict[str, Any]:
    """Анализ сложности кода"""
    complexity = {
        "cyclomatic_complexity": {},
        "cognitive_complexity": {},
        "max_nesting": 0,
        "long_functions": [],
        "complex_functions": []
    }
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Цикломатическая сложность
            cc = calculate_cyclomatic_complexity(node)
            complexity["cyclomatic_complexity"][node.name] = cc
            
            # Проверка на длинные функции
            if hasattr(node, 'end_lineno'):
                func_lines = node.end_lineno - node.lineno
                if func_lines > 50:
                    complexity["long_functions"].append({
                        "name": node.name,
                        "lines": func_lines,
                        "start": node.lineno
                    })
            
            # Проверка на сложные функции
            if cc > 10:
                complexity["complex_functions"].append({
                    "name": node.name,
                    "complexity": cc,
                    "line": node.lineno
                })
            
            # Максимальная вложенность
            nesting = calculate_max_nesting(node)
            if nesting > complexity["max_nesting"]:
                complexity["max_nesting"] = nesting
    
    return complexity


def calculate_cyclomatic_complexity(node: ast.AST) -> int:
    """Расчет цикломатической сложности"""
    complexity = 1  # Базовая сложность
    
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
            # Учитываем elif
            if isinstance(child, ast.If) and hasattr(child, 'orelse'):
                if child.orelse and isinstance(child.orelse[0], ast.If):
                    complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += sum(1 for _ in child.ifs) + 1
    
    return complexity


def calculate_max_nesting(node: ast.AST, current_depth: int = 0) -> int:
    """Расчет максимальной вложенности"""
    max_depth = current_depth
    
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.With, ast.Try)):
            child_depth = calculate_max_nesting(child, current_depth + 1)
            max_depth = max(max_depth, child_depth)
        else:
            child_depth = calculate_max_nesting(child, current_depth)
            max_depth = max(max_depth, child_depth)
    
    return max_depth


@create_openai_tool
async def find_code_patterns(
    directory: str = ".",
    pattern: str = "",
    pattern_type: str = "ast",
    file_pattern: str = "*.py",
    max_results: int = 50
) -> str:
    """
    Ищет паттерны кода в файлах проекта.
    
    Args:
        directory: Директория для поиска
        pattern: Паттерн для поиска (зависит от pattern_type)
        pattern_type: Тип паттерна (ast, regex, function, class, decorator)
        file_pattern: Паттерн файлов
        max_results: Максимальное количество результатов
        
    Returns:
        Найденные паттерны в формате JSON
    """
    try:
        from .file_tools import list_files, read_file
        
        # Получаем список файлов
        files_json = await list_files(
            directory=directory,
            pattern=file_pattern,
            recursive=True,
            max_files=200
        )
        
        files_data = json.loads(files_json)
        if "error" in files_data:
            return json.dumps({
                "success": False,
                "error": files_data["error"]
            })
        
        results = []
        patterns_found = 0
        
        # Нормализация directory
        if not os.path.isabs(directory):
            directory = os.path.join("/workspace", directory)
        
        for file_info in files_data.get("files", []):
            if patterns_found >= max_results:
                break
                
            file_path = os.path.join(directory, file_info["path"])
            
            # Читаем файл
            content = await read_file(file_path)
            if content.startswith("❌"):
                continue
            
            # Ищем паттерны в зависимости от типа
            if pattern_type == "regex":
                matches = find_regex_patterns(content, pattern)
            elif pattern_type == "function":
                matches = find_function_patterns(content, pattern)
            elif pattern_type == "class":
                matches = find_class_patterns(content, pattern)
            elif pattern_type == "decorator":
                matches = find_decorator_patterns(content, pattern)
            elif pattern_type == "ast":
                matches = find_ast_patterns(content, pattern)
            else:
                continue
            
            if matches:
                results.append({
                    "file": file_info["path"],
                    "matches": matches[:max_results - patterns_found]
                })
                patterns_found += len(matches)
        
        return json.dumps({
            "success": True,
            "pattern": pattern,
            "pattern_type": pattern_type,
            "total_matches": patterns_found,
            "results": results
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка поиска паттернов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def find_function_patterns(content: str, pattern: str) -> List[Dict[str, Any]]:
    """Поиск функций по паттерну"""
    matches = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not pattern or pattern.lower() in node.name.lower():
                    matches.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "async": isinstance(node, ast.AsyncFunctionDef),
                        "args": [arg.arg for arg in node.args.args],
                        "decorators": [get_node_name(d) for d in node.decorator_list]
                    })
    except:
        pass
    return matches


def find_class_patterns(content: str, pattern: str) -> List[Dict[str, Any]]:
    """Поиск классов по паттерну"""
    matches = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not pattern or pattern.lower() in node.name.lower():
                    matches.append({
                        "type": "class",
                        "name": node.name,
                        "line": node.lineno,
                        "bases": [get_node_name(base) for base in node.bases],
                        "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    })
    except:
        pass
    return matches


def find_decorator_patterns(content: str, pattern: str) -> List[Dict[str, Any]]:
    """Поиск декораторов по паттерну"""
    matches = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    dec_name = get_node_name(decorator)
                    if not pattern or pattern.lower() in dec_name.lower():
                        matches.append({
                            "type": "decorator",
                            "decorator": dec_name,
                            "target": node.name,
                            "target_type": type(node).__name__,
                            "line": decorator.lineno
                        })
    except:
        pass
    return matches


@create_openai_tool
async def analyze_imports(
    directory: str = ".",
    check_unused: bool = True,
    check_circular: bool = True,
    check_missing: bool = True
) -> str:
    """
    Анализирует импорты в проекте.
    
    Args:
        directory: Директория проекта
        check_unused: Проверять неиспользуемые импорты
        check_circular: Проверять циклические импорты
        check_missing: Проверять отсутствующие модули
        
    Returns:
        Анализ импортов в формате JSON
    """
    try:
        from .file_tools import list_files, read_file
        
        # Получаем список Python файлов
        files_json = await list_files(
            directory=directory,
            pattern="*.py",
            recursive=True,
            max_files=500
        )
        
        files_data = json.loads(files_json)
        if "error" in files_data:
            return json.dumps({
                "success": False,
                "error": files_data["error"]
            })
        
        # Анализируем импорты во всех файлах
        import_graph = {}
        all_imports = defaultdict(list)
        issues = {
            "unused_imports": [],
            "circular_imports": [],
            "missing_modules": []
        }
        
        # Первый проход - собираем все импорты
        for file_info in files_data.get("files", []):
            file_path = os.path.join(directory, file_info["path"])
            content = await read_file(file_path)
            
            if content.startswith("❌"):
                continue
            
            try:
                tree = ast.parse(content)
                file_imports = extract_imports(tree)
                import_graph[file_info["path"]] = file_imports
                
                # Проверка неиспользуемых импортов
                if check_unused:
                    unused = find_unused_imports(tree, content)
                    if unused:
                        issues["unused_imports"].append({
                            "file": file_info["path"],
                            "imports": unused
                        })
                        
            except SyntaxError:
                continue
        
        # Проверка циклических импортов
        if check_circular:
            cycles = find_circular_imports(import_graph)
            if cycles:
                issues["circular_imports"] = cycles
        
        # Проверка отсутствующих модулей
        if check_missing:
            missing = find_missing_modules(import_graph)
            if missing:
                issues["missing_modules"] = missing
        
        # Статистика
        stats = {
            "total_files": len(import_graph),
            "total_imports": sum(len(imports) for imports in import_graph.values()),
            "unique_modules": len(set(sum(import_graph.values(), []))),
            "files_with_issues": len(set(
                [f["file"] for f in issues["unused_imports"]] +
                [f for cycle in issues["circular_imports"] for f in cycle] +
                [f["file"] for f in issues["missing_modules"]]
            ))
        }
        
        return json.dumps({
            "success": True,
            "stats": stats,
            "issues": issues,
            "import_graph": import_graph
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка анализа импортов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def extract_imports(tree: ast.AST) -> List[str]:
    """Извлекает все импорты из AST"""
    imports = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    
    return imports


def find_unused_imports(tree: ast.AST, content: str) -> List[str]:
    """Находит неиспользуемые импорты"""
    imported_names = set()
    used_names = set()
    
    # Собираем импортированные имена
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imported_names.add(name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imported_names.add(name)
    
    # Собираем используемые имена
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                used_names.add(node.value.id)
    
    # Находим неиспользуемые
    unused = imported_names - used_names
    
    # Фильтруем специальные случаи
    unused = [name for name in unused if not name.startswith('_')]
    
    return list(unused)


def find_circular_imports(import_graph: Dict[str, List[str]]) -> List[List[str]]:
    """Находит циклические импорты"""
    cycles = []
    visited = set()
    rec_stack = set()
    
    def dfs(module, path):
        visited.add(module)
        rec_stack.add(module)
        path.append(module)
        
        if module in import_graph:
            for imported in import_graph[module]:
                if imported in import_graph:  # Только локальные модули
                    if imported not in visited:
                        if dfs(imported, path):
                            return True
                    elif imported in rec_stack:
                        # Найден цикл
                        cycle_start = path.index(imported)
                        cycle = path[cycle_start:] + [imported]
                        if len(cycle) > 2 and cycle not in cycles:
                            cycles.append(cycle)
        
        path.pop()
        rec_stack.remove(module)
        return False
    
    for module in import_graph:
        if module not in visited:
            dfs(module, [])
    
    return cycles


@create_openai_tool
async def find_code_smells(
    file_path: str,
    check_all: bool = True
) -> str:
    """
    Находит потенциальные проблемы в коде (code smells).
    
    Args:
        file_path: Путь к файлу для анализа
        check_all: Проверять все типы проблем
        
    Returns:
        Найденные проблемы в формате JSON
    """
    try:
        from .file_tools import read_file, is_safe_path
        
        # Нормализация пути
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        # Проверка безопасности
        if not is_safe_path(file_path):
            return json.dumps({
                "success": False,
                "error": f"Небезопасный путь: {file_path}"
            })
        
        # Читаем файл
        content = await read_file(file_path)
        if content.startswith("❌"):
            return json.dumps({
                "success": False,
                "error": content
            })
        
        # Парсим AST
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return json.dumps({
                "success": False,
                "error": f"Синтаксическая ошибка: {e}"
            })
        
        smells = {
            "long_functions": find_long_functions(tree),
            "long_parameter_lists": find_long_parameter_lists(tree),
            "duplicate_code": find_duplicate_code(tree, content),
            "complex_conditions": find_complex_conditions(tree),
            "god_classes": find_god_classes(tree),
            "dead_code": find_dead_code(tree, content),
            "magic_numbers": find_magic_numbers(tree)
        }
        
        # Подсчет общего количества проблем
        total_issues = sum(len(issues) for issues in smells.values())
        
        # Рекомендации
        recommendations = generate_recommendations(smells)
        
        return json.dumps({
            "success": True,
            "file": file_path,
            "total_issues": total_issues,
            "smells": smells,
            "recommendations": recommendations
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка поиска code smells: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


def find_long_functions(tree: ast.AST) -> List[Dict[str, Any]]:
    """Находит слишком длинные функции"""
    long_functions = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, 'end_lineno'):
                length = node.end_lineno - node.lineno
                if length > 50:
                    long_functions.append({
                        "name": node.name,
                        "lines": length,
                        "start_line": node.lineno,
                        "severity": "high" if length > 100 else "medium"
                    })
    
    return long_functions


def find_long_parameter_lists(tree: ast.AST) -> List[Dict[str, Any]]:
    """Находит функции с большим количеством параметров"""
    issues = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            param_count = len(node.args.args) + len(node.args.kwonlyargs)
            if param_count > 5:
                issues.append({
                    "name": node.name,
                    "parameters": param_count,
                    "line": node.lineno,
                    "severity": "high" if param_count > 7 else "medium"
                })
    
    return issues


def find_complex_conditions(tree: ast.AST) -> List[Dict[str, Any]]:
    """Находит слишком сложные условия"""
    issues = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            complexity = calculate_condition_complexity(node.test)
            if complexity > 3:
                issues.append({
                    "line": node.lineno,
                    "complexity": complexity,
                    "severity": "high" if complexity > 5 else "medium"
                })
    
    return issues


def calculate_condition_complexity(node: ast.AST) -> int:
    """Подсчитывает сложность условия"""
    if isinstance(node, ast.BoolOp):
        return sum(calculate_condition_complexity(val) for val in node.values)
    elif isinstance(node, ast.Compare):
        return len(node.ops)
    else:
        return 1


# Вспомогательные функции
def get_node_name(node: ast.AST) -> str:
    """Получает имя узла AST"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{get_node_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return get_node_name(node.func)
    elif isinstance(node, ast.Str):
        return node.s
    elif isinstance(node, ast.Constant):
        return str(node.value)
    else:
        return type(node).__name__


def is_nested(node: ast.AST, tree: ast.AST) -> bool:
    """Проверяет, является ли узел вложенным"""
    for parent in ast.walk(tree):
        if isinstance(parent, ast.ClassDef):
            if node in ast.walk(parent) and node != parent:
                return True
    return False


def get_stdlib_modules() -> Set[str]:
    """Получает список модулей стандартной библиотеки"""
    import sys
    stdlib = set(sys.builtin_module_names)
    stdlib.update(['os', 'sys', 'json', 're', 'math', 'random', 'datetime', 
                   'collections', 'itertools', 'functools', 'typing', 'pathlib',
                   'unittest', 'logging', 'asyncio', 'threading', 'subprocess',
                   'io', 'abc', 'contextlib', 'copy', 'pickle', 'traceback',
                   'warnings', 'weakref', 'types', 'importlib', 'inspect',
                   'ast', 'tokenize', 'shutil', 'tempfile', 'glob', 'fnmatch',
                   'hashlib', 'hmac', 'secrets', 'uuid', 'platform', 'dataclasses'])
    return stdlib


def categorize_import(module: str, dependencies: Dict, stdlib_modules: Set[str]):
    """Категоризирует импорт"""
    root_module = module.split('.')[0]
    
    if root_module in stdlib_modules:
        if module not in dependencies["stdlib"]:
            dependencies["stdlib"].append(module)
    elif root_module.startswith('.') or root_module in ['app', 'core', 'utils']:
        if module not in dependencies["local"]:
            dependencies["local"].append(module)
    else:
        if module not in dependencies["third_party"]:
            dependencies["third_party"].append(module)


def find_regex_patterns(content: str, pattern: str) -> List[Dict[str, Any]]:
    """Поиск по регулярному выражению"""
    matches = []
    try:
        regex = re.compile(pattern)
        for i, line in enumerate(content.split('\n'), 1):
            for match in regex.finditer(line):
                matches.append({
                    "type": "regex",
                    "line": i,
                    "column": match.start() + 1,
                    "match": match.group(),
                    "groups": match.groups()
                })
    except re.error:
        pass
    return matches


def find_ast_patterns(content: str, pattern: str) -> List[Dict[str, Any]]:
    """Поиск AST паттернов (упрощенная версия)"""
    # Это упрощенная реализация
    # В реальности нужен более сложный матчинг AST
    matches = []
    
    try:
        tree = ast.parse(content)
        
        # Простые паттерны
        if pattern == "try_except":
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    matches.append({
                        "type": "try_except",
                        "line": node.lineno,
                        "handlers": len(node.handlers),
                        "has_else": node.orelse != [],
                        "has_finally": node.finalbody != []
                    })
                    
        elif pattern == "with_statement":
            for node in ast.walk(tree):
                if isinstance(node, ast.With):
                    matches.append({
                        "type": "with_statement",
                        "line": node.lineno,
                        "items": len(node.items)
                    })
                    
        elif pattern == "list_comprehension":
            for node in ast.walk(tree):
                if isinstance(node, ast.ListComp):
                    matches.append({
                        "type": "list_comprehension",
                        "line": node.lineno
                    })
    except:
        pass
    
    return matches


def find_duplicate_code(tree: ast.AST, content: str) -> List[Dict[str, Any]]:
    """Находит дублирующийся код (упрощенная версия)"""
    duplicates = []
    
    # Собираем все функции
    functions = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Простое сравнение по структуре
            func_str = ast.dump(node.body) if node.body else ""
            if func_str in functions:
                duplicates.append({
                    "function1": functions[func_str],
                    "function2": node.name,
                    "line": node.lineno
                })
            else:
                functions[func_str] = node.name
    
    return duplicates


def find_god_classes(tree: ast.AST) -> List[Dict[str, Any]]:
    """Находит слишком большие классы"""
    god_classes = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_count = sum(1 for n in node.body if isinstance(n, ast.FunctionDef))
            if method_count > 20:
                god_classes.append({
                    "name": node.name,
                    "methods": method_count,
                    "line": node.lineno,
                    "severity": "high" if method_count > 30 else "medium"
                })
    
    return god_classes


def find_dead_code(tree: ast.AST, content: str) -> List[Dict[str, Any]]:
    """Находит мертвый код"""
    dead_code = []
    
    # Проверяем unreachable код после return/raise
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for i, stmt in enumerate(node.body):
                if isinstance(stmt, (ast.Return, ast.Raise)):
                    if i < len(node.body) - 1:
                        dead_code.append({
                            "type": "unreachable",
                            "function": node.name,
                            "line": node.body[i + 1].lineno
                        })
    
    return dead_code


def find_magic_numbers(tree: ast.AST) -> List[Dict[str, Any]]:
    """Находит магические числа"""
    magic_numbers = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                # Исключаем общие константы
                if node.value not in (0, 1, -1, 2, 10, 100, 1000):
                    magic_numbers.append({
                        "value": node.value,
                        "line": node.lineno
                    })
    
    return magic_numbers


def find_missing_modules(import_graph: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Находит отсутствующие модули"""
    missing = []
    
    # Это упрощенная версия
    # В реальности нужно проверять существование модулей
    
    return missing


def generate_recommendations(smells: Dict[str, List]) -> List[str]:
    """Генерирует рекомендации на основе найденных проблем"""
    recommendations = []
    
    if smells["long_functions"]:
        recommendations.append("Разбейте длинные функции на более мелкие, выполняющие одну задачу")
    
    if smells["long_parameter_lists"]:
        recommendations.append("Используйте объекты конфигурации или датаклассы для группировки параметров")
    
    if smells["complex_conditions"]:
        recommendations.append("Упростите сложные условия, вынеся их в отдельные функции с понятными именами")
    
    if smells["god_classes"]:
        recommendations.append("Разделите большие классы согласно принципу единственной ответственности")
    
    if smells["magic_numbers"]:
        recommendations.append("Вынесите магические числа в именованные константы")
    
    return recommendations


# Экспортируем инструменты
CODE_ANALYSIS_TOOLS = [
    analyze_python_code,
    find_code_patterns,
    analyze_imports,
    find_code_smells
]