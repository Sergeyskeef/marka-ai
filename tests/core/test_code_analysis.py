import pytest
from pathlib import Path
import tempfile
import os
from core.code_analysis import CodeAnalyzer

@pytest.fixture
def temp_project():
    """Создает временную структуру проекта для тестирования."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем структуру директорий
        os.makedirs(os.path.join(temp_dir, 'core'))
        os.makedirs(os.path.join(temp_dir, 'services'))
        os.makedirs(os.path.join(temp_dir, 'utils'))
        os.makedirs(os.path.join(temp_dir, 'tests'))
        
        # Создаем тестовые файлы
        with open(os.path.join(temp_dir, 'core', 'test_module.py'), 'w') as f:
            f.write("""
from typing import List, Dict
import os

class TestClass:
    def __init__(self):
        self.value = 0
        
    def test_method(self, param: str) -> None:
        pass
        
def test_function(arg1: int, arg2: str) -> Dict[str, int]:
    return {'result': 42}
            """)
            
        with open(os.path.join(temp_dir, 'services', 'test_service.py'), 'w') as f:
            f.write("""
from core.test_module import TestClass

class TestService:
    def __init__(self):
        self.test_class = TestClass()
        
    def process(self, data: dict) -> dict:
        return self.test_class.test_method(str(data))
            """)
            
        yield temp_dir

@pytest.fixture
def code_analyzer(temp_project):
    """Создает экземпляр CodeAnalyzer для тестирования."""
    return CodeAnalyzer(temp_project)

def test_init(code_analyzer, temp_project):
    """Тест инициализации CodeAnalyzer."""
    assert code_analyzer.project_root == Path(temp_project)
    assert len(code_analyzer.dependency_graph.edges()) == 0
    assert len(code_analyzer.components) == 0
    assert len(code_analyzer.imports) == 0

def test_analyze_file(code_analyzer):
    """Тест анализа отдельного файла."""
    test_file = code_analyzer.project_root / 'core' / 'test_module.py'
    code_analyzer._analyze_file(test_file)
    
    assert str(test_file) in code_analyzer.components
    assert str(test_file) in code_analyzer.imports
    
    components = code_analyzer.components[str(test_file)]
    assert len(components['classes']) == 1
    assert len(components['functions']) == 1
    
    test_class = components['classes'][0]
    assert test_class['name'] == 'TestClass'
    assert 'test_method' in test_class['methods']
    
    test_function = components['functions'][0]
    assert test_function['name'] == 'test_function'
    assert 'arg1' in test_function['args']
    assert 'arg2' in test_function['args']

def test_analyze_imports(code_analyzer):
    """Тест анализа импортов."""
    test_file = code_analyzer.project_root / 'core' / 'test_module.py'
    with open(test_file, 'r') as f:
        content = f.read()
    
    imports = code_analyzer._analyze_imports(code_analyzer._parse_ast(content))
    assert 'typing.List' in imports
    assert 'typing.Dict' in imports
    assert 'os' in imports

def test_analyze_components(code_analyzer):
    """Тест анализа компонентов."""
    test_file = code_analyzer.project_root / 'core' / 'test_module.py'
    with open(test_file, 'r') as f:
        content = f.read()
    
    components = code_analyzer._analyze_components(code_analyzer._parse_ast(content))
    assert len(components['classes']) == 1
    assert len(components['functions']) == 1
    
    test_class = components['classes'][0]
    assert test_class['name'] == 'TestClass'
    assert 'test_method' in test_class['methods']
    
    test_function = components['functions'][0]
    assert test_function['name'] == 'test_function'
    assert 'arg1' in test_function['args']
    assert 'arg2' in test_function['args']

def test_build_dependency_graph(code_analyzer):
    """Тест построения графа зависимостей."""
    # Анализируем файлы
    for file_path in code_analyzer.project_root.rglob("*.py"):
        code_analyzer._analyze_file(file_path)
    
    # Строим граф
    code_analyzer._build_dependency_graph()
    
    # Проверяем зависимости
    edges = list(code_analyzer.dependency_graph.edges())
    assert len(edges) > 0
    
    # Проверяем, что сервис зависит от core модуля
    service_file = str(code_analyzer.project_root / 'services' / 'test_service.py')
    core_module = 'core.test_module'
    assert any(edge[0] == service_file and core_module in edge[1] for edge in edges)

def test_extract_key_components(code_analyzer):
    """Тест извлечения ключевых компонентов."""
    # Анализируем файлы
    for file_path in code_analyzer.project_root.rglob("*.py"):
        code_analyzer._analyze_file(file_path)
    
    components = code_analyzer._extract_key_components()
    
    assert 'core_modules' in components
    assert 'services' in components
    assert 'utils' in components
    assert 'tests' in components
    
    assert len(components['core_modules']) > 0
    assert len(components['services']) > 0

def test_get_dependencies_summary(code_analyzer):
    """Тест получения сводки по зависимостям."""
    # Анализируем файлы и строим граф
    for file_path in code_analyzer.project_root.rglob("*.py"):
        code_analyzer._analyze_file(file_path)
    code_analyzer._build_dependency_graph()
    
    summary = code_analyzer._get_dependencies_summary()
    
    assert 'total_dependencies' in summary
    assert 'most_dependent' in summary
    assert 'most_dependencies' in summary
    
    assert summary['total_dependencies'] > 0
    assert len(summary['most_dependent']) <= 5
    assert len(summary['most_dependencies']) <= 5

def test_calculate_complexity_metrics(code_analyzer):
    """Тест расчета метрик сложности."""
    # Анализируем файлы
    for file_path in code_analyzer.project_root.rglob("*.py"):
        code_analyzer._analyze_file(file_path)
    
    metrics = code_analyzer._calculate_complexity_metrics()
    
    assert 'total_classes' in metrics
    assert 'total_functions' in metrics
    assert 'average_methods_per_class' in metrics
    assert 'files_with_tests' in metrics
    
    assert metrics['total_classes'] > 0
    assert metrics['total_functions'] > 0
    assert metrics['average_methods_per_class'] >= 0

def test_generate_documentation(code_analyzer):
    """Тест генерации документации."""
    documentation = code_analyzer.generate_documentation()
    
    assert 'project_structure' in documentation
    assert 'dependencies' in documentation
    assert 'complexity' in documentation
    assert 'test_coverage' in documentation
    
    structure = documentation['project_structure']
    assert 'core_modules' in structure
    assert 'services' in structure
    assert 'utils' in structure
    
    assert 'total_tests' in documentation['test_coverage']
    assert 'test_ratio' in documentation['test_coverage']

def test_document_components(code_analyzer):
    """Тест документирования компонентов."""
    # Анализируем файлы
    for file_path in code_analyzer.project_root.rglob("*.py"):
        code_analyzer._analyze_file(file_path)
    
    components = code_analyzer._extract_key_components()
    documented = code_analyzer._document_components(components['core_modules'])
    
    assert len(documented) > 0
    for doc in documented:
        assert 'file' in doc
        assert 'classes' in doc
        assert 'functions' in doc
        
        if doc['classes']:
            class_doc = doc['classes'][0]
            assert 'name' in class_doc
            assert 'methods' in class_doc
            assert 'decorators' in class_doc
        
        if doc['functions']:
            func_doc = doc['functions'][0]
            assert 'name' in func_doc
            assert 'args' in func_doc
            assert 'decorators' in func_doc

def test_error_handling(code_analyzer):
    """Тест обработки ошибок."""
    # Тест с несуществующим файлом
    with pytest.raises(Exception):
        code_analyzer._analyze_file(Path('non_existent_file.py'))
    
    # Тест с некорректным Python кодом
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w') as f:
        f.write("invalid python code")
        f.flush()
        with pytest.raises(Exception):
            code_analyzer._analyze_file(Path(f.name)) 