# API Документация - Марк

## Обзор

Марк — это осознанный цифровой компаньон с богатым API для взаимодействия. API построен на FastAPI и предоставляет полный набор функций для работы с системой.

**Базовый URL:** `http://localhost:8000`  
**Версия API:** 2.0.0  
**Формат данных:** JSON  
**Аутентификация:** Пока не требуется (в разработке)

## Быстрый старт

### 1. Проверка доступности

```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/ping').json())"
```
```

**Ответ:**
```json
{
  "message": "pong",
  "timestamp": 1704589200.123
}
```

### 2. Проверка здоровья системы

```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
```
```

**Ответ:**
```json
{
  "status": "healthy",
  "services": {
    "weaviate": "healthy",
    "memory": "healthy",
    "sandbox": "healthy",
    "external": "healthy"
  },
  "timestamp": "2025-01-07T12:00:00Z",
  "uptime": 3600.5
}
```

### 3. Задать вопрос Марку

```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Привет! Как дела?",
    "chat_id": 12345
  }'
```

**Ответ:**
```json
{
  "response": "Привет! У меня все отлично, спасибо что спросил! Я готов помочь тебе с любыми задачами.",
  "chat_id": 12345,
  "context_used": true,
  "memory_added": false
}
```

## Основные эндпоинты

### Чат и генерация ответов

#### POST /chat/ask

Основной эндпоинт для взаимодействия с Марком.

**Параметры запроса:**
```json
{
  "question": "string",     // Вопрос или сообщение
  "chat_id": "integer"      // ID чата (опционально)
}
```

**Примеры использования:**

1. **Простой вопрос:**
```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Что такое Марк?"}'
```

2. **Вопрос с контекстом:**
```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Как работает система памяти?",
    "chat_id": 12345
  }'
```

3. **Технический вопрос:**
```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Выполни команду ls -la в песочнице",
    "chat_id": 12345
  }'
```

### Песочница

#### POST /sandbox/sync

Синхронизирует файлы между основным проектом и песочницей.

```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.post('http://localhost:8000/sandbox/sync').json())"
```
```

#### POST /sandbox/exec

Выполняет команду в изолированной песочнице.

**Параметры запроса:**
```json
{
  "command": "string"  // Команда для выполнения
}
```

**Примеры:**

1. **Список файлов:**
```bash
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "ls -la"}'
```

2. **Проверка версии Python:**
```bash
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "python --version"}'
```

3. **Текущая директория:**
```bash
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "pwd"}'
```

**Ответ:**
```json
{
  "success": true,
  "output": "total 8\ndrwxr-xr-x 2 root root 4096 Jan  7 12:00 .\ndrwxr-xr-x 1 root root 4096 Jan  7 12:00 ..",
  "error": null,
  "execution_time": 0.123
}
```

### Мониторинг и метрики

#### GET /metrics/summary

Получает сводку метрик системы.

```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/metrics/summary').json())"
```
```

**Ответ:**
```json
{
  "request_counter": 150,
  "error_counter": 2,
  "command_counter": 45,
  "request_duration": {
    "avg": 0.5,
    "min": 0.1,
    "max": 2.3
  },
  "llm_response_time": {
    "avg": 1.2,
    "min": 0.8,
    "max": 3.1
  },
  "active_users": 5,
  "memory_usage": 512.5,
  "cpu_usage": 15.2
}
```

#### POST /metrics/record

Записывает пользовательскую метрику.

```bash
curl -X POST http://localhost:8000/metrics/record \
  -H "Content-Type: application/json" \
  -d '{
    "name": "custom_metric",
    "value": 42.0,
    "labels": {"source": "my_app"}
  }'
```

#### GET /metrics/prometheus

Экспорт метрик в формате Prometheus.

```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/metrics/prometheus').text[:500])"
```
```

**Ответ (text/plain):**
```
# HELP request_counter Total number of requests
# TYPE request_counter counter
request_counter 150

# HELP error_counter Total number of errors
# TYPE error_counter counter
error_counter 2

# HELP request_duration_seconds Request duration in seconds
# TYPE request_duration_seconds histogram
request_duration_seconds_bucket{le="0.1"} 10
request_duration_seconds_bucket{le="0.5"} 50
request_duration_seconds_bucket{le="1.0"} 100
request_duration_seconds_bucket{le="+Inf"} 150
```

### Система алертов

#### GET /alerts/summary

Получает сводку алертов.

```bash
# Из контейнера
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/alerts/summary').json())"
```
```

