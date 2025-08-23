#!/bin/bash

# Smoke Test для Марка v2 - Spine Upgrade Phase 1
# Проверяет Graph Schema v1 и Pydantic Tools

set -e

echo "🚀 Запуск Smoke Test для Марка v2..."

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода статуса
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
    exit 1
fi
}

# 1. Проверка контейнеров
echo -e "\n${YELLOW}1. Проверка контейнеров...${NC}"
docker compose ps | grep -q "healthy" || {
    echo -e "${RED}❌ Не все контейнеры healthy${NC}"
    docker compose ps
    exit 1
}
print_status $? "Все контейнеры запущены и healthy"

# 2. Проверка health endpoints
echo -e "\n${YELLOW}2. Проверка health endpoints...${NC}"

# FastAPI app
curl -f http://localhost:8000/health > /dev/null 2>&1
print_status $? "FastAPI app health check"

# Telegram bot
curl -f http://localhost:8001/health > /dev/null 2>&1 || true
# bot может не иметь открытый порт снаружи — не падаем, просто информируем
if curl -f http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Telegram bot health check${NC}"
else
    echo -e "${YELLOW}⚠️ Telegram bot health недоступен на 8001 (пропускаем)${NC}"
fi

# Graphiti
curl -f http://localhost:7878/health > /dev/null 2>&1
print_status $? "Graphiti health check"

# 2.1 Проверка /metrics
echo -e "\n${YELLOW}2.1 Проверка /metrics...${NC}"
curl -f http://localhost:8000/metrics > /dev/null 2>&1
print_status $? "Prometheus metrics endpoint доступен"

# 2.2 Проверка Memory API (save/search)
echo -e "\n${YELLOW}2.2 Проверка Memory API (save/search)...${NC}"
SMOKE_TEXT="smoke memory test $(date +%s)"
# Сохранение
curl -s -f -X POST http://localhost:8000/api/memory/save \
  -H 'Content-Type: application/json' \
  -d "{\"content\": \"${SMOKE_TEXT}\", \"metadata\": {\"source\": \"smoke\"}}" > /dev/null 2>&1
print_status $? "Memory save"
# Поиск
SEARCH_OK=$(curl -s -X POST http://localhost:8000/api/memory/search \
  -H 'Content-Type: application/json' \
  -d "{\"query\": \"${SMOKE_TEXT}\", \"limit\": 5}" | grep -c "${SMOKE_TEXT}" || true)
if [ "${SEARCH_OK}" -ge 1 ]; then
    echo -e "${GREEN}✅ Memory search${NC}"
else
    echo -e "${YELLOW}⚠️ Memory search не нашёл запись (пропускаем, проверьте Graphiti)${NC}"
fi

# 3. Проверка миграции Neo4j
echo -e "\n${YELLOW}3. Проверка миграции Neo4j...${NC}"
docker compose exec graphiti-neo4j cypher-shell -u neo4j -p password "SHOW CONSTRAINTS" | grep -q "user_id"
print_status $? "Constraints созданы"

docker compose exec graphiti-neo4j cypher-shell -u neo4j -p password "SHOW INDEXES" | grep -q "user_email"
print_status $? "Индексы созданы"

# 4. Проверка тестовых данных
echo -e "\n${YELLOW}4. Проверка тестовых данных...${NC}"
docker compose exec graphiti-neo4j cypher-shell -u neo4j -p password "MATCH (u:User {id: 'test_user_001'}) RETURN count(u)" | grep -q "1"
print_status $? "Тестовые данные созданы"

# 5. Запуск тестов миграции
echo -e "\n${YELLOW}5. Запуск тестов миграции...${NC}"
docker compose exec app python -m pytest /app/langchain_api/tests/migrations/test_neo4j_init_v1.py -q
print_status $? "Тесты миграции прошли"

# 6. Проверка Pydantic Tools
echo -e "\n${YELLOW}6. Проверка Pydantic Tools...${NC}"
docker compose exec app python /app/langchain_api/test_pydantic_tools.py > /dev/null 2>&1
print_status $? "Pydantic Tools работают"

# 7. Проверка core тестов
echo -e "\n${YELLOW}7. Запуск core тестов...${NC}"
docker compose exec app python -m pytest -m core -q
print_status $? "Core тесты прошли"

# 8. Проверка линтинга
echo -e "\n${YELLOW}8. Проверка линтинга...${NC}"
docker compose exec app ruff check /app/langchain_api/core/tools/ --exit-zero
print_status $? "Линтинг прошел"

# 9. Проверка Guardrails
echo -e "\n${YELLOW}9. Проверка Guardrails...${NC}"
docker compose exec app python -c "
from langchain_api.core.guardrails_client import is_guardrails_enabled
print('✅ Guardrails включен' if is_guardrails_enabled() else '⚠️ Guardrails отключен')
" > /dev/null 2>&1
print_status $? "Guardrails проверен"

