# 🔍 AGENTS_TRACE - Система трассировки агентов

## Обзор

Система трассировки агентов (AGENTS_TRACE) предоставляет полную видимость в работу AI-агентов, инструментов и LLM-вызовов в проекте Марк v2. Это мощный инструмент для разработчиков, позволяющий анализировать производительность, отлаживать проблемы и оптимизировать работу агентов.

## 🚀 Возможности

### Основные функции
- **Полная трассировка** всех вызовов агентов, инструментов и LLM
- **Визуализация** в реальном времени через веб-интерфейс
- **Древовидная структура** spans для понимания иерархии вызовов
- **Метрики производительности** (время выполнения, ошибки, статистика)
- **Автообновление** данных каждые 5 секунд
- **Фильтрация** по типам spans и временным диапазонам

### Типы трассируемых событий
- **LLM вызовы** - запросы к языковым моделям
- **Tool вызовы** - выполнение инструментов агента
- **HTTP запросы** - API вызовы
- **User/Assistant** - взаимодействия пользователя и ассистента

## 🛠️ Установка и настройка

### Зависимости
```bash
pip install PyYAML jinja2
```

### Переменные окружения
```bash
# Включение/отключение трассировки
TRACE_ENABLED=true

# Путь к базе данных трассировки
TRACE_DB_PATH=/data/trace.db

# Максимальный размер базы данных
TRACE_DB_MAX_SIZE=50MB
```

### Docker Compose
```yaml
services:
  app:
    environment:
      - TRACE_ENABLED=true
      - TRACE_DB_PATH=/data/trace.db
    volumes:
      - trace_data:/data

volumes:
  trace_data:
```

## 📊 Веб-интерфейс

### Доступ к UI
```
http://localhost:8000/trace/
```

### Основные разделы

#### 1. Статистика
- **Всего spans** - общее количество трассируемых событий
- **Среднее время** - средняя продолжительность выполнения
- **Ошибки (%)** - процент неуспешных операций
- **Активные spans** - текущие выполняющиеся операции

#### 2. Управление
- **Обновить** - принудительное обновление данных
- **Статистика** - обновление статистики
- **Фильтр по типу** - фильтрация spans по типу события
- **Лимит** - количество отображаемых spans
- **Очистить** - удаление всех spans (только для разработки)

#### 3. Список Spans
- **Название** - описание операции
- **Тип** - категория события (LLM, Tool, HTTP, etc.)
- **Длительность** - время выполнения в миллисекундах
- **Статус** - результат выполнения (completed, error, started)
- **Детали** - ID, время создания, родительский span

#### 4. Визуализация
- **Дерево трассировки** - иерархическое представление spans
- **D3.js графика** - интерактивная визуализация

## 🔧 API Endpoints

### Получение spans
```http
GET /trace/api/spans?limit=50&span_type=llm
```

**Параметры:**
- `limit` - количество spans (по умолчанию 50)
- `span_type` - фильтр по типу (llm, tool, http_request, user, assistant)

**Ответ:**
```json
{
  "success": true,
  "spans": [
    {
      "span_id": "uuid",
      "name": "LLM Call: gpt-4",
      "span_type": "llm",
      "parent_id": "parent-uuid",
      "start_time": 1234567890.123,
      "end_time": 1234567890.456,
      "duration_ms": 333.0,
      "input_data": {"model": "gpt-4", "prompt": "Hello"},
      "output_data": {"response": "Hi there!", "duration_ms": 333.0},
      "metadata": {"model": "gpt-4"},
      "status": "completed",
      "error": null,
      "created_at": "2024-01-01T12:00:00"
    }
  ],
  "count": 1
}
```

### Детали span
```http
GET /trace/api/spans/{span_id}
```

### Статистика
```http
GET /trace/api/stats
```

**Ответ:**
```json
{
  "success": true,
  "stats": {
    "total_spans": 100,
    "type_distribution": {
      "llm": 50,
      "tool": 30,
      "http_request": 20
    },
    "status_distribution": {
      "completed": 95,
      "error": 5
    },
    "total_duration_ms": 15000.0,
    "avg_duration_ms": 150.0,
    "error_rate": 0.05
  }
}
```

### Здоровье системы
```http
GET /trace/api/health
```

## 💻 Использование в коде

### Базовое использование

