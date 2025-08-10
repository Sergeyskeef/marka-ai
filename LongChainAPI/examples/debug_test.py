#!/usr/bin/env python3
import json

import requests

# Создаем эпизод точно как в тесте
episode_data = {
    "text": "Complex metadata types test",
    "metadata": {
        "string_field": "test string",
        "integer_field": 42,
        "float_field": 3.14,
        "boolean_field": True,
        "list_field": [1, 2, 3],
        "null_field": None
    }
}

print("1. Создаем эпизод как в тесте...")
response = requests.post('http://localhost:8000/memory', json=episode_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Ждем
import time

time.sleep(2)

# Ищем эпизод
print("\n2. Ищем эпизод...")
response = requests.get('http://localhost:8000/search?q=Complex metadata types')
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
