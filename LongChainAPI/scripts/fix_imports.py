#!/usr/bin/env python3
"""
Скрипт для замены импортов langchain_api на относительные
"""

import os
import re
import sys
from pathlib import Path

# Маппинг старых импортов на новые
IMPORT_MAPPING = {
    # Core modules
    'from core.memory.memory_manager import': 'from core.memory.memory_manager import',
    'from core.memory.memory_manager import': 'from core.memory.memory_manager import',
    'from core.': 'from core.',
    'from app.': 'from app.',
    'from sandbox.': 'from sandbox.',
    'from scripts.': 'from scripts.',
    'from tests.': 'from tests.',
    'from utils.': 'from utils.',
    'from routers.': 'from routers.',
    'from routes.': 'from routes.',
    'from services.': 'from services.',
    'from middlewares.': 'from middlewares.',
    'from rag.': 'from rag.',
    'from memory.': 'from memory.',
    
    # Main module
    'from main import': 'from main import',
    'import ': 'import ',
    'from .': 'from .',
}

# Специальные случаи для telegram_bot
TELEGRAM_BOT_MAPPING = {
    'from .telegram_bot.': 'from .',
    'import telegram_bot.': 'import .',
}


def fix_imports_in_file(filepath: Path, dry_run: bool = False):
    """Исправить импорты в одном файле"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes_made = []
        
        # Определяем маппинг в зависимости от пути файла
        if 'telegram_bot' in str(filepath):
            mapping = {**IMPORT_MAPPING, **TELEGRAM_BOT_MAPPING}
        else:
            mapping = IMPORT_MAPPING
        
        # Применяем замены
        for old_import, new_import in mapping.items():
            if old_import in content:
                count = content.count(old_import)
                content = content.replace(old_import, new_import)
                changes_made.append(f"  {old_import} -> {new_import} ({count} раз)")
        
        # Если есть изменения
        if content != original_content:
            print(f"\n📝 {filepath}")
            for change in changes_made:
                print(change)
            
            if not dry_run:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print("  ✅ Сохранено")
            else:
                print("  🔍 Dry run - изменения не сохранены")
            
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Ошибка в {filepath}: {e}")
        return False


def main():
    """Основная функция"""
    dry_run = '--dry-run' in sys.argv
    
    if dry_run:
        print("🔍 DRY RUN MODE - изменения не будут сохранены\n")
    
    # Находим все Python файлы
    workspace = Path('/workspace')
    python_files = []
    
    for root, dirs, files in os.walk(workspace):
        # Пропускаем ненужные директории
        if any(skip in root for skip in ['__pycache__', 'backup', '.git', 'venv']):
            continue
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(Path(root) / file)
    
    print(f"🔍 Найдено {len(python_files)} Python файлов\n")
    
    # Обрабатываем файлы
    fixed_count = 0
    for filepath in sorted(python_files):
        if fix_imports_in_file(filepath, dry_run):
            fixed_count += 1
    
    print(f"\n{'='*50}")
    print(f"✅ Обработано файлов: {fixed_count}/{len(python_files)}")
    
    if dry_run:
        print("\n⚠️  Для применения изменений запустите без --dry-run")


if __name__ == '__main__':
    main()