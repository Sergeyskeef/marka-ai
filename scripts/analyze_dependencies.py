#!/usr/bin/env python3
"""
Анализатор зависимостей проекта для безопасного удаления мертвого кода
"""

import ast
import os
from pathlib import Path
from collections import defaultdict
import json
from typing import Set, Dict, List, Tuple

class DependencyAnalyzer:
    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.imports = defaultdict(set)  # file -> set of imports
        self.exports = defaultdict(set)  # file -> set of exported items
        self.usage_count = defaultdict(int)  # module -> usage count
        self.file_references = defaultdict(set)  # file -> set of files that import it
        
    def analyze_file(self, filepath: Path) -> None:
        """Анализ одного Python файла"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Пропускаем пустые файлы
            if not content.strip():
                return
                
            tree = ast.parse(content)
            relative_path = str(filepath.relative_to(self.root))
            
            # Анализируем импорты
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.imports[relative_path].add(alias.name)
                        self.usage_count[alias.name] += 1
                        
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.imports[relative_path].add(node.module)
                        self.usage_count[node.module] += 1
                        
                        # Отслеживаем локальные импорты
                        if not node.module.startswith(('django', 'flask', 'fastapi')):
                            # Преобразуем модуль в путь к файлу
                            module_path = node.module.replace('.', '/') + '.py'
                            if (self.root / module_path).exists():
                                self.file_references[module_path].add(relative_path)
                            
                            # Также проверяем __init__.py
                            module_dir = node.module.replace('.', '/')
                            init_path = module_dir + '/__init__.py'
                            if (self.root / init_path).exists():
                                self.file_references[init_path].add(relative_path)
                
                # Собираем экспортируемые функции/классы
                elif isinstance(node, ast.FunctionDef):
                    if not node.name.startswith('_'):
                        self.exports[relative_path].add(node.name)
                        
                elif isinstance(node, ast.ClassDef):
                    self.exports[relative_path].add(node.name)
                    
        except Exception as e:
            print(f"⚠️  Ошибка анализа {filepath}: {e}")
            
    def find_entry_points(self) -> List[str]:
        """Найти точки входа в приложение"""
        entry_points = []
        
        # Стандартные точки входа
        standard_entries = ['main.py', 'app.py', 'telegram_bot/bot.py', 
                           'manage.py', 'wsgi.py', '__main__.py']
        
        for entry in standard_entries:
            if (self.root / entry).exists():
                entry_points.append(entry)
                
        # Также ищем файлы с if __name__ == "__main__":
        for filepath in self.root.rglob('*.py'):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    if 'if __name__ == "__main__":' in f.read():
                        relative = str(filepath.relative_to(self.root))
                        if relative not in entry_points:
                            entry_points.append(relative)
            except:
                pass
                
        return entry_points
        
    def trace_dependencies(self, start_files: List[str]) -> Set[str]:
        """Отследить все файлы, достижимые из начальных точек"""
        visited = set()
        queue = list(start_files)
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
                
            visited.add(current)
            
            # Добавляем все импорты текущего файла
            for imported in self.imports.get(current, []):
                # Преобразуем импорт в возможные пути файлов
                possible_files = [
                    imported.replace('.', '/') + '.py',
                    imported.replace('.', '/') + '/__init__.py',
                    imported + '.py'
                ]
                
                for pf in possible_files:
                    if pf not in visited and (self.root / pf).exists():
                        queue.append(pf)
                        
        return visited
        
    def find_dead_code(self) -> Dict[str, List[str]]:
        """Найти мертвый код, сгруппированный по категориям"""
        # Собираем все Python файлы
        all_files = set()
        for filepath in self.root.rglob('*.py'):
            if not any(p in str(filepath) for p in ['.venv', '__pycache__', 'node_modules', '.git']):
                relative = str(filepath.relative_to(self.root))
                all_files.add(relative)
                
        # Находим точки входа
        entry_points = self.find_entry_points()
        print(f"\n📍 Найдено точек входа: {len(entry_points)}")
        for ep in entry_points:
            print(f"   - {ep}")
            
        # Отслеживаем достижимые файлы
        reachable = self.trace_dependencies(entry_points)
        
        # Находим недостижимые файлы
        unreachable = all_files - reachable
        
        # Категоризируем мертвый код
        dead_code = {
            'definitely_dead': [],
            'possibly_dead': [],
            'test_files': [],
            'example_files': []
        }
        
        for file in sorted(unreachable):
            # Тесты отдельно
            if 'test' in file.lower():
                dead_code['test_files'].append(file)
            # Примеры отдельно
            elif 'example' in file.lower() or 'demo' in file.lower():
                dead_code['example_files'].append(file)
            # Файлы без ссылок - точно мертвые
            elif file not in self.file_references:
                dead_code['definitely_dead'].append(file)
            # Файлы с ссылками - возможно мертвые
            else:
                dead_code['possibly_dead'].append(file)
                
        return dead_code
        
    def generate_report(self) -> str:
        """Создать отчет с картой зависимостей"""
        dead_code = self.find_dead_code()
        
        # Считаем строки кода
        def count_lines(files):
            total = 0
            for file in files:
                try:
                    with open(self.root / file, 'r') as f:
                        total += len(f.readlines())
                except:
                    pass
            return total
            
        report = f"""# 📊 ОТЧЕТ АНАЛИЗА ЗАВИСИМОСТЕЙ