```python
from langchain_api.middlewares.agents_trace import trace_span, trace_llm_call, trace_tool_call

# Трассировка LLM вызова
trace_llm_call("gpt-4", "Hello", "Hi there!", 150.5)

# Трассировка вызова инструмента
trace_tool_call("search_web", {"query": "python"}, "results", 50.2)

# Контекстный менеджер для сложных операций
with trace_span("Complex Operation", "custom_type", input_data={"param": "value"}) as span_id:
    # Ваш код здесь
    result = perform_complex_operation()
    # Span автоматически завершится при выходе из контекста
```

### Интеграция с существующим кодом

```python
from langchain_api.core.guardrails_client import with_guardrails

@with_guardrails
def my_llm_function(text: str) -> dict:
    # Функция автоматически будет трассироваться
    return {"role": "assistant", "content": f"Processed: {text}"}
```

### Middleware для FastAPI

```python
from langchain_api.middlewares.agents_trace import AgentsTraceMiddleware

app = FastAPI()
app.add_middleware(AgentsTraceMiddleware)
```

## 📈 Метрики и мониторинг

### Ключевые метрики
- **Latency** - время отклика различных компонентов
- **Throughput** - количество обрабатываемых запросов
- **Error Rate** - частота ошибок
- **Resource Usage** - использование ресурсов

### Алерты
- Высокая латентность (> 5 секунд)
- Высокий процент ошибок (> 10%)
- Недоступность системы трассировки

## 🔍 Отладка

### Типичные проблемы

#### 1. База данных недоступна
```bash
# Проверка прав доступа
ls -la /data/trace.db

# Проверка свободного места
df -h /data
```

#### 2. Высокая латентность
- Проверьте логи на наличие медленных запросов
- Анализируйте статистику по типам spans
- Рассмотрите оптимизацию кода

#### 3. Ошибки валидации
- Проверьте конфигурацию Guardrails
- Анализируйте spans с ошибками
- Исправьте проблемы в коде

### Логирование
```python
import logging

# Настройка логирования для трассировки
logging.getLogger('langchain_api.middlewares.agents_trace').setLevel(logging.DEBUG)
```

## 🚀 Производительность

### Оптимизации
- **Автоочистка** старых spans (по умолчанию 1000 последних)
- **Асинхронная запись** в базу данных
- **Сжатие** данных для экономии места
- **Индексы** для быстрого поиска

### Рекомендации
- Отключайте трассировку в продакшене для критичных систем
- Используйте фильтрацию для снижения нагрузки
- Мониторьте размер базы данных
- Регулярно очищайте старые данные

## 🔒 Безопасность

### Защита данных
- **Маскирование** чувствительных данных (токены, пароли)
- **Хеширование** длинных значений
- **Ограничение доступа** к UI в продакшене

### Конфигурация безопасности
```yaml
# configs/rails/default.yml
security:
  mask_sensitive_data: true
  sensitive_keys: ["api_key", "token", "password"]
  max_data_length: 1000
```

## 📚 Примеры использования

### Анализ производительности
1. Откройте `/trace/`
2. Фильтруйте по типу "llm"
3. Анализируйте время выполнения
4. Ищите аномалии в латентности

### Отладка ошибок
1. Найдите spans со статусом "error"
2. Изучите детали ошибки
3. Проследите цепочку вызовов
4. Исправьте проблему в коде

### Оптимизация
1. Определите медленные операции
2. Анализируйте паттерны использования
3. Оптимизируйте код
4. Измерьте улучшения

## 🤝 Вклад в разработку

### Добавление новых типов spans
```python
# В middlewares/agents_trace.py
def trace_custom_operation(operation_name: str, data: dict, result: any, duration_ms: float):
    span_id = trace_collector.start_span(
        name=f"Custom: {operation_name}",
        span_type="custom",
        input_data=data,
        metadata={"operation": operation_name}
    )
    trace_collector.finish_span(
        span_id=span_id,
        output_data={"result": result, "duration_ms": duration_ms}
    )
```

### Расширение UI
- Добавьте новые фильтры в `templates/trace.html`
- Создайте дополнительные графики с D3.js
- Реализуйте новые API endpoints

## 📞 Поддержка

### Полезные команды
```bash
# Проверка здоровья системы
curl http://localhost:8000/trace/api/health

# Получение статистики
curl http://localhost:8000/trace/api/stats

# Очистка данных (только для разработки)
curl -X DELETE http://localhost:8000/trace/api/spans
```

### Логи
```bash
# Просмотр логов трассировки
docker logs app | grep "agents_trace"

# Проверка размера базы данных
ls -lh /data/trace.db
```

---

**Автор:** Команда разработки Марк v2  
**Версия:** 1.0.0  
**Дата:** 2024-01-01 