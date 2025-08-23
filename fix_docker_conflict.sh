#!/bin/bash

# Скрипт для исправления конфликта с Docker контейнерами

echo "🔧 Исправление конфликта с Docker контейнерами..."
echo "📍 Запускать из корня проекта (где находится docker-compose.yml)"
echo ""

# Проверяем, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Ошибка: docker-compose.yml не найден в текущей директории"
    echo "📂 Пожалуйста, перейдите в корень проекта (не в langchain_api)"
    echo ""
    echo "Пример:"
    echo "  cd ~/marka"
    echo "  ./fix_docker_conflict.sh"
    exit 1
fi

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
containers=("app" "bot" "sandbox" "marka-redis" "graphiti")

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
echo "Теперь можно запустить из текущей директории:"
echo "  docker compose down"
echo "  docker compose build"
echo "  docker compose up -d"
echo ""
echo "Или если у вас старая версия Docker Compose:"
echo "  docker-compose down"
echo "  docker-compose build" 
echo "  docker-compose up -d"