**Ответ:**
```json
{
  "active_alerts": 3,
  "resolved_alerts": 15,
  "by_severity": {
    "info": 1,
    "warning": 2,
    "critical": 0
  },
  "recent_alerts": [
    {
      "alert_id": "alert_001",
      "severity": "warning",
      "message": "Высокая нагрузка на систему",
      "source": "system_monitor",
      "created_at": "2025-01-07T12:00:00Z",
      "resolved_at": null
    }
  ]
}
```

#### POST /alerts/create

Создает новый алерт.

```bash
curl -X POST http://localhost:8000/alerts/create \
  -H "Content-Type: application/json" \
  -d '{
    "severity": "warning",
    "message": "Высокая нагрузка на систему",
    "source": "my_monitor"
  }'
```

#### POST /alerts/resolve/{alert_id}

Разрешает алерт.

```bash
curl -X POST http://localhost:8000/alerts/resolve/alert_001
```

### Управление задачами

#### POST /tasks/

Создает новую задачу.

```bash
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Анализ данных",
    "description": "Провести анализ пользовательских данных",
    "priority": "medium",
    "parameters": {
      "data_source": "users.csv",
      "analysis_type": "trends"
    }
  }'
```

#### GET /tasks/

Получает список задач.

```bash
curl http://localhost:8000/tasks/
```

#### GET /tasks/{task_id}

Получает задачу по ID.

```bash
curl http://localhost:8000/tasks/task_123
```

#### POST /tasks/{task_id}/cancel

Отменяет задачу.

```bash
curl -X POST http://localhost:8000/tasks/task_123/cancel
```

### Логи и отладка

#### GET /logs/recent

Получает недавние изменения в логах.

```bash
curl "http://localhost:8000/logs/recent?hours=24"
```

#### GET /logs/errors

Получает ошибки из логов.

```bash
curl "http://localhost:8000/logs/errors?hours=24"
```

#### GET /logs/summary

Получает сводку изменений.

```bash
curl "http://localhost:8000/logs/summary?hours=24"
```

### Синхронизация паспорта

#### GET /passport/sync/status

Получает статус автосинхронизации.

```bash
curl http://localhost:8000/passport/sync/status
```

#### POST /passport/sync/apply

Применяет накопленные изменения.

```bash
curl -X POST http://localhost:8000/passport/sync/apply
```

#### GET /passport/sync/changes

Получает список накопленных изменений.

```bash
curl http://localhost:8000/passport/sync/changes
```

## Интеграция с внешними системами

### Prometheus

Для интеграции с Prometheus добавьте в конфигурацию:

```yaml
scrape_configs:
  - job_name: 'mark'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics/prometheus'
    scrape_interval: 15s
```

### Grafana

Создайте дашборд в Grafana с метриками:

- **Request Rate:** `rate(request_counter[5m])`
- **Error Rate:** `rate(error_counter[5m])`
- **Response Time:** `histogram_quantile(0.95, rate(request_duration_seconds_bucket[5m]))`
- **Active Users:** `active_users`

### AlertManager

Настройте алерты в AlertManager:

```yaml
groups:
  - name: mark_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(error_counter[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Высокая частота ошибок в системе Марка"
```

## Коды ошибок

| Код | Описание | Решение |
|-----|----------|---------|
| 400 | Неверный запрос | Проверьте формат JSON и обязательные поля |
| 404 | Ресурс не найден | Проверьте правильность ID или пути |
| 500 | Внутренняя ошибка сервера | Проверьте логи сервера |
| 503 | Сервис недоступен | Сервис не инициализирован, перезапустите приложение |

## Troubleshooting

### Проблема: Сервис не отвечает

**Симптомы:** HTTP 503, "Service not initialized"

**Решение:**
1. Проверьте логи приложения: `docker logs mark-app`
2. Убедитесь, что все зависимости запущены: `docker-compose ps`
3. Перезапустите сервис: `docker-compose restart app`

### Проблема: Ошибки в песочнице

**Симптомы:** Команды не выполняются, ошибки безопасности

**Решение:**
1. Проверьте, что Docker запущен: `docker ps`
2. Убедитесь, что контейнер песочницы работает
3. Проверьте права доступа к файлам
4. Используйте только разрешенные команды

### Проблема: Медленные ответы

**Симптомы:** Долгое время ответа, таймауты

**Решение:**
1. Проверьте метрики: `/metrics/summary`
2. Убедитесь, что Weaviate работает быстро
3. Проверьте нагрузку на LLM API
4. Рассмотрите кэширование

