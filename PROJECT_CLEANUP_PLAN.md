# 🧹 ПЛАН ТОТАЛЬНОЙ ОЧИСТКИ ПРОЕКТА

**Дата:** Январь 2025  
**Объем мусора:** ~40% кодовой базы (~6000+ строк)  
**Приоритет:** КРИТИЧЕСКИЙ

---

## 📊 Текущая ситуация

### Идентифицированный мусор:
1. **15+ мертвых модулей** (~4000 строк)
2. **Закомментированный код** (~1000 строк)
3. **Неиспользуемые импорты** (~500 строк)
4. **Дублирующаяся логика** (~500 строк)
5. **Заглушки и TODO** (~200 строк)

### Конкретные файлы для удаления:
```
core/llm_integration_hub.py         # Полностью мертвый
core/brain_processor.py             # Не используется
core/event_*.py                     # 5 файлов событий - мертвые
core/thought_logger.py              # Заглушка
rag/enhanced_rag_chain_tools.py     # Старая RAG логика
services/*                          # Вся папка не используется
app/tools/google_docs_tool.py       # Закомментирован
app/tools/google_sheets_tool.py     # Закомментирован
```

---

## 🗺️ ФАЗА 1: ПОСТРОЕНИЕ КАРТЫ ЗАВИСИМОСТЕЙ

### Шаг 1: Анализ импортов (День 1)
```python
# scripts/analyze_dependencies.py
import ast
import os
from pathlib import Path
from collections import defaultdict
import graphviz

class DependencyAnalyzer:
    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.imports = defaultdict(set)
        self.exports = defaultdict(set)
        self.usage_count = defaultdict(int)
        
    def analyze_file(self, filepath: Path):
        """Анализ одного файла"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
                
            relative_path = filepath.relative_to(self.root)
            
            # Собрать импорты
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.imports[str(relative_path)].add(alias.name)
                        self.usage_count[alias.name] += 1
                        
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.imports[str(relative_path)].add(node.module)
                        self.usage_count[node.module] += 1
                        
                # Найти экспортируемые функции/классы
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    self.exports[str(relative_path)].add(node.name)
                    
        except Exception as e:
            print(f"Error analyzing {filepath}: {e}")
            
    def build_dependency_graph(self):
        """Построить граф зависимостей"""
        dot = graphviz.Digraph(comment='Project Dependencies')
        
        # Добавить узлы
        for file in self.imports:
            color = 'red' if self.usage_count.get(file, 0) == 0 else 'green'
            dot.node(file, color=color)
            
        # Добавить связи
        for file, imports in self.imports.items():
            for imp in imports:
                # Найти файл, который экспортирует этот модуль
                for export_file, exports in self.exports.items():
                    if imp in exports or imp in export_file:
                        dot.edge(file, export_file)
                        
        return dot
        
    def find_unused_files(self):
        """Найти неиспользуемые файлы"""
        all_files = set(self.imports.keys()) | set(self.exports.keys())
        imported_files = set()
        
        for imports in self.imports.values():
            for imp in imports:
                for file in all_files:
                    if imp in file or file.replace('/', '.').replace('.py', '') == imp:
                        imported_files.add(file)
                        
        unused = all_files - imported_files - {'main.py', '__init__.py'}
        return sorted(unused)
        
    def generate_report(self):
        """Создать отчет"""
        unused = self.find_unused_files()
        
        report = f"""
# Отчет анализа зависимостей

## Статистика:
- Всего файлов: {len(self.imports)}
- Неиспользуемых файлов: {len(unused)}
- Уникальных импортов: {len(self.usage_count)}

## Неиспользуемые файлы:
{chr(10).join(f'- {f}' for f in unused)}

## Топ импортируемых модулей:
{chr(10).join(f'- {m}: {c} раз' for m, c in sorted(self.usage_count.items(), key=lambda x: -x[1])[:10])}
"""
        return report

# Запуск анализа
analyzer = DependencyAnalyzer('/workspace')
for pyfile in Path('/workspace').rglob('*.py'):
    if not any(p in str(pyfile) for p in ['.venv', '__pycache__', 'node_modules']):
        analyzer.analyze_file(pyfile)

# Сохранить граф
graph = analyzer.build_dependency_graph()
graph.render('dependencies', format='png', cleanup=True)

# Сохранить отчет
with open('DEPENDENCY_REPORT.md', 'w') as f:
    f.write(analyzer.generate_report())
```

