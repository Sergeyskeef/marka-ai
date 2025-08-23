# 🚀 Марк - Быстрый старт

**Марк** — осознанный цифровой компаньон с памятью, инструментами и способностью к планированию.

## ✨ Что умеет Марк

- 🧠 **Долговременная память** — помнит все разговоры и контекст
- 🛠️ **Инструменты** — выполняет код, анализирует, планирует
- 🎭 **Режимы работы** — chat, code, plan для разных задач
- 📊 **Мониторинг** — метрики и наблюдение за работой
- 🤖 **Telegram бот** — удобный интерфейс для общения

## 🚀 Быстрый запуск

### 1. Клонирование и настройка

```bash
git clone <repository-url>
cd langchain_api
cp .env.example .env
```

### 2. Настройка переменных окружения

Отредактируйте `.env` файл:

```bash
# OpenAI API
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-mini

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Neo4j (опционально)
NEO4J_PASSWORD=your_neo4j_password

# Режим работы
ENV=dev  # или prod
```

### 3. Запуск системы

```bash
docker compose up -d
```

### 4. Проверка работоспособности

```bash
# Быстрая проверка (smoke test)
./scripts/smoke.sh

# Метрики Prometheus
curl http://localhost:8000/metrics | head -n 20

# Проверка памяти/CPU процесса (в контейнере app)
docker compose exec app python /app/langchain_api/scripts/profile_resources.py --seconds 30 --out /app/langchain_api/docs/metrics
```

## 🤖 Использование Telegram бота

### Быстрые кнопки

После команды `/help` бот покажет удобную клавиатуру с кнопками:

- **💬 Chat** — переключить на режим обычного общения
- **👨‍💻 Code** — переключить на режим выполнения кода
- **📝 Plan** — переключить на режим планирования
- **🛠️ Tools** — показать доступные инструменты

### Основные команды

- `/start` — приветствие и начало работы с ботом
- `/ping` — проверить работу бота
- `/help` — показать справку и кнопки
- `/tools` — показать доступные инструменты
- `/ask <вопрос>` — задать вопрос с памятью
- `/mode [режим]` — переключить режим работы
- `/run_code <код>` — выполнить код в песочнице

### Режимы работы

- **chat** — обычное общение (по умолчанию)
- **code** — весь текст считается кодом и выполняется
- **plan** — планирование задач

### Примеры использования

```
# Обычное общение
💬 Chat
Привет! Как дела?

# Выполнение кода
👨‍💻 Code
print(2×2)  # Автоматически исправляется на print(2*2)
# Результат: 4

print(10÷2)  # Автоматически исправляется на print(10/2)
# Результат: 5.0

# Планирование
📝 Plan
Создай план разработки веб-приложения

# Инструменты
🛠️ Tools
```

**💡 Автоматические исправления кода:**
- `×` → `*` (умножение)
- `÷` → `/` (деление)
- `−` → `-` (минус)
- Умные кавычки → стандартные

## 🌐 API Endpoints

### Основные endpoints

- `GET /health` — состояние системы
- `POST /chat/ask` — задать вопрос
- `GET /tools` — список инструментов
- `POST /memory` — добавить в память
- `GET /search` — поиск в памяти
- `GET /metrics/prometheus` — метрики Prometheus

### Примеры API запросов

```bash
# Задать вопрос
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Привет!", "mode": "chat"}'

# Получить инструменты
curl http://localhost:8000/tools

# Добавить в память
curl -X POST http://localhost:8000/memory \
  -H "Content-Type: application/json" \
  -d '{"text": "Важная информация", "metadata": {"type": "note"}}'

# Поиск в памяти
curl "http://localhost:8000/search?q=важная"
```

## 📊 Мониторинг

### Метрики Prometheus

```bash
# Экспорт метрик
curl http://localhost:8000/metrics/prometheus

# Сводка метрик
curl http://localhost:8000/metrics/summary
```

### Grafana (опционально)

Если настроен Grafana, доступен по адресу: `http://localhost:3000`

## 🧪 Тестирование

### Быстрая проверка (Smoke Test)

```bash
# Проверка основных сервисов за 30 секунд
./scripts/smoke.sh

# Для CI/CD
./scripts/smoke.sh && echo "Smoke test passed" || exit 1
```

### Запуск E2E тестов

```bash
# Из контейнера
docker compose exec app python -m pytest /app/langchain_api/tests/test_e2e_basic_flow.py -v

# Локально
cd langchain_api
python tests/test_e2e_basic_flow.py
```

### Запуск unit тестов

```bash
docker compose exec app python -m pytest /app/langchain_api/tests/ -v
```

## 🛠️ Разработка

### Структура проекта

```
langchain_api/
├── core/                 # Основная логика
│   ├── memory/          # Система памяти
│   ├── metrics.py       # Метрики
│   └── prompt_manager.py # Управление промптами
├── telegram_bot/        # Telegram бот
├── utils/               # Утилиты
│   └── toolkit.py       # Реестр инструментов
├── prompts/             # Промпты
│   └── prompts.yaml     # Конфигурация промптов
├── tests/               # Тесты
└── main.py              # FastAPI приложение
```

### Добавление новых инструментов

```python
from langchain_api.utils.toolkit import tool

@tool(
    name="my_tool",
    description="Описание инструмента",
    category="my_category",
    tags=["tag1", "tag2"]
)
def my_tool(param1: str, param2: int = 10) -> dict:
    """Документация инструмента"""
    # Реализация
    return {"result": "success"}
```

### Добавление новых режимов

Отредактируйте `prompts/prompts.yaml`:

```yaml
my_mode:
  system: |
    Ты — Марк в режиме my_mode.
    Описание режима...
```

## 🔧 Устранение неполадок

### Проблемы с Neo4j

```bash
# Проверка состояния Neo4j
docker compose logs graphiti-neo4j

# Перезапуск Neo4j
docker compose restart graphiti-neo4j
```

### Проблемы с ботом

```bash
# Проверка логов бота
docker compose logs bot

# Перезапуск бота
docker compose restart bot
```

### Проблемы с памятью

```bash
# Проверка Graphiti
curl http://localhost:7878/health

# Очистка данных (осторожно!)
docker compose down -v
docker compose up -d
```

## 📈 Производительность

### Рекомендуемые ресурсы

- **CPU**: 2+ ядра
- **RAM**: 4+ GB
- **Disk**: 10+ GB свободного места

### Оптимизация

- Используйте `ENV=prod` для продакшена
- Настройте лимиты Docker
- Мониторьте метрики Prometheus

## 🤝 Поддержка

- 📖 Документация: см. `IMPLEMENTATION_PROGRESS.md`
- 🐛 Issues: создавайте в репозитории
- 💬 Обсуждения: используйте Discussions

---

**Марк готов к работе! 🎉**

Начните с команды `/help` в Telegram боте или отправьте первый запрос через API. 