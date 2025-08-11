#!/usr/bin/env python3
"""
Тест hot-reload промптов
"""
import requests
import json

def test_prompt_reload():
    """Тестирует hot-reload функциональность промптов"""
    
    print("🔍 Тестирование hot-reload промптов...")
    
    # 1. Проверяем доступные режимы
    response = requests.get('http://localhost:8000/prompts/modes')
    if response.status_code == 200:
        modes = response.json()
        print(f"📋 Доступные режимы: {modes['modes']}")
        print(f"📊 Всего режимов: {modes['total']}")
        
        # 2. Проверяем, есть ли test_mode
        if 'test_mode' in modes['modes']:
            print("✅ test_mode найден в списке режимов")
            
            # 3. Тестируем новый режим
            chat_response = requests.post('http://localhost:8000/chat/ask', 
                                        json={'question': 'Привет!', 'mode': 'test_mode'})
            
            if chat_response.status_code == 200:
                answer = chat_response.json()['answer']
                print(f"🤖 Ответ в test_mode: {answer[:200]}...")
                
                if 'тестовом режиме' in answer.lower():
                    print("✅ test_mode работает корректно!")
                else:
                    print("⚠️ test_mode может не работать как ожидается")
            else:
                print(f"❌ Ошибка чата: {chat_response.status_code}")
        else:
            print("❌ test_mode не найден в списке режимов")
    else:
        print(f"❌ Ошибка получения режимов: {response.status_code}")

if __name__ == "__main__":
    test_prompt_reload() 