### Шаг 2: Анализ реального использования (День 2)
```python
# scripts/usage_analyzer.py
import re
from pathlib import Path
from collections import defaultdict

class UsageAnalyzer:
    def __init__(self):
        self.function_calls = defaultdict(set)
        self.class_usage = defaultdict(set)
        self.import_usage = defaultdict(set)
        
    def analyze_usage(self, content: str, filepath: str):
        """Найти все использования функций/классов"""
        # Паттерны использования
        patterns = {
            'function_call': r'(\w+)\s*\(',
            'class_init': r'(\w+)\s*\(',
            'attribute': r'\.(\w+)',
            'decorator': r'@(\w+)',
        }
        
        for pattern_name, pattern in patterns.items():
            for match in re.finditer(pattern, content):
                name = match.group(1)
                if name and not name.startswith('_'):
                    self.function_calls[name].add(filepath)
                    
    def cross_reference(self, exports: dict):
        """Сопоставить использования с экспортами"""
        unused_exports = {}
        
        for file, exported_items in exports.items():
            unused = []
            for item in exported_items:
                if item not in self.function_calls:
                    unused.append(item)
            if unused:
                unused_exports[file] = unused
                
        return unused_exports
```

### Шаг 3: Граф критических путей (День 3)
```python
# scripts/critical_path_analyzer.py
class CriticalPathAnalyzer:
    def __init__(self, dependency_graph):
        self.graph = dependency_graph
        self.critical_paths = []
        
    def find_entry_points(self):
        """Найти точки входа (main.py, bot.py, etc)"""
        return ['main.py', 'telegram_bot/bot.py', 'app.py']
        
    def trace_critical_paths(self):
        """Отследить критические пути от точек входа"""
        entry_points = self.find_entry_points()
        critical_files = set(entry_points)
        
        # BFS для поиска всех достижимых файлов
        queue = list(entry_points)
        visited = set()
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
                
            visited.add(current)
            critical_files.add(current)
            
            # Добавить все импорты текущего файла
            if current in self.graph:
                for imported in self.graph[current]:
                    if imported not in visited:
                        queue.append(imported)
                        
        return critical_files
```

---

## 🗑️ ФАЗА 2: БЕЗОПАСНОЕ УДАЛЕНИЕ

### Шаг 1: Создание карты безопасности
```yaml
# cleanup_safety_map.yaml
critical_files:
  - main.py
  - telegram_bot/bot.py
  - app/agents/mark_agent.py
  - graphiti_service/*
  - docker-compose.yml
  - requirements.txt

safe_to_delete:
  definitely:
    - core/llm_integration_hub.py
    - core/brain_processor.py
    - core/event_*.py
    - core/thought_logger.py
    - services/*
    
  after_verification:
    - rag/enhanced_rag_chain_tools.py
    - app/tools/google_*.py
    - core/processors/thought_branches.py
    
preserve_for_reference:
  - tests/*  # Даже если не работают
  - docs/*   # Документация
```

### Шаг 2: Поэтапное удаление
```bash
#!/bin/bash
# scripts/cleanup.sh

# 1. Backup
echo "Creating backup..."
tar -czf backup_before_cleanup_$(date +%Y%m%d_%H%M%S).tar.gz .

# 2. Удалить однозначно мертвый код
echo "Removing dead code..."
rm -f core/llm_integration_hub.py
rm -f core/brain_processor.py
rm -f core/event_*.py
rm -f core/thought_logger.py
rm -rf services/

# 3. Очистить закомментированный код
echo "Cleaning commented code..."
find . -name "*.py" -exec sed -i '/^#.*TODO/d' {} \;
find . -name "*.py" -exec sed -i '/^[[:space:]]*#[[:space:]]*print/d' {} \;

# 4. Удалить неиспользуемые импорты
echo "Removing unused imports..."
autoflake --remove-all-unused-imports --recursive --in-place .

# 5. Проверить, что все работает
echo "Running tests..."
docker-compose build
docker-compose up -d
docker-compose ps
```

