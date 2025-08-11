#!/bin/bash

echo "🚀 Финальное исправление и перезапуск проекта Марк"
echo "=================================================="
echo ""

# 1. Проверяем, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Ошибка: запустите скрипт из корня проекта (где docker-compose.yml)"
    exit 1
fi

echo "✅ Находимся в корне проекта"
echo ""

# 2. Останавливаем контейнеры
echo "🛑 Останавливаем контейнеры..."
docker compose down
echo ""

# 3. Проверяем .env файл
echo "📄 Проверка конфигурации..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📝 Создаю .env из примера..."
        cp .env.example .env
        echo "⚠️  Не забудьте отредактировать .env и добавить ключи API!"
    else
        echo "❌ Ошибка: нет .env файла"
        exit 1
    fi
else
    echo "✅ .env файл найден"
fi

# 4. Добавляем недостающую зависимость
echo ""
echo "📦 Добавляю недостающие зависимости..."
if ! grep -q "graphiti-core" langchain_api/requirements.txt; then
    echo "graphiti-core==0.3.0" >> langchain_api/requirements.txt
    echo "✅ Добавлена зависимость graphiti-core"
fi

# 5. Перестраиваем образы
echo ""
echo "🔨 Перестройка Docker образов..."
docker compose build

# 6. Запускаем контейнеры
echo ""
echo "🚀 Запуск контейнеров..."
docker compose up -d

# 7. Ждем инициализации
echo ""
echo "⏳ Ожидание запуска сервисов (30 сек)..."
sleep 30

# 8. Проверяем статус
echo ""
echo "📊 Проверка статуса контейнеров:"
docker compose ps

echo ""
echo "🔍 Проверка работоспособности сервисов:"
echo ""

# API
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API (FastAPI) - работает на http://localhost:8000"
    curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo ""
else
    echo "❌ API не отвечает"
fi

echo ""

# Graphiti
if curl -s http://localhost:7878/health > /dev/null 2>&1; then
    echo "✅ Graphiti - работает на http://localhost:7878"
else
    echo "❌ Graphiti не отвечает"
fi

echo ""

# Neo4j
if curl -s http://localhost:7474 > /dev/null 2>&1; then
    echo "✅ Neo4j UI - доступен на http://localhost:7474"
else
    echo "❌ Neo4j не отвечает"
fi

echo ""

# Проверяем логи проблемных контейнеров
BOT_STATUS=$(docker ps --filter "name=bot" --format "{{.Status}}" 2>/dev/null)
if [[ $BOT_STATUS == *"Restarting"* ]] || [[ -z "$BOT_STATUS" ]]; then
    echo "⚠️  Telegram Bot имеет проблемы"
    echo "Последние логи:"
    docker logs bot --tail 10 2>&1 || echo "Контейнер не найден"
else
    echo "✅ Telegram Bot - работает"
fi

echo ""
echo "============================================"
echo "✨ Готово!"
echo ""
echo "Полезные команды:"
echo "  docker compose logs -f       # Смотреть все логи"
echo "  docker compose logs bot -f   # Логи бота"
echo "  docker logs graphiti --tail 50  # Последние логи Graphiti"
echo "  docker compose ps           # Статус контейнеров"
echo ""
echo "Если бот не нужен, остановите его:"
echo "  docker stop bot"
echo ""