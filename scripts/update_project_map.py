#!/usr/bin/env python3
"""
Скрипт для обновления карты архитектуры проекта.
Запускается автоматически через Git hooks.
"""

import os
import sys
import subprocess
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def update_project_map():
    """Обновляет project_map.json"""
    try:
        # Запускаем генерацию карты проекта
        result = subprocess.run([
            sys.executable, "scripts/generate_project_map.py"
        ], capture_output=True, text=True, cwd="/app/langchain_api")
        
        if result.returncode == 0:
            print("✅ project_map.json успешно обновлен")
            return True
        else:
            print(f"❌ Ошибка при обновлении project_map.json: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение при обновлении project_map.json: {e}")
        return False

def update_self_map():
    """Обновляет карту Марка"""
    try:
        # Запускаем генерацию карты Марка
        result = subprocess.run([
            sys.executable, "scripts/generate_mark_self_map.py"
        ], capture_output=True, text=True, cwd="/app/langchain_api")
        
        if result.returncode == 0:
            print("✅ Карта Марка успешно обновлена")
            return True
        else:
            print(f"❌ Ошибка при обновлении карты Марка: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение при обновлении карты Марка: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Обновление карты архитектуры проекта...")
    
    # Обновляем project_map.json
    success1 = update_project_map()
    
    # Обновляем карту Марка
    success2 = update_self_map()
    
    if success1 and success2:
        print("✅ Все карты успешно обновлены")
        sys.exit(0)
    else:
        print("❌ Ошибки при обновлении карт")
        sys.exit(1) 