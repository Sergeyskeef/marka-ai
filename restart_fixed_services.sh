#!/bin/bash

echo "🔄 Перезапуск исправленных сервисов..."
echo ""

# Перестраиваем и перезапускаем только проблемные контейнеры
echo "📦 Перестройка контейнеров bot и graphiti..."
docker compose build bot graphiti

echo ""
echo "🚀 Перезапуск контейнеров..."
docker compose up -d bot graphiti

echo ""
echo "⏳ Ожидание запуска (10 сек)..."
sleep 10

echo ""
echo "📊 Проверка статуса:"
docker compose ps

echo ""
echo "📝 Последние логи bot:"
docker logs bot --tail 5

echo ""
echo "📝 Последние логи graphiti:"
docker logs graphiti --tail 5

echo ""
echo "✅ Готово!"
echo ""
echo "Если все еще есть ошибки, запустите:"
echo "  docker logs bot --tail 50"
echo "  docker logs graphiti --tail 50"