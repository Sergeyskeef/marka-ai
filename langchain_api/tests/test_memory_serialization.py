#!/usr/bin/env python3
"""
Тест сериализации/десериализации памяти
"""
import requests
import json

def test_memory_serialization():
    """Тестирует сериализацию и десериализацию сложных объектов в памяти"""
    
    # Тестовые данные с вложенными структурами
    test_data = {
        "text": "test message with complex metadata",
        "metadata": {
            "tg_user": 12345,
            "chat_id": 67890,
            "tags": ["test", "demo", "complex"],
            "config": {
                "theme": "dark",
                "language": "ru",
                "features": ["memory", "tools", "planning"]
            },
            "nested": {
                "level1": {
                    "level2": {
                        "level3": ["deep", "nested", "list"]
                    }
                }
            }
        }
    }
    
    print("🔍 Тестирование сериализации/десериализации памяти...")
    print(f"📤 Отправляем данные: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
    
    try:
        # 1. Добавляем в память
        response = requests.post(
            "http://localhost:8000/memory",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 201:
            print("✅ Данные успешно добавлены в память")
            result = response.json()
            print(f"📝 ID записи: {result.get('id', 'N/A')}")
            
            # 2. Ищем в памяти
            search_response = requests.get(
                "http://localhost:8000/search",
                params={"query": "test message"}
            )
            
            if search_response.status_code == 200:
                search_results = search_response.json()
                print("✅ Поиск выполнен успешно")
                print(f"📊 Найдено записей: {len(search_results.get('results', []))}")
                
                # Проверяем, что сложные объекты десериализованы правильно
                for i, result in enumerate(search_results.get('results', [])):
                    print(f"\n🔍 Результат {i+1}:")
                    metadata = result.get('metadata', {})
                    
                    # Проверяем типы данных
                    print(f"  📋 tg_user тип: {type(metadata.get('tg_user'))} = {metadata.get('tg_user')}")
                    print(f"  📋 tags тип: {type(metadata.get('tags'))} = {metadata.get('tags')}")
                    print(f"  📋 config тип: {type(metadata.get('config'))} = {metadata.get('config')}")
                    print(f"  📋 nested тип: {type(metadata.get('nested'))} = {metadata.get('nested')}")
                    
                    # Проверяем, что это Python объекты, а не строки
                    if isinstance(metadata.get('tags'), list):
                        print("  ✅ tags - это список (правильно)")
                    else:
                        print("  ❌ tags - НЕ список (ошибка сериализации)")
                        
                    if isinstance(metadata.get('config'), dict):
                        print("  ✅ config - это словарь (правильно)")
                    else:
                        print("  ❌ config - НЕ словарь (ошибка сериализации)")
                        
                    if isinstance(metadata.get('nested'), dict):
                        print("  ✅ nested - это словарь (правильно)")
                    else:
                        print("  ❌ nested - НЕ словарь (ошибка сериализации)")
                        
            else:
                print(f"❌ Ошибка поиска: {search_response.status_code}")
                print(f"📄 Ответ: {search_response.text}")
                
        else:
            print(f"❌ Ошибка добавления в память: {response.status_code}")
            print(f"📄 Ответ: {response.text}")
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")

if __name__ == "__main__":
    test_memory_serialization() 