# A/B Backend Selector для Q1 Миграции

Система переключения между GraphitiMemory и Weaviate backend'ами памяти, реализованная для задачи D0 плана Q1.

## Основные возможности

### 🔄 Переключение Backend'ов
- **Environment Variable**: `MEMORY_BACKEND=graphiti|weaviate|auto`
- **Query Parameter**: `?backend=graphiti|weaviate|auto` в API запросах
- **Runtime Switch**: Динамическое переключение через API

### 🧪 A/B Тестирование
- **Session-based**: Автоматическое распределение на основе session_id
- **Configurable Ratio**: `AB_TEST_RATIO=0.5` (50/50 по умолчанию)
- **Enable/Disable**: `AB_TEST_MEMORY=true|false`

### 🛡️ Fallback & Health Checks
- **Automatic Fallback**: При недоступности GraphitiMemory → Weaviate
- **Health Monitoring**: Проверка доступности backend'ов
- **Graceful Degradation**: Система продолжает работать при сбоях

## Использование

### Переменные окружения
```bash
# Выбор default backend'а
MEMORY_BACKEND=auto          # Автоматический выбор (default)
MEMORY_BACKEND=graphiti      # Принудительно GraphitiMemory  
MEMORY_BACKEND=weaviate      # Принудительно Weaviate

# Настройки A/B тестирования
AB_TEST_MEMORY=true          # Включить A/B тестирование
AB_TEST_RATIO=0.3            # 30% GraphitiMemory, 70% Weaviate

# Настройки fallback
MEMORY_FALLBACK_ENABLED=true # Включить fallback (default)
MEMORY_FALLBACK_TIMEOUT=5    # Таймаут health check (секунды)
```

### API использование
```bash
# Обычный запрос (использует default backend)
curl -X POST "http://localhost:8000/chat/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Привет!"}'

# A/B тест с GraphitiMemory
curl -X POST "http://localhost:8000/chat/ask?backend=graphiti" \
  -H "Content-Type: application/json" \
  -d '{"question": "Тест GraphitiMemory"}'

# A/B тест с Weaviate
curl -X POST "http://localhost:8000/chat/ask?backend=weaviate" \
  -H "Content-Type: application/json" \
  -d '{"question": "Тест Weaviate"}'

# Статус backend'ов
curl "http://localhost:8000/backends/status"
```

### Программное использование
```python
from langchain_api.core.backend_selector import create_memory, get_backend_status

# Создание памяти с автоматическим выбором backend'а
memory = create_memory(short_term_limit=20)

# Создание памяти с принудительным выбором backend'а
memory = create_memory(backend='graphiti', session_id='user_123')

# Получение статуса backend'ов
status = get_backend_status()
print(f"Default backend: {status['default_backend']}")
print(f"GraphitiMemory: {status['backends']['graphiti']['status']}")
print(f"Weaviate: {status['backends']['weaviate']['status']}")
```

## Обновленные компоненты

### Основные файлы памяти
- `langchain_api/telegram_bot/bot.py` - обновлен для использования A/B selector
- `langchain_api/core/llm_integration_hub.py` - обновлен для A/B selector
- `langchain_api/rag/enhanced_rag_chain.py` - обновлен для A/B selector
- `langchain_api/rag/enhanced_rag_chain_tools.py` - обновлен для A/B selector

### API endpoints
- `POST /chat/ask?backend=<backend>` - поддержка query-параметра backend
- `GET /backends/status` - новый endpoint для мониторинга backend'ов

### Новые модули
- `langchain_api/core/backend_selector.py` - основная логика A/B switcher
- `langchain_api/tests/test_backend_selector.py` - полное покрытие тестами

## Мониторинг и отладка

### Endpoint статуса
```bash
curl "http://localhost:8000/backends/status"
```

Возвращает:
```json
{
  "success": true,
  "backend_status": {
    "default_backend": "auto",
    "ab_test_enabled": true,
    "ab_test_ratio": 0.5,
    "fallback_enabled": true,
    "backends": {
      "graphiti": {
        "available": true,
        "status": "healthy"
      },
      "weaviate": {
        "available": true, 
        "status": "healthy"
      }
    }
  },
  "timestamp": 1704067200.0
}
```

### Логи
```bash
# Логи backend selector'а
docker logs app | grep "BackendSelector"

# Логи GraphitiMemory
docker logs app | grep "GraphitiMemory"

# Логи выбора backend'а  
docker logs app | grep "Используем\|AUTO:"
```

## Тестирование

### Запуск тестов
```bash
# Все тесты backend selector'а
docker compose exec app python -m pytest /app/langchain_api/tests/test_backend_selector.py -v

# Конкретный тест
docker compose exec app python -m pytest /app/langchain_api/tests/test_backend_selector.py::TestBackendSelector::test_ab_testing_session_hash -v
```

### Покрытие тестов
- ✅ Выбор backend'а из переменных окружения
- ✅ Query-параметр в API запросах  
- ✅ A/B тестирование на основе session_id
- ✅ Fallback логика при недоступности GraphitiMemory
- ✅ Health checks и мониторинг
- ✅ Runtime переключение backend'ов
- ✅ Интеграционные тесты

## Следующие шаги (D1-D5)

После успешной реализации D0, следующие задачи из плана:

- **D1**: `make export-weaviate` → JSONL экспорт данных
- **D2**: `make import-graphiti` + smoke тесты импорта
- **D3**: Вызов Rust Core из Python retriever
- **D4**: `make bench-rust` локально, собрать p95 метрики
- **D5**: PR → CI bench сравнение & review

## Заключение

✅ **A/B Backend Selector успешно реализован** для задачи D0!

Система обеспечивает:
- Гибкое переключение между GraphitiMemory и Weaviate
- A/B тестирование для постепенной миграции
- Надежный fallback при проблемах с GraphitiMemory
- Полное тестовое покрытие и мониторинг
- Обратную совместимость с существующим кодом 