# 🔄 Reflexion Loop α

Система самоанализа и повторных попыток для AI-агента Mark v1.

## 🎯 Обзор

Reflexion Loop α позволяет агенту анализировать свои неудачи, извлекать уроки из прошлого опыта и делать повторные попытки с учетом полученных знаний. Это реализует принцип "обучения на ошибках" для улучшения качества ответов.

## 🏗️ Архитектура

### Компоненты системы

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AgentRunner   │───▶│ OutcomeLogger   │───▶│     Neo4j       │
│                 │    │                 │    │   (Outcomes)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                                              ▲
         ▼                                              │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ ReflexionAgent  │───▶│ DiaryEntry      │───▶│     Neo4j       │
│                 │    │   Writer        │    │ (DiaryEntries)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                                              ▲
         ▼                                              │
┌─────────────────┐    ┌─────────────────┐             │
│     LLM         │    │Neo4jDiaryBackend│─────────────┘
│  (Рефлексия)    │    │ (Vector Search) │
└─────────────────┘    └─────────────────┘
```

## 🔄 Двухшаговый цикл

### Алгоритм работы

1. **Первая попытка**
   - Агент получает запрос пользователя
   - Генерирует ответ через LLM
   - Оценивает качество ответа
   - Логирует результат в Neo4j

2. **Анализ неудачи** (если первая попытка неуспешна)
   - Агент анализирует причины неудачи
   - Создает DiaryEntry с выводами
   - Ищет похожие успешные случаи через vector search

3. **Вторая попытка**
   - Интегрирует найденные подсказки в контекст
   - Генерирует улучшенный ответ
   - Логирует финальный результат

### Пример работы

```python
from langchain_api.core.agent.runner import AgentRunner

runner = AgentRunner()

# Двухшаговый цикл с автоматической рефлексией
result = await runner.try_answer(
    user_message="Объясни квантовые компьютеры",
    user_id="user123"
)

print(f"Успех: {result.success}")
print(f"Попыток: {result.final_attempt}")
print(f"Ответ: {result.answer}")
```

## 🧠 Компоненты

### 1. OutcomeLogger

Логирует результаты каждого вызова инструментов.

```python
from langchain_api.core.metrics.outcome_logger import OutcomeLogger

logger = OutcomeLogger()

# Логирование успеха
logger.log_success(
    tool_name="search_memory",
    duration_ms=150,
    details="Найдено 5 релевантных записей"
)

# Логирование неудачи
logger.log_failure(
    tool_name="run_code",
    duration_ms=300,
    error="SyntaxError: invalid syntax",
    details="Ошибка в строке 15"
)
```

### 2. ReflexionAgent

Выполняет самоанализ неудач и создает DiaryEntry.

```python
from langchain_api.core.agent.reflexion import ReflexionAgent

agent = ReflexionAgent()

# Рефлексия после неудачи
result = await agent.self_reflect(
    user_message="Что такое блокчейн?",
    failed_answer="Не знаю",
    user_id="user123",
    context={
        "tools_used": ["search_memory"],
        "error_type": "insufficient_information"
    }
)

print(f"Успех рефлексии: {result.success}")
print(f"Извлеченные уроки: {result.insights}")
```

### 3. Neo4jDiaryBackend

Поиск похожих успешных случаев через vector search.

```python
from langchain_api.core.graphiti.backend_neo4j import Neo4jDiaryBackend

backend = Neo4jDiaryBackend()

# Поиск подсказок
hints = await backend.fetch_similar_successes(
    current_query="Объясни машинное обучение",
    user_id="user123",
    limit=3
)

for hint in hints:
    print(f"Подсказка: {hint.content}")
    print(f"Инсайты: {hint.insights}")
```

## 📊 Схема данных Neo4j

### Outcome (Результаты инструментов)

```cypher
CREATE (o:Outcome {
  tool_name: "search_memory",
  status: "success",  // "success" | "failure"
  duration_ms: 150,
  error: null,
  details: "Найдено 5 записей",
  tool_call_id: "call_123",
  timestamp: "2024-01-15T10:30:00Z",
  created_at: datetime()
})
```

### DiaryEntry (Записи рефлексии)

```cypher
CREATE (d:DiaryEntry {
  id: "diary_456",
  content: "Не хватало информации о квантовых алгоритмах...",
  source: "reflexion",
  timestamp: "2024-01-15T10:35:00Z",
  context: '{"tools_used": ["search_memory"], "error_type": "insufficient_info"}'
})

