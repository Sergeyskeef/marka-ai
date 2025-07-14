# Исправление команд для работы из контейнера

## Обзор изменений

Все команды в документации были исправлены для выполнения из контейнера `app`, так как API доступен только внутри Docker сети.

## Основные изменения

### 1. deployment_guide.md

**Было:**
```bash
# Запуск системы
docker-compose up -d

# Проверка API
curl http://localhost:8000/health
curl http://localhost:8000/ping
```

**Стало:**
```bash
# Запуск системы
cd langchain_api
docker-compose up -d

# Проверка API (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/ping').json())"
```

### 2. api_documentation.md

**Было:**
```bash
curl http://localhost:8000/ping
curl http://localhost:8000/health
curl http://localhost:8000/metrics/summary
```

**Стало:**
```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/ping').json())"
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/metrics/summary').json())"
```

### 3. examples.md

**Добавлено предупреждение:**
```markdown
## ⚠️ Важно: Выполнение команд

**Все команды в этом документе должны выполняться из контейнера `app`:**

```bash
# Вместо curl http://localhost:8000/...
# Используйте:
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/...').json())"

# Вместо curl -X POST http://localhost:8000/...
# Используйте:
docker exec app python -c "import requests; print(requests.post('http://localhost:8000/...', json={...}).json())"
```

**Причина:** API доступен только внутри Docker сети контейнеров.
```

### 4. README.md

**Было:**
```bash
docker-compose up -d
```

**Стало:**
```bash
cd langchain_api
docker-compose up -d
```

## Причина изменений

1. **Docker сеть:** API доступен только внутри Docker сети контейнеров
2. **Правильный docker-compose:** Используется `langchain_api/docker-compose.yml` вместо корневого
3. **Безопасность:** Все проверки выполняются из изолированной среды

## Команды для диагностики

```bash
# Проверка статуса контейнеров
docker ps

# Проверка API из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/').json())"

# Просмотр логов
docker logs app --tail=50

# Переход в правильную директорию
cd langchain_api
```

## Статус

✅ **Все команды исправлены** - документация теперь корректно отражает необходимость выполнения команд из контейнера. 