**Дата анализа:** {Path(__file__).stat().st_mtime}
**Корневая директория:** {self.root}

## 📈 Общая статистика

- **Всего Python файлов:** {len(self.imports) + len(dead_code['definitely_dead']) + len(dead_code['possibly_dead'])}
- **Используемых файлов:** {len(self.imports)}
- **Мертвых файлов:** {len(dead_code['definitely_dead']) + len(dead_code['possibly_dead'])}
- **Строк мертвого кода:** ~{count_lines(dead_code['definitely_dead'] + dead_code['possibly_dead'])}

## 🔴 ТОЧНО МЕРТВЫЙ КОД ({len(dead_code['definitely_dead'])} файлов)
*Эти файлы можно безопасно удалить - на них нет ссылок*

"""
        for file in sorted(dead_code['definitely_dead']):
            lines = count_lines([file])
            report += f"- `{file}` ({lines} строк)\n"
            
        report += f"""

## 🟡 ВОЗМОЖНО МЕРТВЫЙ КОД ({len(dead_code['possibly_dead'])} файлов)
*Эти файлы имеют ссылки, но не достижимы из точек входа*

"""
        for file in sorted(dead_code['possibly_dead']):
            refs = self.file_references.get(file, set())
            lines = count_lines([file])
            report += f"- `{file}` ({lines} строк) - ссылки из: {', '.join(refs)}\n"
            
        report += f"""

## 🧪 ТЕСТОВЫЕ ФАЙЛЫ ({len(dead_code['test_files'])} файлов)
*Тесты, которые возможно не работают*

"""
        for file in sorted(dead_code['test_files']):
            report += f"- `{file}`\n"
            
        # Сохраняем детальную карту в JSON
        dependency_map = {
            'entry_points': self.find_entry_points(),
            'imports': {k: list(v) for k, v in self.imports.items()},
            'exports': {k: list(v) for k, v in self.exports.items()},
            'file_references': {k: list(v) for k, v in self.file_references.items()},
            'dead_code': dead_code
        }
        
        with open(self.root / 'dependency_map.json', 'w') as f:
            json.dump(dependency_map, f, indent=2)
            
        report += """

## 💾 Сохранено

- `dependency_map.json` - полная карта зависимостей
- Используйте эту карту для безопасного удаления файлов

## ⚡ Рекомендуемые команды для очистки

```bash
# Создать backup
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz .

# Удалить точно мертвый код
"""
        
        for file in dead_code['definitely_dead'][:10]:  # Первые 10 для примера
            report += f"rm -f {file}\n"
            
        report += "# ... и остальные файлы из списка\n```"
        
        return report

def main():
    """Главная функция"""
    print("🔍 Анализ зависимостей проекта...")
    
    analyzer = DependencyAnalyzer('/workspace')
    
    # Анализируем все Python файлы
    python_files = list(Path('/workspace').rglob('*.py'))
    valid_files = [f for f in python_files if not any(
        p in str(f) for p in ['.venv', '__pycache__', 'node_modules', '.git', 'backup_']
    )]
    
    print(f"📁 Найдено {len(valid_files)} Python файлов для анализа")
    
    for filepath in valid_files:
        analyzer.analyze_file(filepath)
        
    # Генерируем отчет
    report = analyzer.generate_report()
    
    # Сохраняем отчет
    with open('/workspace/DEPENDENCY_ANALYSIS_REPORT.md', 'w') as f:
        f.write(report)
        
    print("\n✅ Анализ завершен!")
    print("📄 Отчет сохранен в DEPENDENCY_ANALYSIS_REPORT.md")
    print("📊 Карта зависимостей сохранена в dependency_map.json")

if __name__ == "__main__":
    main()