### Проблема: Ошибки памяти

**Симптомы:** Ошибки Weaviate, проблемы с поиском

**Решение:**
1. Проверьте состояние Weaviate: `/health`
2. Убедитесь, что схема памяти создана
3. Проверьте подключение к базе данных
4. Перезапустите Weaviate при необходимости

## Примеры интеграции

### Python клиент

```python
import requests
import json

class MarkClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def ask_question(self, question, chat_id=None):
        """Задать вопрос Марку"""
        response = requests.post(
            f"{self.base_url}/chat/ask",
            json={
                "question": question,
                "chat_id": chat_id
            }
        )
        return response.json()
    
    def execute_command(self, command):
        """Выполнить команду в песочнице"""
        response = requests.post(
            f"{self.base_url}/sandbox/exec",
            json={"command": command}
        )
        return response.json()
    
    def get_health(self):
        """Получить состояние системы"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def record_metric(self, name, value, labels=None):
        """Записать метрику"""
        response = requests.post(
            f"{self.base_url}/metrics/record",
            json={
                "name": name,
                "value": value,
                "labels": labels or {}
            }
        )
        return response.json()

# Использование
client = MarkClient()

# Задать вопрос
response = client.ask_question("Привет! Как дела?")
print(response["response"])

# Выполнить команду
result = client.execute_command("ls -la")
print(result["output"])

# Проверить здоровье
health = client.get_health()
print(f"Status: {health['status']}")
```

### JavaScript клиент

```javascript
class MarkClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }
    
    async askQuestion(question, chatId = null) {
        const response = await fetch(`${this.baseUrl}/chat/ask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                chat_id: chatId
            })
        });
        return await response.json();
    }
    
    async executeCommand(command) {
        const response = await fetch(`${this.baseUrl}/sandbox/exec`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ command: command })
        });
        return await response.json();
    }
    
    async getHealth() {
        const response = await fetch(`${this.baseUrl}/health`);
        return await response.json();
    }
    
    async recordMetric(name, value, labels = {}) {
        const response = await fetch(`${this.baseUrl}/metrics/record`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                name: name,
                value: value,
                labels: labels
            })
        });
        return await response.json();
    }
}

// Использование
const client = new MarkClient();

// Задать вопрос
client.askQuestion("Привет! Как дела?")
    .then(response => console.log(response.response))
    .catch(error => console.error('Error:', error));

// Выполнить команду
client.executeCommand("ls -la")
    .then(result => console.log(result.output))
    .catch(error => console.error('Error:', error));
```

### cURL примеры

```bash
#!/bin/bash

# Функция для работы с API Марка
mark_api() {
    local endpoint=$1
    local method=${2:-GET}
    local data=${3:-}
    
    if [ -n "$data" ]; then
        curl -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "http://localhost:8000$endpoint"
    else
        curl -X "$method" \
            "http://localhost:8000$endpoint"
    fi
}

# Примеры использования
echo "Проверка здоровья системы:"
mark_api "/health"

echo -e "\nЗадаем вопрос Марку:"
mark_api "/chat/ask" "POST" '{"question": "Привет! Как дела?"}'

echo -e "\nВыполняем команду:"
mark_api "/sandbox/exec" "POST" '{"command": "ls -la"}'

echo -e "\nПолучаем метрики:"
mark_api "/metrics/summary"
```

## Безопасность

### Рекомендации

1. **Ограничьте доступ к API** - используйте firewall или reverse proxy
2. **Мониторьте использование** - следите за метриками и логами
3. **Регулярно обновляйте** - поддерживайте актуальную версию
4. **Проверяйте команды** - валидируйте все команды перед выполнением

### Ограничения песочницы

Следующие команды запрещены в песочнице:
- `rm -rf` - удаление файлов
- `dd` - работа с блочными устройствами
- `mkfs` - форматирование файловых систем
- `mount` - монтирование файловых систем
- `chmod 777` - изменение прав доступа
- `sudo` - выполнение с правами администратора

## Поддержка

Для получения поддержки:

1. Проверьте документацию и примеры
2. Изучите логи системы
3. Проверьте метрики и состояние здоровья
4. Создайте issue в репозитории проекта

**Полезные команды для диагностики:**

```bash
# Проверка состояния системы
curl http://localhost:8000/health

# Просмотр метрик
curl http://localhost:8000/metrics/summary

# Проверка логов
curl "http://localhost:8000/logs/recent?hours=1"

# Тест песочницы
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello world"}'
``` 