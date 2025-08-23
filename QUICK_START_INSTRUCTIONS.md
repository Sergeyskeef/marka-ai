# 🚀 Инструкции по запуску проекта Марк

## ⚠️ Важно: Откуда запускать

**ВСЕ КОМАНДЫ ЗАПУСКАЮТСЯ ИЗ КОРНЯ ПРОЕКТА** (где находится `docker-compose.yml`), а **НЕ** из `langchain_api`!

```bash
# Правильно ✅
cd ~/marka  # или где у вас корень проекта
ls docker-compose.yml  # должен быть виден файл

# Неправильно ❌
cd ~/marka/langchain_api
```

## 📋 Пошаговая инструкция

### 1. Перейти в корень проекта

```bash
cd ~/marka  # или ваш путь к проекту
```

### 2. Создать .env файл

```bash
cp .env.example .env
```

Отредактируйте `.env` и добавьте:
- `OPENAI_API_KEY` - ваш ключ OpenAI
- `BOT_TOKEN` - токен Telegram бота (если нужен бот)

### 3. Исправить конфликты Docker (если есть ошибка)

```bash
# Сделать скрипт исполняемым
chmod +x fix_docker_conflict.sh

# Запустить очистку
./fix_docker_conflict.sh
```

### 4. Запустить проект

```bash
# Остановить старые контейнеры (если есть)
docker compose down

# Собрать образы
docker compose build

# Запустить в фоновом режиме
docker compose up -d
```

Или для старых версий Docker Compose:
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

### 5. Проверить статус

```bash
# Посмотреть запущенные контейнеры
docker compose ps

# Посмотреть логи
docker compose logs -f

# Проверить конкретный сервис
docker compose logs app
docker compose logs bot
docker compose logs graphiti-neo4j
```

## ✅ Проверка работоспособности

### API сервис
```bash
curl http://localhost:8000/health
```

### Graphiti сервис
```bash
curl http://localhost:7878/health
```

### Neo4j UI
Откройте в браузере: http://localhost:7474
- Логин: neo4j
- Пароль: из .env файла (NEO4J_PASSWORD)

### Telegram бот
Найдите вашего бота в Telegram и отправьте `/start`

## 🛑 Остановка проекта

```bash
# Из корня проекта
docker compose down

# Или для полной очистки (включая volumes)
docker compose down -v
```

## 🔧 Решение проблем

### Ошибка "container name already in use"
```bash
./fix_docker_conflict.sh
```

### Ошибка с портами
Проверьте, что порты не заняты:
- 8000 - FastAPI
- 7878 - Graphiti
- 7474, 7687 - Neo4j
- 6379 - Redis

### Проблемы с памятью
Убедитесь, что у Docker достаточно памяти (минимум 4GB).

## 📁 Структура после запуска

```
~/marka/                    # Корень проекта
├── docker-compose.yml      # ← Отсюда запускаем!
├── .env                    # Настройки
├── langchain_api/          # Код приложения
│   ├── app/               # Основные модули
│   ├── telegram_bot/      # Telegram бот
│   └── ...
└── fix_docker_conflict.sh  # Скрипт для исправления конфликтов
```