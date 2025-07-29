#!/usr/bin/env python3
"""
Скрипт для автоматической очистки проекта Марка v2.
Удаляет неиспользуемые файлы, отладочный код и временные файлы.
"""

import os
import sys
import shutil
import re
from pathlib import Path
from typing import List, Set

class ProjectCleaner:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.removed_files = []
        self.removed_dirs = []
        self.modified_files = []
        
    def log_action(self, action: str, path: str):
        """Логирует действие."""
        print(f"[{action}] {path}")
        
    def remove_file(self, file_path: str) -> bool:
        """Удаляет файл и логирует действие."""
        try:
            full_path = self.project_root / file_path
            if full_path.exists():
                full_path.unlink()
                self.removed_files.append(file_path)
                self.log_action("REMOVE", file_path)
                return True
        except Exception as e:
            print(f"Ошибка при удалении {file_path}: {e}")
        return False
        
    def remove_directory(self, dir_path: str) -> bool:
        """Удаляет директорию и логирует действие."""
        try:
            full_path = self.project_root / dir_path
            if full_path.exists() and full_path.is_dir():
                shutil.rmtree(full_path)
                self.removed_dirs.append(dir_path)
                self.log_action("REMOVE_DIR", dir_path)
                return True
        except Exception as e:
            print(f"Ошибка при удалении директории {dir_path}: {e}")
        return False
        
    def clean_grpc_files(self):
        """Удаляет gRPC/Protobuf файлы."""
        print("\n🧹 Удаление gRPC/Protobuf файлов...")
        
        grpc_files = [
            "tests/helloworld_pb2.py",
            "tests/helloworld_pb2_grpc.py",
            "proto/helloworld.proto"
        ]
        
        for file_path in grpc_files:
            self.remove_file(file_path)
            
        # Удаляем пустую директорию proto
        proto_dir = self.project_root / "proto"
        if proto_dir.exists() and not any(proto_dir.iterdir()):
            self.remove_directory("proto")
            
    def clean_unused_scripts(self):
        """Удаляет неиспользуемые демо-скрипты."""
        print("\n🧹 Удаление неиспользуемых демо-скриптов...")
        
        unused_scripts = [
            "scripts/test_autonomous_development_demo.py"
        ]
        
        for file_path in unused_scripts:
            self.remove_file(file_path)
            
    def clean_stub_files(self):
        """Удаляет заглушки и stub файлы."""
        print("\n🧹 Удаление заглушек и stub файлов...")
        
        stub_files = [
            "memory/multi_layer_memory.py"
        ]
        
        for file_path in stub_files:
            self.remove_file(file_path)
            
    def clean_temp_files(self):
        """Удаляет временные файлы."""
        print("\n🧹 Удаление временных файлов...")
        
        # Удаляем .log файлы
        for log_file in self.project_root.rglob("*.log"):
            if log_file.is_file():
                self.remove_file(str(log_file.relative_to(self.project_root)))
                
        # Удаляем .tmp файлы
        for tmp_file in self.project_root.rglob("*.tmp"):
            if tmp_file.is_file():
                self.remove_file(str(tmp_file.relative_to(self.project_root)))
                
        # Удаляем .cache файлы
        for cache_file in self.project_root.rglob("*.cache"):
            if cache_file.is_file():
                self.remove_file(str(cache_file.relative_to(self.project_root)))
                
        # Удаляем __pycache__ директории
        for pycache_dir in self.project_root.rglob("__pycache__"):
            if pycache_dir.is_dir():
                self.remove_directory(str(pycache_dir.relative_to(self.project_root)))
                
    def clean_debug_files(self):
        """Удаляет отладочные файлы."""
        print("\n🧹 Удаление отладочных файлов...")
        
        debug_files = [
            "analyze_project.py",
            "local_test.py"
        ]
        
        for file_path in debug_files:
            self.remove_file(file_path)
            
    def replace_print_with_logger(self, file_path: str) -> bool:
        """Заменяет print() на logger в файле."""
        try:
            full_path = self.project_root / file_path
            if not full_path.exists():
                return False
                
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Проверяем, есть ли print() в файле
            if 'print(' not in content:
                return False
                
            # Проверяем, есть ли уже logging
            has_logging = 'import logging' in content or 'from logging' in content
            has_logger = 'logger = logging.getLogger' in content
            
            # Если нет logging, добавляем
            if not has_logging:
                # Находим первое import
                import_match = re.search(r'^import\s+', content, re.MULTILINE)
                if import_match:
                    logging_import = 'import logging\n'
                    content = content[:import_match.start()] + logging_import + content[import_match.start():]
                else:
                    # Если нет импортов, добавляем в начало
                    content = 'import logging\n\n' + content
                    
            # Если нет logger, добавляем
            if not has_logger:
                # Находим подходящее место для logger (после импортов)
                lines = content.split('\n')
                logger_line = 'logger = logging.getLogger(__name__)'
                
                # Ищем место после импортов
                insert_pos = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith('import ') or line.strip().startswith('from '):
                        insert_pos = i + 1
                    elif line.strip() and not line.strip().startswith('#'):
                        break
                        
                lines.insert(insert_pos, logger_line)
                content = '\n'.join(lines)
                
            # Заменяем print() на logger.info()
            content = re.sub(r'print\((.*?)\)', r'logger.info(\1)', content)
            
            # Записываем обратно
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            self.modified_files.append(file_path)
            self.log_action("MODIFY", file_path)
            return True
            
        except Exception as e:
            print(f"Ошибка при модификации {file_path}: {e}")
            return False
            
    def clean_debug_code(self):
        """Убирает отладочный код из продакшн файлов."""
        print("\n🧹 Удаление отладочного кода...")
        
        debug_files = [
            "rag/enhanced_rag_chain.py",
            "rag/enhanced_rag_chain_tools.py",
            "core/backend_selector.py",
            "core/graphiti_config.py",
            "main.py"
        ]
        
        for file_path in debug_files:
            self.replace_print_with_logger(file_path)
            
    def clean_all(self):
        """Выполняет полную очистку проекта."""
        print("🚀 Начинаем очистку проекта Марка v2...")
        print("=" * 50)
        
        self.clean_grpc_files()
        self.clean_unused_scripts()
        self.clean_stub_files()
        self.clean_temp_files()
        self.clean_debug_files()
        self.clean_debug_code()
        
        self.print_summary()
        
    def print_summary(self):
        """Выводит сводку по очистке."""
        print("\n" + "=" * 50)
        print("📊 СВОДКА ОЧИСТКИ")
        print("=" * 50)
        
        print(f"🗑️  Удалено файлов: {len(self.removed_files)}")
        print(f"🗑️  Удалено директорий: {len(self.removed_dirs)}")
        print(f"✏️  Модифицировано файлов: {len(self.modified_files)}")
        
        if self.removed_files:
            print("\n📁 Удаленные файлы:")
            for file_path in self.removed_files:
                print(f"  - {file_path}")
                
        if self.removed_dirs:
            print("\n📁 Удаленные директории:")
            for dir_path in self.removed_dirs:
                print(f"  - {dir_path}")
                
        if self.modified_files:
            print("\n✏️  Модифицированные файлы:")
            for file_path in self.modified_files:
                print(f"  - {file_path}")
                
        print("\n✅ Очистка завершена!")
        print("\n⚠️  РЕКОМЕНДАЦИИ:")
        print("1. Проверьте, что все тесты проходят")
        print("2. Убедитесь, что приложение запускается")
        print("3. Проверьте Docker Compose на ошибки")
        print("4. Обновите документацию при необходимости")

def main():
    """Главная функция."""
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = "."
        
    cleaner = ProjectCleaner(project_root)
    
    # Проверяем, что мы в правильной директории
    if not (Path(project_root) / "main.py").exists():
        print("❌ Ошибка: main.py не найден. Убедитесь, что вы в корне проекта.")
        sys.exit(1)
        
    # Запрашиваем подтверждение
    print("⚠️  ВНИМАНИЕ: Этот скрипт удалит файлы безвозвратно!")
    print("Убедитесь, что у вас есть резервная копия проекта.")
    
    response = input("\nПродолжить очистку? (y/N): ")
    if response.lower() != 'y':
        print("❌ Очистка отменена.")
        sys.exit(0)
        
    cleaner.clean_all()

if __name__ == "__main__":
    main() 