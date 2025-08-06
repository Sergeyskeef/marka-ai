# 🗺️ Карта проекта Марк и План действий

## 📊 Текущее состояние проекта

### ✅ Что уже реализовано и работает:

1. **Основная инфраструктура**:
   - FastAPI приложение (`main.py`) - центральный API
   - Telegram бот (`telegram_bot/bot.py`) - интерфейс пользователя
   - Docker Compose окружение с сервисами:
     - `app` - основное приложение
     - `bot` - Telegram бот
     - `sandbox` - изолированная песочница
     - `graphiti-neo4j` - графовая БД для памяти
     - `redis` - кеш и сессии
     - `postgres` - реляционное хранилище
   - НЕТ Weaviate (удален из проекта)

2. **Система памяти**:
   - GraphitiMemoryAdapter (`core/memory/graphiti_adapter.py`) - HTTP клиент для Graphiti
   - Neo4j используется как векторная БД через Graphiti
   - Многослойная память с типами: Memory, Experience, Insight, Persona, Userfacts
   - Кеширование через Redis (`core/memory/graphiti_cache.py`)
   - Гибридный поиск (`core/memory/hybrid_search.py`)

3. **Песочница**:
   - SandboxManager (`sandbox/sandbox_manager.py`) - управление выполнением кода
   - Базовая AST проверка Python кода
   - Docker контейнер для изоляции
   - API endpoints: `/sandbox/sync`, `/sandbox/exec`

4. **Бот функциональность**:
   - Команды: `/sync`, `!pytest`, `/sandbox_report`
   - Кнопка "👨‍💻 code" и команда `/run_code`
   - Shell команды через `!` префикс
   - Заглушка для декомпозиции задач

### ⚠️ Что требует доработки:

1. **Безопасность песочницы**:
   - Нет белого списка shell команд (критично!)
   - Слабая проверка сетевых операций
   - Отсутствует проверка ресурсов

2. **Система планирования**:
   - `task_planning_system.py` - только заглушки
   - `decompose_cmd` в боте - просто выводит текст
   - Нет сохранения планов в памяти

3. **Интеграция компонентов**:
   - 87 изолированных модулей
   - Нет Event Bus для связи
   - Компоненты вызывают друг друга напрямую

4. **Самосознание**:
   - Базовая версия без анализа кода
   - Не может читать свой код
   - Не диагностирует ошибки

### ❌ Что отсутствует:

1. Event Bus для асинхронной связи
2. Структурированное логирование
3. Метрики и мониторинг
4. Webhook поддержка

## 🎯 План действий (с учетом существующего кода)

### Фаза 1: Критические исправления безопасности (1 день)

#### 1.1 Обновить SandboxManager (2 часа)

**Файл**: `/workspace/sandbox/sandbox_manager.py`

```python
# Добавить в __init__:
self.allowed_shell_commands = {
    'echo', 'printf', 'date', 'pwd', 'whoami',
    'ls', 'dir', 'find', 'grep', 'sed', 'awk',
    'sort', 'uniq', 'wc', 'head', 'tail', 'cat',
    'python', 'python3', 'pip', 'npm', 'node'
}

# Добавить метод _check_shell_command
# Обновить execute_command с проверкой shell команд
```

#### 1.2 Расширить AST проверки (1 час)

```python
# Добавить в dangerous_ast_nodes:
ast.Import: ['socket', 'urllib', 'requests', 'httpx'],
# Блокировать getattr, setattr, globals, locals
```

#### 1.3 Написать тесты безопасности (1 час)

**Файл**: `/workspace/tests/test_sandbox_security_enhanced.py`

### Фаза 2: Система планирования (2 дня)

#### 2.1 Реализовать TaskPlanner (4 часа)

**Файл**: `/workspace/sandbox/task_planning_system.py`
- Заменить заглушки на полную реализацию
- Использовать существующий LLM клиент из `langchain_api.core.llm`
- Интегрировать с GraphitiMemoryAdapter для сохранения планов

