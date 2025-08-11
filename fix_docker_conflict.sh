#!/bin/bash

# Скрипт для исправления конфликта с Docker контейнерами

echo "🔧 Исправление конфликта с Docker контейнерами..."

# Проверяем, запущен ли конфликтующий контейнер
if docker ps -a | grep -q "graphiti-neo4j"; then
    echo "⚠️  Найден существующий контейнер graphiti-neo4j"
    
    # Останавливаем контейнер
    echo "🛑 Останавливаем контейнер..."
    docker stop graphiti-neo4j 2>/dev/null || true
    
    # Удаляем контейнер
    echo "🗑️  Удаляем контейнер..."
    docker rm graphiti-neo4j 2>/dev/null || true
    
    echo "✅ Контейнер удален"
else
    echo "✅ Конфликтующий контейнер не найден"
fi

# Проверяем другие потенциально конфликтующие контейнеры
containers=("app" "bot" "sandbox" "marka-redis")

for container in "${containers[@]}"; do
    if docker ps -a | grep -q "$container"; then
        echo "⚠️  Найден контейнер $container, удаляем..."
        docker stop "$container" 2>/dev/null || true
        docker rm "$container" 2>/dev/null || true
    fi
done

echo ""
echo "✨ Все конфликты устранены!"
echo ""
echo "Теперь можно запустить:"
echo "  docker compose build"
echo "  docker compose up -d"