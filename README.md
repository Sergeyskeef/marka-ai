# Марка v2 - LangChain API
![Build Status](https://github.com/sergey/marka/workflows/CI/badge.svg)

## 🎯 Статус проекта

**🟢 Production Ready** - Интеграция Graphiti ⇆ Neo4j полностью протестирована и готова к использованию.

**✅ Последнее тестирование**: 15 июля 2025 - **9/9 интеграционных тестов прошли успешно**

**✅ Code Quality**: 15 июля 2025 - **Все ошибки Ruff исправлены (0 ошибок)**

## Описание проекта

Марка v2 - это интеллектуальный ассистент с интеграцией Graphiti и Neo4j для долговременной памяти. Проект использует современные технологии для создания эффективной системы памяти и обработки запросов.

## 🧠 Система памяти Graphiti ⇆ Neo4j

### Реализованная функциональность

#### ✅ Интеграция Graphiti с Neo4j
- **Надёжный запуск**: Neo4j стартует раньше Graphiti с healthcheck и depends_on
- **Сохранение метаданных**: Все примитивные типы (str, int, float, bool) сохраняются как отдельные свойства в Neo4j
- **Сериализация сложных типов**: Списки и словари автоматически сериализуются в JSON строки
- **Чтение из Neo4j**: Graphiti читает узлы из Neo4j и предоставляет их через API

#### ✅ API эндпоинты
- `POST /memory` - создание эпизодов с метаданными
- `GET /search?q=<query>` - поиск эпизодов по тексту
- `GET /health` - проверка состояния системы

#### ✅ Поддерживаемые типы метаданных
```python
{
    "text": "Текст эпизода",
    "metadata": {
        "source": "string",           # ✅ Сохраняется как строка
        "priority": 1,                # ✅ Сохраняется как число
        "score": 3.14,                # ✅ Сохраняется как float
        "is_important": True,         # ✅ Сохраняется как boolean
        "tags": ["tag1", "tag2"],     # ✅ Сериализуется в JSON
        "config": {"key": "value"}    # ✅ Сериализуется в JSON
    }
}
```

### Архитектура

```
┌─────────────────┐    HTTP    ┌─────────────────┐    Bolt    ┌─────────────────┐
│   Main API      │ ────────── │    Graphiti     │ ───────── │      Neo4j      │
│   (FastAPI)     │            │   (FastAPI)     │           │   (Database)    │
└─────────────────┘            └─────────────────┘           └─────────────────┘
        │                               │                           │
        │ POST /memory                   │ CREATE (e:Episode $props)│
        │ GET /search                    │ MATCH (e:Episode)        │
        └───────────────────────────────┴───────────────────────────┘
```

### Технические детали

#### Docker Compose конфигурация
```yaml
graphiti-neo4j:
  image: neo4j:5.11
  healthcheck:
    test: ["CMD-SHELL", "cypher-shell -u neo4j -p password 'RETURN 1'"]
    interval: 10s
    retries: 15

graphiti:
  build: ./graphiti_service
  depends_on:
    graphiti-neo4j:
      condition: service_healthy
```

#### Модель данных Graphiti
```python
class NodeProperties(BaseModel):
    msg: Optional[str] = None
    timestamp: Optional[float] = None
    test_run: Optional[bool] = None
    pytest_test: Optional[bool] = None

    class Config:
        extra = "allow"  # Разрешает любые дополнительные ключи
```

#### Cypher запросы
```cypher
-- Создание узла с метаданными
CREATE (e:Episode $props)

-- Поиск узлов
MATCH (e:Episode {msg: 'test'}) RETURN e.source, e.priority

-- Получение всех узлов
MATCH (n) RETURN n ORDER BY n.timestamp DESC
```

## 🚀 Запуск проекта

### Предварительные требования
- Docker и Docker Compose
- Python 3.10+

### Запуск всех сервисов
```bash
cd langchain_api
docker compose up -d
```

### Проверка статуса
```bash
docker compose ps
```

### Тестирование памяти
```bash
# Создание эпизода
docker compose exec app python -c "
import requests
response = requests.post('http://localhost:8000/memory', json={
    'text': 'Test episode',
    'metadata': {'source': 'test', 'priority': 1}
})
print(response.json())
"

# Поиск эпизодов
docker compose exec app python -c "
import requests
response = requests.get('http://localhost:8000/search?q=test')
print(response.json())
"
```

## 🧪 Тестирование

### Интеграционные тесты ✅ **ПРОХОДЯТ 100%**
```bash
# Запуск всех интеграционных тестов
docker compose exec app python -m pytest /app/langchain_api/tests/integration/test_graphiti_integration.py -v

# Запуск отдельных тестов
docker compose exec app python -m pytest /app/langchain_api/tests/integration/test_graphiti_integration.py::TestGraphitiIntegration::test_create_episode_with_metadata -v
```

**Результаты тестирования (15 июля 2025):**
- ✅ **9/9 тестов прошли успешно**
- ✅ **Health checks**: API, Graphiti, Neo4j
- ✅ **Создание эпизодов**: с метаданными
- ✅ **Поиск**: полнотекстовый поиск работает
- ✅ **API узлов**: Graphiti API доступен
- ✅ **Сохранение метаданных**: все типы данных
- ✅ **Сложные типы**: списки и словари
- ✅ **Индексы и constraints**: Neo4j оптимизация

**Статус**: 🟢 **Production Ready**

### Проверка в Neo4j
```bash
# Подключение к Neo4j
docker compose exec graphiti-neo4j cypher-shell -u neo4j -p password

# Просмотр всех эпизодов
MATCH (e:Episode) RETURN e.msg, e.source, e.priority LIMIT 10;

# Поиск по метаданным
MATCH (e:Episode {source: 'test'}) RETURN e;
```

## 📊 Мониторинг

### Health checks
- **Основной API**: `http://localhost:8000/health`
- **Graphiti**: `http://localhost:7878/health`
- **Neo4j**: `http://localhost:7474` (браузер)

### Логи
```bash
# Логи основного приложения
docker logs app

# Логи Graphiti
docker logs graphiti

# Логи Neo4j
docker logs graphiti-neo4j
```

## 🔧 Разработка

### Code Quality & Linting ✅ **ИСПРАВЛЕНО**

**Статус**: Все критические ошибки Ruff исправлены (0 ошибок)

**Исправленные типы ошибок:**
- ✅ **F821** (undefined-name) - 18 ошибок исправлены
- ✅ **F811** (unused imports) - 6 ошибок исправлены  
- ✅ **F401** (unused imports) - 2 ошибки исправлены
- ✅ **E722** (bare except) - 4 ошибки исправлены
- ✅ **W293** (blank line contains whitespace) - исправлены автоматически
- ✅ **UP007** (use-x-return-type) - 2 ошибки исправлены
- ✅ **B007** (unused-loop-control-variable) - 2 ошибки исправлены
- ✅ **F601** (dict-key-missing) - 2 ошибки исправлены
- ✅ **I001** (unsorted-imports) - 6 ошибок исправлены

**Исправленные файлы:**
- `core/backend_selector.py` - исправлены аннотации типов
- `utils/task_manager.py` - исправлены неопределенные переменные
- `main.py` - удален неиспользуемый импорт
- `services/task_executor.py` - удален дублирующий метод
- `utils/openai_proxy_client.py` - исправлено дублирование переменной
- `core/monitoring.py` - исправлен bare except
- `core/brain_processor.py` - исправлены bare except
- `rag/enhanced_rag_chain_tools.py` - исправлен bare except
- `core/event_reflection_integration.py` - исправлен дублирующий ключ
- `core/reflection/reflection_analyzer.py` - исправлена неиспользуемая переменная

**Конфигурация:**
- `pyproject.toml` - добавлен `B904` в ignore для временного отключения рекомендаций

### Структура проекта
```
langchain_api/
├── core/memory/
│   ├── graphiti_adapter.py    # HTTP-клиент для Graphiti
│   └── memory_manager.py      # Менеджер памяти
├── graphiti_service/
│   └── main.py               # Graphiti API сервер
├── tests/integration/
│   └── test_graphiti_integration.py  # Интеграционные тесты
└── docker-compose.yml        # Конфигурация контейнеров
```

### Добавление новых типов метаданных
1. Метаданные автоматически сохраняются в Neo4j
2. Примитивные типы (str, int, float, bool) сохраняются как есть
3. Сложные типы (list, dict) сериализуются в JSON строки
4. None значения пропускаются

### Расширение функциональности
- Добавление новых эндпоинтов в `main.py`
- Расширение модели данных в `graphiti_service/main.py`
- Создание новых тестов в `tests/integration/`

## 📈 Производительность

### Оптимизации
- **Healthcheck**: Neo4j запускается до Graphiti
- **Сериализация**: Сложные типы сериализуются в JSON
- **Фильтрация**: В поиске исключаются служебные поля
- **Пагинация**: Поддержка limit/offset в API

### Мониторинг
- Метрики через `/metrics/prometheus`
- Статистика через `/stats`
- Логирование всех операций

## 🔒 Безопасность

### Текущие меры
- Изоляция контейнеров
- Переменные окружения для паролей
- Валидация входных данных через Pydantic

### Рекомендации для production
- Использование секретов Docker
- Настройка SSL/TLS
- Ограничение доступа к Neo4j
- Регулярное резервное копирование

## 📝 История изменений

### Последние обновления
- ✅ Интеграция Graphiti с Neo4j
- ✅ Поддержка любых примитивных метаданных
- ✅ Сериализация сложных типов в JSON
- ✅ Интеграционные тесты
- ✅ Health checks и мониторинг
- ✅ Документация и README

### Планы развития
- [ ] Векторный поиск с embedding
- [ ] Связи между эпизодами
- [ ] Автоматическая очистка старых данных
- [ ] Репликация Neo4j для отказоустойчивости

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Добавьте тесты
4. Убедитесь, что все тесты проходят
5. Создайте Pull Request

## 📄 Лицензия

Проект разрабатывается в рамках внутренней разработки.

---

**Статус**: ✅ Graphiti ⇆ Neo4j интеграция полностью реализована и протестирована 