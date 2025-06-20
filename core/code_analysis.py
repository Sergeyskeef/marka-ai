from typing import Dict, List, Any, Optional
import ast
import os
import logging
from pathlib import Path
import networkx as nx

logger = logging.getLogger(__name__)

class CodeAnalyzer:
    """
    Система для глубокого анализа кодовой базы, построения графа зависимостей
    и извлечения ключевых компонентов.
    """
    
    def __init__(self, project_path: str):
        """
        Инициализация анализатора кода.
        
        Args:
            project_path: Путь к корневой директории проекта
        """
        self.project_path = Path(project_path)
        self.total_files = 0
        self.total_classes = 0
        self.total_functions = 0
        self.total_imports = 0
        self.components = {}
        self.dependencies = {}
        self.complexity_metrics = {
            'avg_methods_per_class': 0.0,
            'avg_args_per_function': 0.0,
            'test_files': 0
        }
        self.dependency_graph = nx.DiGraph()
        self.imports: Dict[str, List[str]] = {}
        
    def analyze_codebase(self) -> Dict[str, Any]:
        """
        Анализирует всю кодовую базу.
        
        Returns:
            Dict[str, Any]: Результаты анализа
        """
        try:
            # Сканируем все Python файлы
            python_files = list(self.project_path.rglob("*.py"))
            self.total_files = len(python_files)
            
            # Анализируем каждый файл
            for file_path in python_files:
                try:
                    # Пропускаем бинарные файлы и файлы без расширения .py
                    if not str(file_path).endswith('.py'):
                        continue
                        
                    # Анализируем файл
                    file_analysis = self._analyze_file(file_path)
                    
                    # Обновляем статистику
                    self.total_classes += file_analysis['classes']
                    self.total_functions += file_analysis['functions']
                    self.total_imports += file_analysis['imports']
                    
                    # Обновляем метрики сложности
                    if file_analysis['classes'] > 0:
                        self.complexity_metrics['avg_methods_per_class'] = (
                            self.complexity_metrics['avg_methods_per_class'] * (self.total_classes - 1) +
                            file_analysis['avg_methods_per_class']
                        ) / self.total_classes
                    
                    if file_analysis['functions'] > 0:
                        self.complexity_metrics['avg_args_per_function'] = (
                            self.complexity_metrics['avg_args_per_function'] * (self.total_functions - 1) +
                            file_analysis['avg_args_per_function']
                        ) / self.total_functions
                    
                    # Считаем тестовые файлы
                    if 'test' in str(file_path).lower():
                        self.complexity_metrics['test_files'] += 1
                        
                except SyntaxError as e:
                    print(f"Пропуск файла {file_path} из-за синтаксической ошибки: {str(e)}")
                    continue
                except Exception as e:
                    print(f"Ошибка при анализе файла {file_path}: {str(e)}")
                    continue
            
            # Собираем результаты
            return {
                'total_files': self.total_files,
                'total_classes': self.total_classes,
                'total_functions': self.total_functions,
                'total_imports': self.total_imports,
                'complexity_metrics': self.complexity_metrics,
                'dependencies': {
                    'components_with_deps': len(self.dependencies),
                    'max_dependencies': max([len(deps) for deps in self.dependencies.values()], default=0)
                }
            }
            
        except Exception as e:
            print(f"Ошибка при анализе кодовой базы: {str(e)}")
            return {
                'total_files': 0,
                'total_classes': 0,
                'total_functions': 0,
                'total_imports': 0,
                'complexity_metrics': self.complexity_metrics,
                'dependencies': {
                    'components_with_deps': 0,
                    'max_dependencies': 0
                }
            }
            
    def _analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Анализирует отдельный файл.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Dict[str, Any]: Результаты анализа файла
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим AST
            tree = ast.parse(content)
            
            # Анализируем компоненты
            classes = []
            functions = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node)
                elif isinstance(node, ast.FunctionDef):
                    functions.append(node)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.append(node)
            
            # Считаем методы в классах
            methods_per_class = []
            for class_node in classes:
                methods = [node for node in class_node.body if isinstance(node, ast.FunctionDef)]
                methods_per_class.append(len(methods))
            
            # Считаем аргументы в функциях
            args_per_function = []
            for func in functions:
                args = len(func.args.args) + len(func.args.kwonlyargs)
                args_per_function.append(args)
            
            return {
                'classes': len(classes),
                'functions': len(functions),
                'imports': len(imports),
                'avg_methods_per_class': sum(methods_per_class) / len(methods_per_class) if methods_per_class else 0,
                'avg_args_per_function': sum(args_per_function) / len(args_per_function) if args_per_function else 0
            }
            
        except Exception as e:
            print(f"Ошибка при анализе файла {file_path}: {str(e)}")
            return {
                'classes': 0,
                'functions': 0,
                'imports': 0,
                'avg_methods_per_class': 0,
                'avg_args_per_function': 0
            }
        
    def _parse_ast(self, content: str) -> ast.AST:
        """
        Парсит Python код в AST.
        
        Args:
            content: Содержимое Python файла
            
        Returns:
            ast.AST: AST дерево
        """
        return ast.parse(content)
        
    def _analyze_imports(self, tree: ast.AST) -> List[str]:
        """
        Анализирует импорты в файле.
        
        Args:
            tree: AST дерево файла
            
        Returns:
            List[str]: Список импортов
        """
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports.append(name.name)
                else:
                    module = node.module if node.module else ''
                    for name in node.names:
                        imports.append(f"{module}.{name.name}")
        return imports
        
    def _analyze_components(self, tree: ast.AST) -> Dict[str, Any]:
        """
        Анализирует классы и функции в файле.
        
        Args:
            tree: AST дерево файла
            
        Returns:
            Dict[str, Any]: Информация о компонентах
        """
        components = {
            'classes': [],
            'functions': []
        }
        
        # Сначала собираем все классы и их методы
        class_nodes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_nodes[node] = set()
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        class_nodes[node].add(child)
        
        # Теперь анализируем все узлы
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                components['classes'].append({
                    'name': node.name,
                    'methods': [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                    'decorators': [d.id for d in node.decorator_list if isinstance(d, ast.Name)]
                })
            elif isinstance(node, ast.FunctionDef):
                # Проверяем, не является ли функция методом класса
                is_method = any(node in methods for methods in class_nodes.values())
                if not is_method:
                    components['functions'].append({
                        'name': node.name,
                        'args': [arg.arg for arg in node.args.args],
                        'decorators': [d.id for d in node.decorator_list if isinstance(d, ast.Name)]
                    })
                
        return components
        
    def _build_dependency_graph(self) -> None:
        """
        Строит граф зависимостей между файлами.
        """
        for file_path, imports in self.imports.items():
            for imp in imports:
                # Добавляем ребро в граф
                self.dependency_graph.add_edge(file_path, imp)
                
    def _extract_key_components(self) -> Dict[str, Any]:
        """
        Извлекает ключевые компоненты из кодовой базы.
        
        Returns:
            Dict[str, Any]: Информация о ключевых компонентах
        """
        key_components = {
            'core_modules': [],
            'services': [],
            'utils': [],
            'tests': []
        }
        
        for file_path, components in self.components.items():
            if 'core' in file_path:
                key_components['core_modules'].append({
                    'file': file_path,
                    'components': components
                })
            elif 'services' in file_path:
                key_components['services'].append({
                    'file': file_path,
                    'components': components
                })
            elif 'utils' in file_path:
                key_components['utils'].append({
                    'file': file_path,
                    'components': components
                })
            elif 'tests' in file_path:
                key_components['tests'].append({
                    'file': file_path,
                    'components': components
                })
                
        return key_components
        
    def _get_dependencies_summary(self) -> Dict[str, Any]:
        """
        Получает сводку по зависимостям.
        
        Returns:
            Dict[str, Any]: Сводка по зависимостям
        """
        return {
            'total_dependencies': len(self.dependency_graph.edges()),
            'most_dependent': list(self.dependency_graph.in_degree(nbunch=None, weight=None))[:5],
            'most_dependencies': list(self.dependency_graph.out_degree(nbunch=None, weight=None))[:5]
        }
        
    def _calculate_complexity_metrics(self) -> Dict[str, Any]:
        """
        Рассчитывает метрики сложности кода.
        
        Returns:
            Dict[str, Any]: Метрики сложности
        """
        metrics = {
            'total_classes': 0,
            'total_functions': 0,
            'average_methods_per_class': 0,
            'files_with_tests': 0
        }
        
        total_methods = 0
        for components in self.components.values():
            metrics['total_classes'] += len(components['classes'])
            metrics['total_functions'] += len(components['functions'])
            for cls in components['classes']:
                total_methods += len(cls['methods'])
                
        if metrics['total_classes'] > 0:
            metrics['average_methods_per_class'] = total_methods / metrics['total_classes']
            
        # Подсчет файлов с тестами
        metrics['files_with_tests'] = sum(1 for path in self.components.keys() if 'test' in path.lower())
        
        return metrics
        
    def generate_documentation(self) -> Dict[str, Any]:
        """
        Генерирует документацию на основе анализа кода.
        
        Returns:
            Dict[str, Any]: Сгенерированная документация
        """
        try:
            analysis = self.analyze_codebase()
            
            documentation = {
                'project_structure': {
                    'core_modules': self._document_components(analysis['components']['core_modules']),
                    'services': self._document_components(analysis['components']['services']),
                    'utils': self._document_components(analysis['components']['utils'])
                },
                'dependencies': analysis['dependencies'],
                'complexity': analysis['complexity_metrics'],
                'test_coverage': {
                    'total_tests': analysis['complexity_metrics']['files_with_tests'],
                    'test_ratio': analysis['complexity_metrics']['files_with_tests'] / analysis['total_files']
                }
            }
            
            return documentation
            
        except Exception as e:
            logger.error(f"Ошибка при генерации документации: {str(e)}")
            raise
            
    def _document_components(self, components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Генерирует документацию для компонентов.
        
        Args:
            components: Список компонентов
            
        Returns:
            List[Dict[str, Any]]: Документация компонентов
        """
        documented = []
        for component in components:
            doc = {
                'file': component['file'],
                'classes': [],
                'functions': []
            }
            
            for cls in component['components']['classes']:
                class_doc = {
                    'name': cls['name'],
                    'methods': cls['methods'],
                    'decorators': cls['decorators']
                }
                doc['classes'].append(class_doc)
                
            for func in component['components']['functions']:
                func_doc = {
                    'name': func['name'],
                    'args': func['args'],
                    'decorators': func['decorators']
                }
                doc['functions'].append(func_doc)
                
            documented.append(doc)
            
        return documented 