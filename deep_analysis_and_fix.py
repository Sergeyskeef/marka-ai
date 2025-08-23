#!/usr/bin/env python3
"""
Глубокий анализ и исправление проекта Марк
"""

import os
import ast
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple
import importlib.util


class ProjectAnalyzer:
    def __init__(self, root_path: str = "/workspace"):
        self.root_path = Path(root_path)
        self.issues = []
        self.fixes = []
        
    def analyze_all(self):
        """Полный анализ проекта"""
        print("🔍 Начинаю глубокий анализ проекта...\n")
        
        # 1. Анализ структуры проекта
        self.analyze_project_structure()
        
        # 2. Анализ импортов
        self.analyze_imports()
        
        # 3. Анализ зависимостей
        self.analyze_dependencies()
        
        # 4. Анализ Docker конфигурации
        self.analyze_docker_config()
        
        # 5. Анализ Telegram бота
        self.analyze_telegram_bot()
        
        # 6. Генерация отчета
        self.generate_report()
    
    def analyze_project_structure(self):
        """Анализ структуры директорий"""
        print("📁 Анализ структуры проекта...")
        
        required_dirs = [
            "langchain_api",
            "langchain_api/app",
            "langchain_api/telegram_bot",
            "langchain_api/graphiti_service",
            "langchain_api/app/agents",
            "langchain_api/app/memory",
            "langchain_api/app/autonomy",
            "langchain_api/app/learning"
        ]
        
        for dir_path in required_dirs:
            full_path = self.root_path / dir_path
            if not full_path.exists():
                self.issues.append(f"❌ Отсутствует директория: {dir_path}")
            else:
                print(f"✅ {dir_path}")
    
    def analyze_imports(self):
        """Анализ всех импортов в проекте"""
        print("\n📦 Анализ импортов...")
        
        python_files = list(self.root_path.glob("langchain_api/**/*.py"))
        import_issues = []
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Парсим AST
                try:
                    tree = ast.parse(content)
                    imports = self._extract_imports(tree)
                    
                    # Проверяем импорты
                    for imp in imports:
                        if self._is_problematic_import(imp, file_path):
                            import_issues.append({
                                'file': str(file_path.relative_to(self.root_path)),
                                'import': imp,
                                'issue': self._get_import_issue(imp, file_path)
                            })
                            
                except SyntaxError as e:
                    self.issues.append(f"❌ Синтаксическая ошибка в {file_path}: {e}")
                    
            except Exception as e:
                self.issues.append(f"❌ Ошибка чтения {file_path}: {e}")
        
        if import_issues:
            self.issues.append(f"❌ Найдено {len(import_issues)} проблем с импортами")
            for issue in import_issues[:5]:  # Показываем первые 5
                print(f"  - {issue['file']}: {issue['import']} ({issue['issue']})")
    
    def _extract_imports(self, tree) -> List[str]:
        """Извлечь все импорты из AST"""
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                level = node.level
                if level > 0:
                    imports.append('.' * level + module)
                else:
                    imports.append(module)
        
        return imports
    
    def _is_problematic_import(self, imp: str, file_path: Path) -> bool:
        """Проверить, является ли импорт проблемным"""
        # Проблемные паттерны для telegram_bot
        if 'telegram_bot' in str(file_path):
            # В main.py не должно быть относительных импортов
            if file_path.name == 'main.py' and imp.startswith('.'):
                return True
            # В других файлах должны быть относительные импорты для внутренних модулей
            if file_path.name != 'main.py' and not imp.startswith('.') and imp in ['config', 'middleware', 'handlers', 'services']:
                return True
        
        return False
    
    def _get_import_issue(self, imp: str, file_path: Path) -> str:
        """Получить описание проблемы с импортом"""
        if 'telegram_bot' in str(file_path):
            if file_path.name == 'main.py' and imp.startswith('.'):
                return "Относительный импорт в main.py"
            if file_path.name != 'main.py' and not imp.startswith('.'):
                return "Абсолютный импорт внутреннего модуля"
        
        return "Неизвестная проблема"
    
    def analyze_dependencies(self):
        """Анализ зависимостей requirements.txt"""
        print("\n📋 Анализ зависимостей...")
        
        req_file = self.root_path / "langchain_api/requirements.txt"
        if not req_file.exists():
            self.issues.append("❌ Отсутствует requirements.txt")
            return
        
        with open(req_file, 'r') as f:
            requirements = f.read().splitlines()
        
        # Проверяем критические зависимости
        critical_deps = {
            'fastapi': None,
            'uvicorn': None,
            'openai': None,
            'neo4j': None,
            'python-telegram-bot': '21.0',
            'httpx': None,
            'redis': None,
            'graphiti-core': None
        }
        
        found_deps = {}
        for req in requirements:
            req = req.strip()
            if not req or req.startswith('#'):
                continue
            
            for dep in critical_deps:
                if req.startswith(dep):
                    found_deps[dep] = req
                    print(f"✅ {req}")
        
        # Проверяем отсутствующие
        for dep, version in critical_deps.items():
            if dep not in found_deps:
                self.issues.append(f"❌ Отсутствует зависимость: {dep}")
    
    def analyze_docker_config(self):
        """Анализ Docker конфигурации"""
        print("\n🐳 Анализ Docker конфигурации...")
        
        # Проверяем docker-compose.yml
        compose_file = self.root_path / "docker-compose.yml"
        if not compose_file.exists():
            self.issues.append("❌ Отсутствует docker-compose.yml")
            return
        
        # Проверяем Dockerfile для бота
        bot_dockerfile = self.root_path / "langchain_api/telegram_bot/Dockerfile"
        if bot_dockerfile.exists():
            with open(bot_dockerfile, 'r') as f:
                content = f.read()
            
            # Проверяем PYTHONPATH
            if 'PYTHONPATH' not in content:
                self.issues.append("❌ PYTHONPATH не установлен в Dockerfile бота")
            
            # Проверяем WORKDIR
            if 'WORKDIR /bot/langchain_api/telegram_bot' in content:
                self.fixes.append({
                    'file': 'telegram_bot/Dockerfile',
                    'issue': 'WORKDIR создает проблемы с импортами',
                    'fix': 'Изменить WORKDIR или структуру импортов'
                })
    
    def analyze_telegram_bot(self):
        """Детальный анализ Telegram бота"""
        print("\n🤖 Анализ Telegram бота...")
        
        bot_path = self.root_path / "langchain_api/telegram_bot"
        
        # Проверяем все необходимые файлы
        required_files = [
            "main.py",
            "config.py",
            "__init__.py",
            "middleware/__init__.py",
            "handlers/__init__.py",
            "services/__init__.py",
            "keyboards/__init__.py"
        ]
        
        for file_name in required_files:
            file_path = bot_path / file_name
            if not file_path.exists():
                self.issues.append(f"❌ Отсутствует файл: telegram_bot/{file_name}")
            else:
                print(f"✅ {file_name}")
        
        # Проверяем команды бота
        self._check_bot_commands()
    
    def _check_bot_commands(self):
        """Проверка обработчиков команд"""
        handlers_path = self.root_path / "langchain_api/telegram_bot/handlers"
        
        expected_handlers = {
            'start.py': ['start_command'],
            'chat.py': ['handle_text_message', 'handle_chat_mode_callback'],
            'memory.py': ['handle_memory_menu', 'handle_memory_search', 'handle_memory_add', 'handle_memory_stats']
        }
        
        for file_name, expected_funcs in expected_handlers.items():
            file_path = handlers_path / file_name
            if file_path.exists():
                with open(file_path, 'r') as f:
                    content = f.read()
                
                for func in expected_funcs:
                    if f"def {func}" not in content and f"async def {func}" not in content:
                        self.issues.append(f"❌ Отсутствует функция {func} в {file_name}")
    
    def generate_report(self):
        """Генерация отчета с исправлениями"""
        print("\n" + "="*60)
        print("📊 ОТЧЕТ ПО АНАЛИЗУ")
        print("="*60)
        
        if self.issues:
            print(f"\n❌ Найдено проблем: {len(self.issues)}")
            for issue in self.issues:
                print(f"  • {issue}")
        else:
            print("\n✅ Критических проблем не найдено!")
        
        if self.fixes:
            print(f"\n🔧 Предлагаемые исправления:")
            for fix in self.fixes:
                print(f"\n  📄 {fix['file']}:")
                print(f"     Проблема: {fix['issue']}")
                print(f"     Решение: {fix['fix']}")
        
        # Генерируем файл с исправлениями
        self._generate_fixes_script()
    
    def _generate_fixes_script(self):
        """Генерация скрипта с исправлениями"""
        fixes_content = """#!/bin/bash
# Автоматические исправления для проекта Марк

echo "🔧 Применение исправлений..."

# 1. Исправление импортов в telegram_bot
echo "📦 Исправление импортов..."

# Создаем __init__.py где необходимо
touch /workspace/langchain_api/telegram_bot/__init__.py
touch /workspace/langchain_api/telegram_bot/handlers/__init__.py
touch /workspace/langchain_api/telegram_bot/services/__init__.py
touch /workspace/langchain_api/telegram_bot/middleware/__init__.py
touch /workspace/langchain_api/telegram_bot/keyboards/__init__.py

# 2. Обновляем Dockerfile для правильных импортов
echo "🐳 Обновление Dockerfile..."
cat > /workspace/langchain_api/telegram_bot/Dockerfile.fixed << 'EOF'
FROM python:3.10-slim
WORKDIR /app

# Копируем весь проект
COPY . /app/langchain_api/

# Устанавливаем зависимости
WORKDIR /app/langchain_api
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir python-telegram-bot==21.0 aiohttp[speedups]

# Устанавливаем PYTHONPATH для корректных импортов
ENV PYTHONPATH=/app/langchain_api

# Запускаем бота из корня langchain_api
WORKDIR /app/langchain_api
CMD ["python", "-m", "telegram_bot.main"]
EOF

echo "✅ Исправления готовы!"
echo ""
echo "Для применения:"
echo "1. mv /workspace/langchain_api/telegram_bot/Dockerfile.fixed /workspace/langchain_api/telegram_bot/Dockerfile"
echo "2. docker compose build bot"
echo "3. docker compose up -d bot"
"""
        
        with open(self.root_path / "apply_fixes.sh", 'w') as f:
            f.write(fixes_content)
        
        os.chmod(self.root_path / "apply_fixes.sh", 0o755)
        print("\n✅ Создан скрипт apply_fixes.sh с исправлениями")


if __name__ == "__main__":
    analyzer = ProjectAnalyzer()
    analyzer.analyze_all()