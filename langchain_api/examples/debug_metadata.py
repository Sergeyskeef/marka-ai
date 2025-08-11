#!/usr/bin/env python3
import json

import requests

# Создаем эпизод с list_field
episode_data = {
    'text': 'Debug test with list',
    'metadata': {
        'list_field': [1, 2, 3],
        'string_field': 'test string'
    }
}

print("1. Создаем эпизод...")
response = requests.post('http://localhost:8000/memory', json=episode_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Ждем
import time

time.sleep(2)

# Ищем эпизод
print("\n2. Ищем эпизод...")
response = requests.get('http://localhost:8000/search?q=Debug test with list')
print(f"Status: {response.status_code}")

data = response.json()
print(f"Total: {data['total']}")
print(f"Items: {len(data['items'])}")

if data['items']:
    item = data['items'][0]
    print(f"Text: {item['text']}")
    print(f"Metadata keys: {list(item['metadata'].keys())}")
    print(f"Full metadata: {json.dumps(item['metadata'], indent=2)}")

    # Проверяем list_field
    if 'list_field' in item['metadata']:
        print(f"list_field type: {type(item['metadata']['list_field'])}")
        print(f"list_field value: {item['metadata']['list_field']}")
    else:
        print("list_field НЕ НАЙДЕН в метаданных!")
else:
    print("Эпизоды не найдены!")
