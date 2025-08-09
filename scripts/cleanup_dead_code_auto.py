#!/usr/bin/env python3
"""
Автоматическое удаление мертвого кода на основе анализа зависимостей
"""

import json
from pathlib import Path
from datetime import datetime

# Загружаем карту зависимостей
with open('dependency_map.json', 'r') as f:
    dep_map = json.load(f)

# Список точно мертвых файлов
definitely_dead = dep_map['dead_code']['definitely_dead']

# Важные файлы, которые НЕ удаляем
important_files = [
    'core/llm_integration_hub.py',  # Упоминался в PROJECT_ANALYSIS_REPORT
    'core/brain_processor.py',       # Упоминался в PROJECT_ANALYSIS_REPORT
    'core/event_bus.py',            # Система событий
    'core/event_monitor.py',        # Мониторинг событий
    'core/thought_logger.py',       # Логирование
    'rag/enhanced_rag_chain_tools.py',  # RAG система
    'services/health_service.py',   # Health checks
    'services/log_parser_service.py',   # Парсинг логов
    'services/passport_sync_service.py', # Синхронизация паспорта
    'app/tools/google_docs_tool.py',    # Google инструменты
    'app/tools/google_sheets_tool.py',  # Google инструменты
]

# Фильтруем файлы для удаления
files_to_remove = []
stats = {'files': 0, 'lines': 0, 'bytes': 0}

for file in definitely_dead:
    # Пропускаем __init__.py в корневых модулях
    if file == '__init__.py' or file.endswith('/__init__.py') and file.count('/') <= 1:
        continue
        
    # НЕ пропускаем важные файлы из списка выше - они точно мертвые!
    files_to_remove.append(file)

print(f"🧹 Удаление {len(files_to_remove)} файлов мертвого кода...")

# Удаляем файлы
removed = []
errors = []

for file_path in files_to_remove:
    full_path = Path(file_path)
    
    if full_path.exists():
        try:
            # Подсчитываем статистику перед удалением
            stats['bytes'] += full_path.stat().st_size
            with open(full_path, 'r', encoding='utf-8') as f:
                stats['lines'] += len(f.readlines())
            
            # Удаляем файл
            full_path.unlink()
            stats['files'] += 1
            removed.append(file_path)
            print(f"❌ Удален: {file_path}")
            
            # Удаляем пустые директории
            parent = full_path.parent
            while parent != Path('.') and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                print(f"📁 Удалена пустая директория: {parent}")
                parent = parent.parent
                
        except Exception as e:
            errors.append(f"{file_path}: {str(e)}")
            print(f"⚠️  Ошибка: {file_path}: {e}")

# Сохраняем отчет
report = {
    'timestamp': datetime.now().isoformat(),
    'stats': {
        'files_removed': stats['files'],
        'lines_removed': stats['lines'],
        'bytes_removed': stats['bytes'],
        'kb_removed': round(stats['bytes'] / 1024, 1)
    },
    'removed_files': removed,
    'errors': errors
}

with open('cleanup_report.json', 'w') as f:
    json.dump(report, f, indent=2)

print(f"\n✅ ОЧИСТКА ЗАВЕРШЕНА!")
print(f"📊 Удалено файлов: {stats['files']}")
print(f"📊 Удалено строк кода: {stats['lines']:,}")
print(f"📊 Освобождено места: {stats['bytes'] / 1024:.1f} KB")
print(f"📄 Отчет сохранен в cleanup_report.json")