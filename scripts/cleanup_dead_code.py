#!/usr/bin/env python3
"""
Скрипт для безопасного удаления мертвого кода на основе анализа зависимостей
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime

def load_dependency_map(json_path):
    """Загрузить карту зависимостей"""
    with open(json_path, 'r') as f:
        return json.load(f)

def remove_files(files_to_remove, dry_run=True):
    """Удалить файлы с подсчетом статистики"""
    stats = {
        'files_removed': 0,
        'lines_removed': 0,
        'bytes_removed': 0,
        'errors': []
    }
    
    for file_path in files_to_remove:
        full_path = Path(file_path)
        
        if full_path.exists():
            try:
                # Подсчитываем статистику
                stats['bytes_removed'] += full_path.stat().st_size
                with open(full_path, 'r', encoding='utf-8') as f:
                    stats['lines_removed'] += len(f.readlines())
                
                if not dry_run:
                    # Удаляем файл
                    full_path.unlink()
                    print(f"❌ Удален: {file_path}")
                    
                    # Удаляем пустые директории
                    parent = full_path.parent
                    while parent != Path('.') and not any(parent.iterdir()):
                        print(f"📁 Удалена пустая директория: {parent}")
                        parent.rmdir()
                        parent = parent.parent
                else:
                    print(f"🔍 Будет удален: {file_path}")
                    
                stats['files_removed'] += 1
                
            except Exception as e:
                stats['errors'].append(f"{file_path}: {str(e)}")
                print(f"⚠️  Ошибка при удалении {file_path}: {e}")
        else:
            print(f"⏭️  Файл уже удален: {file_path}")
            
    return stats

def main():
    """Главная функция"""
    print("🧹 ОЧИСТКА МЕРТВОГО КОДА")
    print("=" * 50)
    
    # Загружаем карту зависимостей
    dep_map = load_dependency_map('dependency_map.json')
    
    # Список файлов для удаления (только точно мертвые)
    definitely_dead = dep_map['dead_code']['definitely_dead']
    
    # Исключаем важные файлы
    exclude_patterns = [
        '__pycache__',
        '.git',
        '.venv',
        'node_modules',
        # Важные __init__.py файлы
        'app/__init__.py',
        'telegram_bot/__init__.py',
        'tests/__init__.py',
        'scripts/__init__.py'
    ]
    
    # Фильтруем файлы
    files_to_remove = []
    for file in definitely_dead:
        if not any(pattern in file for pattern in exclude_patterns):
            # Специальная проверка для __init__.py
            if file.endswith('__init__.py'):
                # Оставляем только если это не корневые модули
                if file.count('/') > 1:  # Не в корне модуля
                    files_to_remove.append(file)
            else:
                files_to_remove.append(file)
    
    print(f"\n📊 Найдено файлов для удаления: {len(files_to_remove)}")
    print(f"📊 Из них __init__.py: {sum(1 for f in files_to_remove if f.endswith('__init__.py'))}")
    
    # Сначала делаем dry run
    print("\n🔍 РЕЖИМ ПРОВЕРКИ (dry run):")
    print("-" * 30)
    stats_dry = remove_files(files_to_remove, dry_run=True)
    
    print(f"\n📈 Статистика (прогноз):")
    print(f"   - Файлов: {stats_dry['files_removed']}")
    print(f"   - Строк кода: {stats_dry['lines_removed']:,}")
    print(f"   - Размер: {stats_dry['bytes_removed'] / 1024:.1f} KB")
    
    # Спрашиваем подтверждение
    response = input("\n⚠️  Продолжить удаление? (yes/no): ")
    
    if response.lower() == 'yes':
        print("\n🗑️  УДАЛЕНИЕ ФАЙЛОВ:")
        print("-" * 30)
        stats = remove_files(files_to_remove, dry_run=False)
        
        print(f"\n✅ ОЧИСТКА ЗАВЕРШЕНА!")
        print(f"📊 Итоговая статистика:")
        print(f"   - Удалено файлов: {stats['files_removed']}")
        print(f"   - Удалено строк кода: {stats['lines_removed']:,}")
        print(f"   - Освобождено места: {stats['bytes_removed'] / 1024:.1f} KB")
        
        if stats['errors']:
            print(f"\n⚠️  Ошибки при удалении:")
            for error in stats['errors']:
                print(f"   - {error}")
                
        # Сохраняем отчет
        report = {
            'timestamp': datetime.now().isoformat(),
            'files_removed': files_to_remove,
            'stats': stats
        }
        
        with open('cleanup_report.json', 'w') as f:
            json.dump(report, f, indent=2)
            
        print(f"\n📄 Отчет сохранен в cleanup_report.json")
    else:
        print("\n❌ Очистка отменена")

if __name__ == "__main__":
    main()