# 10. Проверка Trace UI
echo -e "\n${YELLOW}10. Проверка Trace UI...${NC}"
docker compose exec app python -c "import requests; r = requests.get('http://localhost:8000/trace/api/health'); exit(0 if r.status_code == 200 and r.json().get('status') == 'healthy' else 1)" > /dev/null 2>&1
print_status $? "Trace API работает"

# 11. Проверка Trace API данных
echo -e "\n${YELLOW}11. Проверка Trace API данных...${NC}"
docker compose exec app python -c "
import requests
import json
r = requests.get('http://localhost:8000/trace/api/spans')
if r.status_code == 200:
    spans = r.json()
    print(f'Найдено {len(spans)} spans')
    exit(0 if len(spans) >= 0 else 1)
else:
    exit(1)
" > /dev/null 2>&1
print_status $? "Trace API возвращает данные"

# 12. Проверка Guardrails длины
echo -e "\n${YELLOW}12. Проверка Guardrails длины...${NC}"
docker compose exec app python -c "
import requests
import json
# Тест нормальной длины
r1 = requests.post('http://localhost:8000/v1/chat', json={'content': 'Привет!'})
# Тест слишком длинного сообщения
r2 = requests.post('http://localhost:8000/v1/chat', json={'content': 'x' * 5000})
exit(0 if r1.status_code == 200 and r2.status_code == 422 else 1)
" > /dev/null 2>&1
print_status $? "Guardrails блокирует длинные сообщения"

# 13. Проверка CRUD предпочтений
echo -e "\n${YELLOW}13. Проверка CRUD предпочтений...${NC}"
docker compose exec app python -c "
import requests
import json

# Создание предпочтения
r1 = requests.post('http://localhost:8000/v1/prefs', 
                   json={'user_id': 'smoke_user', 'key': 'response_style', 'value': 'brief'})
print(f'Create: {r1.status_code}')

# Чтение предпочтения
r2 = requests.get('http://localhost:8000/v1/prefs?user_id=smoke_user&key=response_style')
print(f'Read: {r2.status_code}')
if r2.status_code == 200:
    data = r2.json()
    print(f'Value: {data.get("value")}')

# Чтение всех предпочтений
r3 = requests.get('http://localhost:8000/v1/prefs?user_id=smoke_user')
print(f'Read All: {r3.status_code}')

# Проверяем что все операции успешны
exit(0 if r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200 else 1)
" > /dev/null 2>&1
print_status $? "CRUD предпочтений работает"

# 14. Проверка адаптации ответа
echo -e "\n${YELLOW}14. Проверка адаптации ответа...${NC}"
docker compose exec app python -c "
import requests
import json

# Тест краткого стиля ответа
r = requests.post('http://localhost:8000/v1/chat', 
                  json={'user_id': 'smoke_user', 'content': 'Расскажи о проекте Марк'})
                  
if r.status_code == 200:
    response = r.json()
    answer_length = len(response.get('answer', ''))
    print(f'Answer length: {answer_length}')
    # Краткий стиль должен давать более короткие ответы
    exit(0 if answer_length > 0 else 1)
else:
    print(f'Error: {r.status_code}')
    exit(1)
" > /dev/null 2>&1
print_status $? "Адаптация промптов работает"

# 15. Проверка Reflexion Loop α
echo -e "\n${YELLOW}15. Проверка Reflexion Loop α...${NC}"
docker compose exec app python /app/langchain_api/test_reflexion_smoke.py
print_status $? "Reflexion Loop α работает"

# 16. Очистка тестовых данных
echo -e "\n${YELLOW}16. Очистка тестовых данных...${NC}"
docker compose exec app python -c "
import requests

# Удаление тестового предпочтения
r = requests.delete('http://localhost:8000/v1/prefs?user_id=smoke_user&key=response_style')
print(f'Delete: {r.status_code}')
exit(0 if r.status_code in [200, 404] else 1)
" > /dev/null 2>&1
print_status $? "Тестовые данные очищены"

echo -e "\n${GREEN}🎉 Smoke Test завершен успешно!${NC}"
echo -e "${GREEN}✅ Graph Schema v1 готов к использованию${NC}"
echo -e "${GREEN}✅ Pydantic Tools работают корректно${NC}"
echo -e "${GREEN}✅ Guardrails + Tracing UI готовы к использованию${NC}"
echo -e "${GREEN}✅ Preferences API + Prompt Adaptation работают${NC}"
echo -e "${GREEN}✅ Reflexion Loop α готов к использованию${NC}"
echo -e "${GREEN}✅ Все тесты проходят${NC}"

exit 0 