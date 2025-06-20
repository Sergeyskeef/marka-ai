#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для загрузки Core Docs в SystemMemory.
"""

import os
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent))

from core.memory.system_memory_wrapper import SystemMemoryWrapper
from core.memory.memory_manager import MemoryManager

def get_weaviate_client():
    """Получение Weaviate клиента."""
    try:
        import weaviate
        from weaviate.connect import ConnectionParams
        
        # Подключение к локальному Weaviate серверу (как в init_schema.py)
        connection_params = ConnectionParams.from_params(
            http_host="weaviate",
            http_port=8080,
            http_secure=False,
            grpc_host="weaviate",
            grpc_port=50051,
            grpc_secure=False
        )
        
        client = weaviate.WeaviateClient(connection_params=connection_params)
        client.connect()
        
        print("✅ Подключение к локальному Weaviate серверу установлено")
        return client
        
    except Exception as e:
        print(f"⚠️ Не удалось подключиться к Weaviate: {e}")
        print("📝 Данные будут сохранены только в локальной памяти")
        return None

def load_core_docs_to_system_memory():
    """Загружает Core Docs в SystemMemory."""
    
    # Получаем путь к корню проекта
    project_root = Path(__file__).parent.parent
    
    print("🚀 Загрузка Core Docs в SystemMemory...")
    
    # Получаем Weaviate клиент
    weaviate_client = get_weaviate_client()
    
    # Создаем SystemMemoryWrapper с Weaviate клиентом
    wrapper = SystemMemoryWrapper(weaviate_client)
    
    if weaviate_client:
        print("✅ Подключение к Weaviate установлено")
        print("💾 Данные будут сохранены в локальную память и векторную БД")
    else:
        print("⚠️ Weaviate недоступен")
        print("💾 Данные будут сохранены только в локальную память")
    
    # Загружаем Core Docs
    core_docs_path = project_root / "core_docs"
    if core_docs_path.exists():
        print(f"📁 Найдена директория Core Docs: {core_docs_path}")
        wrapper.load_core_documents(str(core_docs_path))
        
        # Проверяем загрузку
        results = wrapper.search_by_type('core_docs', limit=100)
        print(f"✅ Загружено {len(results)} документов Core Docs")
        
        for doc in results:
            print(f"  - {doc.get('filename', 'unknown')} (приоритет: {doc.get('priority', 0)})")
        
        # Проверяем контекст идентичности
        context = wrapper.get_identity_context()
        if context['identity'].get('core'):
            print("✅ Контекст идентичности загружен")
        else:
            print("⚠️ Контекст идентичности не найден")
            
    else:
        print(f"❌ Директория Core Docs не найдена: {core_docs_path}")
        return False
    
    # Загружаем системные файлы
    project_map_path = project_root / "project_map.json"
    if project_map_path.exists():
        print(f"📄 Загружаем project_map.json...")
        wrapper.load_core_documents(str(project_root))
    
    # Получаем статус системы
    status = wrapper.get_system_status()
    print(f"📊 Статус SystemMemory:")
    print(f"  - Всего записей: {status['total_records']}")
    print(f"  - Типы памяти: {status['memory_types']}")
    
    return True

def main():
    """Основная функция."""
    print("=" * 60)
    print("🔄 ЗАГРУЗКА CORE DOCS В SYSTEMMEMORY")
    print("=" * 60)
    
    success = load_core_docs_to_system_memory()
    
    if success:
        print("\n✅ Загрузка завершена успешно!")
        print("Теперь SystemMemory содержит документы идентичности Марка")
    else:
        print("\n❌ Загрузка завершена с ошибками")
        sys.exit(1)

if __name__ == "__main__":
    main() 