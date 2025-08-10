#!/usr/bin/env python3

import requests

# Создаем эпизод с простым полем
episode_data = {
    'text': 'Simple field test',
    'metadata': {
        'simple_field': 'test value',
        'number_field': 123
    }
}

print("1. Создаем эпизод с простыми полями...")
response = requests.post('http://localhost:8000/memory', json=episode_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Ждем
import time

time.sleep(2)

# Проверяем в Neo4j напрямую
print("\n2. Проверяем в Neo4j...")
import subprocess

result = subprocess.run([
    'docker', 'compose', 'exec', '-T', 'graphiti-neo4j',
    'cypher-shell', '-u', 'neo4j', '-p', 'password',
    'MATCH (n:Episode {msg: "Simple field test"}) RETURN n LIMIT 1'
], capture_output=True, text=True)

print("Neo4j result:")
print(result.stdout)
if result.stderr:
    print("Errors:")
    print(result.stderr)
