#!/usr/bin/env bash
# Скрипт для перезапуска Docker-контейнеров после внесения изменений

# Установка правильных прав для скрипта
chmod +x restart_containers.sh

# Выводим информацию о текущем состоянии
echo "🔍 Текущее состояние контейнеров:"
docker compose ps

# Останавливаем контейнеры
echo "🛑 Останавливаем контейнеры..."
docker compose down

# Небольшая пауза
sleep 2

# Запускаем контейнеры заново
echo "🚀 Запускаем контейнеры..."
docker compose up -d

# Ждем инициализации
echo "⏳ Ожидаем инициализации контейнеров..."
sleep 10

# Проверяем состояние
echo "✅ Проверяем состояние после перезапуска:"
docker compose ps

# Проверяем логи с ошибками
echo "🔎 Проверяем логи на наличие ошибок..."
docker compose logs --tail=20 app | grep -i error
docker compose logs --tail=20 weaviate | grep -i error

echo "✨ Готово! Контейнеры перезапущены."
echo "📝 Для просмотра полных логов используйте: docker compose logs -f" 