# GraphitiMemory Validation Guide

## Обзор

Этот документ описывает процесс валидации GraphitiMemory в проекте "Марк v2" - критически важного компонента для снижения латентности на 30% в Q1.

## Компоненты

### 1. Docker Services

В `docker-compose.yml` добавлены два сервиса:

- **graphiti**: Основной GraphitiMemory сервис (порт 7878)
- **graphiti-neo4j**: Neo4j backend (порт 7474, bolt 7687)

### 2. Feature Flags

Конфигурация через переменные окружения:

```bash
# Режим работы
GRAPHITI_MODE=shadow  # shadow | active | hybrid | disabled

# Подключение
GRAPHITI_BASE_URL=http://localhost:7878
GRAPHITI_NEO4J_URI=bolt://localhost:7687

# Фич-флаги для Q1
GRAPHITI_FALLBACK_TO_WEAVIATE=true
GRAPHITI_VALIDATION_ENABLED=true
```

### 3. Тесты

- **Smoke тесты**: `tests/graphiti_smoke.py`
- **Pytest тесты**: `tests/graphiti/test_graphiti_smoke.py`

## Локальное тестирование

### 1. Запуск сервисов

```bash
cd langchain_api
docker-compose up -d graphiti graphiti-neo4j
```

### 2. Проверка статуса

```bash
# Проверка контейнеров
docker ps | grep graphiti

# Проверка health endpoint
curl http://localhost:7878/health
```

### 3. Запуск smoke тестов

```bash
# Простые smoke тесты
python tests/graphiti_smoke.py

# Pytest тесты
python -m pytest tests/graphiti/test_graphiti_smoke.py -v
```

### 4. Проверка конфигурации

```bash
# Проверка feature flags
python -c "from core.graphiti_config import get_graphiti_feature_flags; print(get_graphiti_feature_flags())"

# Валидация конфигурации
python -c "from core.graphiti_config import validate_graphiti_config; print(validate_graphiti_config())"
```

## Тестирование в CI

### Автоматический запуск

GraphitiMemory автоматически тестируется в GitHub Actions:

```bash
# Запуск bench.yml workflow
gh workflow run bench.yml --ref main
```

### Мониторинг в CI

1. **Статус сервисов**: Проверка Docker контейнеров
2. **Health checks**: Проверка доступности API
3. **Smoke тесты**: Валидация основных операций
4. **Cleanup**: Автоматическая остановка сервисов

## Ожидаемые результаты

### ✅ Успешная валидация

- GraphitiMemory сервис запущен и отвечает на запросы
- Neo4j backend работает корректно
- Smoke тесты проходят успешно
- Feature flags настроены правильно

### 🔧 Troubleshooting

#### Проблема: GraphitiMemory не запускается

```bash
# Проверка логов
docker logs graphiti

# Проверка Neo4j
docker logs graphiti-neo4j

# Проверка сетевого подключения
docker network ls
```

#### Проблема: Smoke тесты не проходят

```bash
# Проверка доступности API
curl -v http://localhost:7878/health

# Проверка портов
netstat -tlnp | grep 7878
```

#### Проблема: Feature flags не работают

```bash
# Проверка переменных окружения
env | grep GRAPHITI

# Проверка конфигурации
python core/graphiti_config.py
```

## Следующие шаги

После успешной валидации:

1. **GraphitiMemory адаптер**: Создание `GraphitiMemory` класса
2. **Миграция данных**: Экспорт из Weaviate в GraphitiMemory
3. **A/B тестирование**: Сравнение производительности
4. **Полная замена**: Отключение Weaviate в Q1

## Метрики для мониторинга

| Метрика | Ожидаемое значение | Проверка |
|---------|-------------------|----------|
| Health endpoint | 200 OK | `curl http://localhost:7878/health` |
| Neo4j connectivity | UP | `docker ps \| grep graphiti-neo4j` |
| Smoke tests | PASSED | `python tests/graphiti_smoke.py` |
| Feature flags | shadow mode | `python -c "from core.graphiti_config import is_graphiti_shadow_mode; print(is_graphiti_shadow_mode())"` |

## Интеграция с существующим кодом

### Пример использования

```python
from core.graphiti_config import get_graphiti_config, is_graphiti_enabled

# Проверка включения GraphitiMemory
if is_graphiti_enabled():
    config = get_graphiti_config()
    
    if config.is_shadow_mode():
        print("GraphitiMemory в shadow режиме")
    elif config.is_active_mode():
        print("GraphitiMemory активен")
```

### Подготовка к Q1 миграции

```python
# Пример будущего адаптера
class GraphitiMemoryAdapter:
    def __init__(self):
        self.config = get_graphiti_config()
        self.base_url = self.config.base_url
        
    def store_memory(self, content: str, metadata: dict):
        if self.config.should_use_for_storage():
            # Сохранение в GraphitiMemory
            pass
        elif self.config.fallback_to_weaviate:
            # Fallback к Weaviate
            pass
```

## Заключение

GraphitiMemory Validation обеспечивает:

1. **Готовность к Q1**: Инфраструктура для миграции от Weaviate
2. **Безопасность**: Shadow режим без влияния на продакшн
3. **Мониторинг**: Автоматические проверки в CI
4. **Гибкость**: Feature flags для контроля развертывания

Успешная валидация открывает путь для реализации целей Q1 по снижению латентности на 30% через GraphitiMemory + Rust Core. 