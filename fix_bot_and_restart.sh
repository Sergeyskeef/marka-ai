#!/bin/bash

echo "🚀 ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ БОТА"
echo "=============================="
echo ""

# Проверяем директорию
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Запустите из корня проекта"
    exit 1
fi

echo "✅ Исправления применены:"
echo "  - Исправлен endpoint: /api/chat вместо /chat/enhanced"
echo "  - Исправлен формат запроса и ответа"
echo "  - Добавлена поддержка обоих форматов API"
echo ""

# Останавливаем только бота
echo "🛑 Останавливаем бота..."
docker stop bot

# Ждем немного
sleep 2

# Запускаем бота заново
echo "🚀 Запускаем бота..."
docker start bot

# Ждем инициализацию
echo "⏳ Ожидание запуска (10 сек)..."
for i in {1..10}; do
    echo -n "."
    sleep 1
done
echo ""

# Проверяем статус
echo ""
echo "📊 Статус:"
status=$(docker ps --filter "name=bot" --format "{{.Status}}" | head -n1)
if [[ $status == *"Up"* ]] && [[ $status != *"Restarting"* ]]; then
    echo "✅ Telegram Bot работает!"
else
    echo "❌ Проблемы с ботом"
    echo "Последние логи:"
    docker logs bot --tail 10
fi

echo ""
echo "🎯 Готово!"
echo ""
echo "Теперь бот должен отвечать на сообщения!"
echo ""
echo "📱 Проверьте в Telegram:"
echo "  - Отправьте /start"
echo "  - Напишите любое сообщение"
echo "  - Попробуйте разные режимы чата"