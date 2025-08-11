#!/bin/bash

echo "🤖 Перезапуск Telegram бота..."
echo ""

# Останавливаем бота
echo "🛑 Останавливаем бота..."
docker stop bot 2>/dev/null || true

# Перестраиваем образ бота
echo "🔨 Перестройка образа бота..."
docker compose build bot

# Запускаем бота
echo "🚀 Запуск бота..."
docker compose up -d bot

# Ждем немного
echo "⏳ Ожидание запуска (10 сек)..."
sleep 10

# Проверяем статус
echo ""
echo "📊 Проверка статуса:"
BOT_STATUS=$(docker ps --filter "name=bot" --format "{{.Status}}" 2>/dev/null)

if [[ $BOT_STATUS == *"Up"* ]] && [[ $BOT_STATUS != *"Restarting"* ]]; then
    echo "✅ Telegram Bot - работает!"
    echo ""
    echo "Проверьте работу бота, отправив ему команду /start"
else
    echo "❌ Telegram Bot - проблемы"
    echo "Статус: $BOT_STATUS"
    echo ""
    echo "Последние логи:"
    docker logs bot --tail 20
fi

echo ""
echo "Полезные команды:"
echo "  docker logs bot -f        # Смотреть логи в реальном времени"
echo "  docker ps                  # Проверить статус"
echo "  ./diagnose_and_fix.sh      # Диагностика"