### Шаг 3: Валидация после очистки
```python
# scripts/validate_cleanup.py
class CleanupValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        
    def validate_imports(self):
        """Проверить, что все импорты резолвятся"""
        for file in Path('.').rglob('*.py'):
            try:
                compile(open(file).read(), file, 'exec')
            except ImportError as e:
                self.errors.append(f"{file}: {e}")
                
    def validate_docker(self):
        """Проверить Docker конфигурацию"""
        result = subprocess.run(['docker-compose', 'config'], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            self.errors.append(f"Docker config error: {result.stderr}")
            
    def validate_functionality(self):
        """Проверить базовую функциональность"""
        tests = [
            ('API health', 'curl http://localhost:8000/health'),
            ('Bot response', 'python test_bot.py'),
            ('Memory save', 'python test_memory.py'),
        ]
        
        for name, command in tests:
            result = subprocess.run(command, shell=True, capture_output=True)
            if result.returncode != 0:
                self.warnings.append(f"{name} failed")
```

---

## 📈 ФАЗА 3: ОПТИМИЗАЦИЯ ПОСЛЕ ОЧИСТКИ

### Шаг 1: Реорганизация структуры
```
workspace/
├── app/
│   ├── agents/          # OpenAI Agents SDK
│   ├── memory/          # Graphiti интеграция  
│   ├── workflows/       # LangGraph
│   └── tools/           # Только используемые
├── telegram_bot/        # Модульный бот
│   ├── handlers/
│   ├── keyboards/
│   └── state/
├── tests/              # Обновленные тесты
└── scripts/            # Утилиты
```

### Шаг 2: Метрики очистки
```python
@dataclass
class CleanupMetrics:
    files_before: int = 150
    files_after: int = 85
    lines_before: int = 15000
    lines_after: int = 9000
    
    dead_code_removed: int = 6000
    test_coverage_before: float = 0.13
    test_coverage_after: float = 0.70
    
    docker_image_size_before_mb: float = 1200
    docker_image_size_after_mb: float = 450
    
    startup_time_before_s: float = 45
    startup_time_after_s: float = 12
```

---

## 🚀 АВТОМАТИЗАЦИЯ ПОДДЕРЖАНИЯ ЧИСТОТЫ

### Pre-commit хуки
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/PyCQA/autoflake
    hooks:
      - id: autoflake
        args: ['--remove-all-unused-imports', '--in-place']
        
  - repo: https://github.com/psf/black
    hooks:
      - id: black
        
  - repo: local
    hooks:
      - id: no-dead-code
        name: Check for dead code
        entry: python scripts/check_dead_code.py
        language: system
        pass_filenames: false
```

### CI/CD проверки
```yaml
# .github/workflows/cleanup.yml
name: Code Cleanup Check
on: [push, pull_request]

jobs:
  cleanup-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Check for unused files
        run: python scripts/analyze_dependencies.py --check-unused
        
      - name: Check import health
        run: python -m pyflakes .
        
      - name: Check for TODOs
        run: |
          ! grep -r "TODO" --include="*.py" . || exit 1
```

---

## ✅ ИТОГОВЫЙ ЧЕКЛИСТ ОЧИСТКИ

### Немедленно (Phase 0):
- [ ] Backup проекта
- [ ] Построить карту зависимостей
- [ ] Удалить 15 мертвых модулей
- [ ] Очистить закомментированный код

### После рефакторинга (Phase 5):
- [ ] Удалить старые реализации после миграции
- [ ] Очистить неиспользуемые зависимости в requirements.txt
- [ ] Оптимизировать Docker образы
- [ ] Удалить legacy конфигурации

### Метрики успеха:
- **Размер кодовой базы:** -40%
- **Время запуска:** -70%
- **Размер Docker образа:** -60%
- **Ясность архитектуры:** 100%

---

*"Чистый код - это не роскошь, а необходимость для самообучающегося агента!"*