#### 2.2 API endpoints (2 часа)

**Файл**: `/workspace/main.py`
```python
# Добавить после строки 187 (инициализация _sandbox_manager):
from langchain_api.sandbox.task_planning_system import TaskPlanner
task_planner = TaskPlanner()

# Добавить endpoints:
@app.post("/plan/create")
@app.get("/plan/{plan_id}/status")
@app.post("/plan/{plan_id}/execute")
```

#### 2.3 Обновить команду декомпозиции в боте (2 часа)

**Файл**: `/workspace/telegram_bot/bot.py`

Заменить заглушку `decompose_cmd` (строка 495) на полноценную реализацию:
```python
async def decompose_cmd(update, context):
    """Создает план выполнения задачи"""
    # Реализация с вызовом /plan/create API
```

### Фаза 3: Event Bus и интеграция (2 дня)

#### 3.1 Создать Event Bus (3 часа)

**Новый файл**: `/workspace/core/event_bus.py`
- Простая реализация с подписками
- Асинхронная публикация событий
- История событий

#### 3.2 Интегрировать компоненты (3 часа)

Подключить к Event Bus:
- GraphitiMemoryAdapter - события сохранения/поиска
- SandboxManager - события выполнения кода
- TaskPlanner - события создания/выполнения планов

### Фаза 4: Расширение самосознания (1 день)

#### 4.1 Добавить анализ кода (3 часа)

**Файл**: `/workspace/sandbox/self_awareness.py`
```python
# Добавить методы:
- analyze_own_code(file_path)
- find_capability_implementation(capability)
- diagnose_error(error_type, error_message)
```

#### 4.2 Интеграция с ботом (2 часа)

Добавить команды:
- `/analyze <file>` - анализ файла проекта
- `/diagnose` - диагностика последней ошибки

### Фаза 5: UX улучшения (опционально, 1 день)

#### 5.1 Улучшить вывод кода (2 часа)
- Использовать Pygments для подсветки
- Форматировать вывод ошибок

#### 5.2 История команд (2 часа)
- Сохранять в Redis
- Команда `/history`

## 🔧 Оптимизация под ограниченные ресурсы

### Docker лимиты (уже в docker-compose.yml):
```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 1G
          
  sandbox:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
```

### Лимиты песочницы:
```python
RESOURCE_LIMITS = ResourceLimits(
    cpu_quota=50000,      # 50% одного CPU
    memory_mb=512,        # 512MB RAM
    execution_timeout=30  # 30 секунд
)
```

## 📋 Приоритеты выполнения

1. **🚨 КРИТИЧНО** (сегодня):
   - Безопасность песочницы - белый список команд
   - Тесты безопасности

2. **🔥 ВЫСОКИЙ** (2-3 дня):
   - Система планирования
   - Интеграция с памятью

3. **⚡ СРЕДНИЙ** (4-5 дней):
   - Event Bus
   - Расширение самосознания

4. **💫 НИЗКИЙ** (позже):
   - UX улучшения
   - Мониторинг

## 🚀 Начало работы

```bash
# 1. Начинаем с критических исправлений
cd /workspace/sandbox
vim sandbox_manager.py

# 2. Проверяем изменения
cd /workspace
python3 -m pytest tests/test_sandbox_exec_f4.py -v

# 3. Коммитим
git add .
git commit -m "fix: добавлен белый список shell команд в песочницу"
```

## 📝 Важные замечания

1. **Не переписываем с нуля** - только дорабатываем существующий код
2. **Используем GraphitiMemory** вместо Weaviate для векторного поиска
3. **Учитываем ограничения** - 2 CPU, 4GB RAM
4. **Фокус на безопасности** - сначала закрываем критические уязвимости

## 🔍 Следующие шаги

После выполнения Фазы 1 (безопасность):
1. Провести полное тестирование песочницы
2. Начать реализацию системы планирования
3. Постепенно связывать компоненты через Event Bus