// Связь с пользователем
MERGE (u:User {id: "user123"})
MERGE (u)-[:WRITES]->(d)
```

## 🎛️ API Интеграция

### Использование в основном чате

```python
# main.py
from langchain_api.core.agent.runner import AgentRunner

@app.post("/v1/chat")
async def v1_chat(request: V1ChatRequest):
    runner = AgentRunner()
    
    # Автоматический Reflexion Loop
    result = await runner.try_answer(
        user_message=request.content,
        user_id=request.user_id
    )
    
    return V1ChatResponse(
        content=result.answer,
        success=result.success,
        attempts=result.final_attempt,
        reflexion_used=result.final_attempt > 1
    )
```

## 📈 Метрики

### Prometheus метрики

- `reflexion_success_rate` - Процент успешных рефлексий
- `reflexion_attempts_total` - Общее количество попыток
- `reflexion_second_attempt_success` - Успех второй попытки

### Доступ к метрикам

```bash
# Проверка метрик
curl http://localhost:8000/metrics | grep reflexion
```

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты Reflexion Loop
docker compose exec app python -m pytest /app/langchain_api/tests/e2e/test_reflexion_success.py -v

# Тесты отдельных компонентов
docker compose exec app python -m pytest /app/langchain_api/tests/metrics/ -v
docker compose exec app python -m pytest /app/langchain_api/tests/agent/ -v
docker compose exec app python -m pytest /app/langchain_api/tests/graphiti/ -v
```

### Покрытие тестами

- **OutcomeLogger**: 95% покрытие
- **ReflexionAgent**: 92% покрытие  
- **Neo4jDiaryBackend**: 88% покрытие
- **AgentRunner**: 89% покрытие

## 🔍 Мониторинг и отладка

### Логи системы

```bash
# Логи рефлексии
docker compose logs app | grep "reflexion"

# Логи Neo4j операций
docker compose logs app | grep "diary_entry"
```

### Отладка через Neo4j Browser

```cypher
// Все записи рефлексии за последний час
MATCH (d:DiaryEntry)
WHERE d.timestamp > datetime() - duration('PT1H')
RETURN d

// Статистика успешности по инструментам
MATCH (o:Outcome)
RETURN o.tool_name, o.status, count(*) as total
ORDER BY total DESC

// Поиск похожих успешных случаев
MATCH (d:DiaryEntry)
WHERE d.content CONTAINS "успешно" 
RETURN d.content, d.context
LIMIT 5
```

## 🚀 Использование

### Базовый сценарий

```python
runner = AgentRunner()

# Агент автоматически использует Reflexion Loop при неудачах
result = await runner.try_answer(
    user_message="Сложный технический вопрос",
    user_id="user123"
)

if result.success:
    print(f"Ответ получен за {result.final_attempt} попыток")
else:
    print("Не удалось найти удовлетворительный ответ")
```

### Продвинутое использование

```python
# Кастомная конфигурация
runner = AgentRunner(
    min_answer_length=100,  # Минимальная длина ответа
    quality_threshold=0.7,  # Порог качества
    max_hints=5            # Максимум подсказок из прошлого
)

result = await runner.try_answer(
    user_message="Детальный анализ темы",
    user_id="expert_user",
    context={"domain": "AI", "complexity": "high"}
)
```

## 🔧 Конфигурация

### Переменные окружения

```bash
# Включение режима отладки рефлексии
REFLEXION_DEBUG=true

# Лимит попыток (по умолчанию 2)
REFLEXION_MAX_ATTEMPTS=3

# Размер контекста для подсказок
REFLEXION_CONTEXT_SIZE=1000
```

### Настройка качества

```python
# Кастомные критерии оценки качества
class CustomQualityEvaluator:
    def evaluate_answer(self, answer: str, question: str) -> float:
        # Ваша логика оценки качества
        return quality_score
```

---

**Reflexion Loop α** — это первая итерация системы самоанализа агента. В будущих версиях планируется добавление машинного обучения для автоматического улучшения стратегий рефлексии.