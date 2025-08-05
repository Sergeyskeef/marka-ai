# 🤖 Марк - AI-компаньон с памятью и саморазвитием

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![Neo4j](https://img.shields.io/badge/Neo4j-5.0+-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
[![Test Coverage](https://img.shields.io/badge/coverage-%E2%89%A550%25-yellow.svg)](.github/workflows/test-coverage.yml)

## 📖 О проекте

**Марк** - это интеллектуальный AI-компаньон с долговременной памятью, способностью к саморазвитию и анализу собственных действий. Проект использует современные технологии машинного обучения и графовые базы данных для создания персонализированного опыта взаимодействия.

### 🎯 Ключевые особенности

- 🧠 **Долговременная память** на базе Neo4j и Graphiti
- 💬 **Telegram-бот** с удобным интерфейсом и inline-кнопками
- 🛡️ **Безопасная песочница** для выполнения кода с AST-проверками
- 🔍 **Система рефлексии** для анализа и улучшения собственных действий
- 📊 **Мониторинг и метрики** с визуализацией в реальном времени
- 🔧 **Расширяемая архитектура** с поддержкой пользовательских инструментов

## 🚀 Быстрый старт

### Требования

- Docker и Docker Compose
- Python 3.11+
- 8GB RAM минимум
- 20GB свободного места на диске

### Установка и запуск

1. **Клонируйте репозиторий:**
```bash
git clone https://github.com/Sergeyskeef/marka-ai.git
cd marka-ai
```

2. **Создайте файл `.env` с настройками:**
```bash
cp .env.example .env
```

Обязательные переменные:
```env
# LLM настройки
OPENAI_API_KEY=your_openai_api_key

# Telegram бот (опционально)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Neo4j
NEO4J_URL=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password
```

3. **Запустите проект:**
```bash
docker-compose up -d
```

4. **Проверьте статус:**
```bash
# Проверка здоровья системы
curl http://localhost:8000/health

# Проверка доступных инструментов
curl http://localhost:8000/tools
```

## 📁 Структура проекта

```
marka-ai/
├── core/                    # Ядро системы
│   ├── llm_service.py      # Сервис работы с LLM
│   ├── memory/             # Система памяти
│   ├── reflection/         # Анализ и рефлексия
│   └── tools_registry.py   # Реестр инструментов
├── telegram_bot/           # Telegram интерфейс
│   ├── bot.py             # Основная логика бота
│   └── handlers/          # Обработчики команд
├── sandbox/               # Безопасное выполнение кода
│   └── sandbox_manager.py # Менеджер песочницы с AST
├── services/              # Внешние сервисы
│   └── task_executor.py   # Выполнение задач
├── tests/                 # Тесты
├── main.py               # FastAPI приложение
└── docker-compose.yml    # Конфигурация контейнеров
```

## 🔌 API Endpoints

### Основные endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/chat/ask` | Отправить сообщение Марку |
| POST | `/memory` | Сохранить информацию в память |
| GET | `/search` | Поиск в памяти |
| GET | `/tools` | Список доступных инструментов |
| POST | `/sandbox/exec` | Выполнить код в песочнице |
| GET | `/reflection/insights` | Получить инсайты из анализа |
| GET | `/health` | Проверка здоровья системы |

### Примеры использования

**Чат с Марком:**
```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет, Марк! Расскажи о себе",
    "chat_id": 12345
  }'
```

**Выполнение кода в песочнице:**
```bash
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "python3 -c \"print(42 * 10)\"",
    "language": "python"
  }'
```

**Поиск в памяти:**
```bash
curl "http://localhost:8000/search?q=важная+информация"
```

## 🤖 Telegram бот

Марк доступен через Telegram бота с удобным интерфейсом.

### Основные команды

- `/start` - Начать общение с Марком
- `/help` - Список всех команд
- `/task_list` - Список текущих задач
- `/run_code` - Выполнить код в песочнице
- `/memory_stats` - Статистика памяти
- `/tools` - Доступные инструменты

### Особенности

- 🎯 **Inline кнопки** для быстрой обратной связи
- 🛡️ **Rate limiting** для защиты от спама
- 📝 **Markdown** форматирование ответов
- 🔄 **Асинхронная обработка** длинных запросов

## 🧠 Система памяти

Марк использует двухуровневую систему памяти:

### 1. Краткосрочная память
- Хранит последние диалоги и контекст
- Быстрый доступ для релевантных ответов
- Автоматическая очистка старых данных

### 2. Долговременная память (Neo4j + Graphiti)
- Графовая структура для связей между концепциями
- Семантический поиск по всей истории
- Метаданные и контекст для каждого воспоминания

### Пример структуры памяти
```json
{
  "text": "Пользователь попросил помощь с Python",
  "metadata": {
    "user_id": "12345",
    "timestamp": 1703001234,
    "tags": ["python", "помощь", "программирование"],
    "importance": 0.8
  }
}
```

## 🛡️ Безопасность

### Песочница для выполнения кода

- ✅ **AST проверка** Python кода перед выполнением
- ✅ **Блокировка опасных операций**: `os.system`, `eval`, `exec`, `open`
- ✅ **Таймауты** для предотвращения зависаний
- ✅ **Ограничение вывода** для защиты от переполнения

### Защита API

- 🔐 **Rate limiting** на всех endpoints
- 🛡️ **Централизованная обработка ошибок** через `@handle_errors`
- 📝 **Валидация входных данных** через Pydantic
- 🔄 **Retry логика** для внешних сервисов

## 📊 Мониторинг и метрики

### Trace UI
Визуальный интерфейс для отслеживания работы системы:
- URL: http://localhost:8000/trace/ui
- Отслеживание всех вызовов инструментов
- Анализ производительности
- История ошибок

### Prometheus метрики
```bash
# Получить метрики
curl http://localhost:8000/metrics/prometheus

# Сводка по системе
curl http://localhost:8000/metrics/summary
```

## 🧪 Тестирование

### Запуск тестов
```bash
# Все тесты
pytest tests/ -v

# С покрытием
pytest --cov=. --cov-report=html

# Проверка покрытия (минимум 50%)
./scripts/check_coverage.sh
```

### CI/CD
- Автоматическая проверка покрытия через GitHub Actions
- Минимальное требование: 50% покрытия кода
- Отчеты в PR с результатами

## 🔧 Разработка

### Добавление нового инструмента

1. Создайте функцию с декоратором `@register_tool`:
```python
from core.tools_registry import register_tool

@register_tool(
    name="my_tool",
    description="Описание инструмента",
    tags=["utility"],
    priority=0.8
)
def my_tool(param1: str, param2: int) -> dict:
    """Делает что-то полезное"""
    return {"result": "success"}
```

2. Инструмент автоматически появится в:
- `/tools` - список всех инструментов
- `/tools/openai-functions` - формат для LLM
- Telegram боте через команду `/tools`

### Режимы работы Марка

- 🎨 **CREATIVE** - Творческий режим для генерации идей
- 🔧 **IMPLEMENT** - Режим реализации и кодирования
- 🧪 **QA** - Режим тестирования и проверки качества
- 📋 **PLAN** - Режим планирования и организации
- 🚐 **VAN** - Универсальный режим

## 📦 Сервисы и порты

| Сервис | Порт | Описание |
|--------|------|----------|
| FastAPI | 8000 | Основное API |
| Telegram Bot | 8001 | Telegram интерфейс |
| Neo4j | 7474/7687 | База знаний (HTTP/Bolt) |
| Graphiti | 7878 | Сервис памяти |
| Redis | 6379 | Кеширование |

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте branch для фичи (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## 📝 Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE) для деталей.

## 🙏 Благодарности

- OpenAI за GPT модели
- Neo4j за графовую базу данных
- FastAPI за отличный веб-фреймворк
- Сообществу открытого ПО за вдохновение

---

**Марк** - ваш персональный AI-компаньон, готовый помочь, учиться и развиваться вместе с вами! 🚀 