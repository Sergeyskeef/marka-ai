#!/bin/bash

# Финальное исправление Telegram бота

echo "🚀 ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ TELEGRAM БОТА"
echo "======================================"
echo ""

# Проверяем, что мы в корне проекта
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Ошибка: docker-compose.yml не найден"
    echo "📂 Пожалуйста, запустите из корня проекта"
    exit 1
fi

echo "✅ Все исправления применены:"
echo "  - Добавлен nest-asyncio для решения проблем с event loop"
echo "  - Исправлены все импорты"
echo "  - Добавлены все недостающие файлы"
echo ""

echo "🛑 Останавливаем бота..."
docker stop bot 2>/dev/null || true
docker rm bot 2>/dev/null || true

echo "🔨 Перестройка образа бота (с очисткой кэша)..."
docker compose build bot --no-cache

echo "🚀 Запуск бота..."
docker compose up -d bot

echo "⏳ Ожидание инициализации (20 сек)..."
for i in {1..20}; do
    echo -n "."
    sleep 1
done
echo ""

echo ""
echo "📊 ПРОВЕРКА СТАТУСА:"
echo "==================="

# Статус контейнера
status=$(docker ps --filter "name=bot" --format "table {{.Status}}" | tail -n1)
if [[ $status == *"Up"* ]] && [[ $status != *"Restarting"* ]]; then
    echo "✅ Telegram Bot - работает!"
else
    echo "❌ Telegram Bot - проблемы"
    echo "Статус: $status"
    echo ""
    echo "Последние логи:"
    docker logs bot --tail 20 2>&1
fi

echo ""
echo "🎯 Готово!"
echo ""
echo "Полезные команды:"
echo "  docker logs bot -f        # Смотреть логи в реальном времени"
echo "  docker ps                 # Проверить статус всех контейнеров"
echo "  ./diagnose_and_fix.sh     # Диагностика проблем"
echo ""
echo "🤖 Бот должен быть доступен в Telegram!"