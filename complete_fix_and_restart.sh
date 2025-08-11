#!/bin/bash

echo "🚀 ПОЛНОЕ ИСПРАВЛЕНИЕ ПРОЕКТА МАРК"
echo "==================================="
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Проверяем директорию
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ Ошибка: запустите из корня проекта${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Находимся в корне проекта${NC}"

# 2. Проверяем все созданные файлы
echo ""
echo "📁 Проверка созданных файлов..."

FILES_TO_CHECK=(
    "langchain_api/telegram_bot/__init__.py"
    "langchain_api/telegram_bot/handlers/__init__.py"
    "langchain_api/telegram_bot/services/memory_service.py"
    "langchain_api/telegram_bot/services/learning_service.py"
    "langchain_api/graphiti_service/utils.py"
)

ALL_FILES_OK=true
for file in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ $file${NC}"
    else
        echo -e "${RED}❌ Отсутствует: $file${NC}"
        ALL_FILES_OK=false
    fi
done

if [ "$ALL_FILES_OK" = false ]; then
    echo -e "${RED}Не все файлы созданы!${NC}"
    exit 1
fi

# 3. Проверяем requirements.txt
echo ""
echo "📋 Проверка зависимостей..."
if grep -q "neo4j>=5.23.0" langchain_api/requirements.txt; then
    echo -e "${GREEN}✅ neo4j версия исправлена${NC}"
else
    echo -e "${YELLOW}⚠️  Исправляю версию neo4j...${NC}"
    sed -i 's/neo4j==5.11.0/neo4j>=5.23.0/g' langchain_api/requirements.txt
fi

# 4. Останавливаем все контейнеры
echo ""
echo "🛑 Останавливаем контейнеры..."
docker compose down

# 5. Очищаем кэш Docker для проблемных образов
echo ""
echo "🧹 Очистка кэша Docker..."
docker rmi marka-bot marka-app 2>/dev/null || true

# 6. Перестраиваем образы
echo ""
echo "🔨 Перестройка Docker образов..."
echo "Это может занять несколько минут..."
docker compose build --no-cache bot app

# 7. Запускаем все сервисы
echo ""
echo "🚀 Запуск всех сервисов..."
docker compose up -d

# 8. Ждем инициализации
echo ""
echo "⏳ Ожидание полной инициализации (45 сек)..."
for i in {1..45}; do
    echo -n "."
    sleep 1
done
echo ""

# 9. Финальная проверка
echo ""
echo "📊 ФИНАЛЬНАЯ ПРОВЕРКА:"
echo "====================="

# Функция для проверки статуса контейнера
check_container() {
    local name=$1
    local status=$(docker ps --filter "name=$name" --format "{{.Status}}" 2>/dev/null)
    
    if [[ -z "$status" ]]; then
        echo -e "${RED}❌ $name - не найден${NC}"
        return 1
    elif [[ $status == *"Up"* ]] && [[ $status != *"Restarting"* ]]; then
        echo -e "${GREEN}✅ $name - работает${NC}"
        return 0
    else
        echo -e "${RED}❌ $name - проблемы (${status})${NC}"
        return 1
    fi
}

# Проверяем все контейнеры
CONTAINERS=("app" "bot" "graphiti" "graphiti-neo4j" "marka-redis" "sandbox")
ALL_OK=true

for container in "${CONTAINERS[@]}"; do
    if ! check_container "$container"; then
        ALL_OK=false
        
        # Показываем логи для проблемных контейнеров
        if [[ "$container" == "bot" ]] || [[ "$container" == "graphiti" ]]; then
            echo "   Последние логи:"
            docker logs "$container" --tail 5 2>&1 | sed 's/^/   /'
        fi
    fi
done

# 10. Проверка сервисов
echo ""
echo "🔍 Проверка доступности сервисов:"

# API
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ API - http://localhost:8000${NC}"
else
    echo -e "${RED}❌ API не отвечает${NC}"
fi

# Graphiti
if curl -s http://localhost:7878/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Graphiti - http://localhost:7878${NC}"
else
    echo -e "${RED}❌ Graphiti не отвечает${NC}"
fi

# Neo4j
if curl -s http://localhost:7474 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Neo4j UI - http://localhost:7474${NC}"
else
    echo -e "${RED}❌ Neo4j не отвечает${NC}"
fi

# 11. Итоговый статус
echo ""
echo "=================================="
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}✨ ВСЕ СЕРВИСЫ РАБОТАЮТ!${NC}"
    echo ""
    echo "Проект Марк полностью готов к использованию!"
    echo ""
    echo "Доступные сервисы:"
    echo "- API: http://localhost:8000"
    echo "- API Docs: http://localhost:8000/docs"
    echo "- Graphiti: http://localhost:7878"
    echo "- Neo4j: http://localhost:7474"
    echo ""
    echo "Telegram бот готов к работе!"
else
    echo -e "${YELLOW}⚠️  Некоторые сервисы требуют внимания${NC}"
    echo ""
    echo "Рекомендации:"
    echo "1. Проверьте логи: docker compose logs -f"
    echo "2. Для работы без бота: docker stop bot"
    echo "3. Проверьте .env файл"
fi

echo ""
echo "Полезные команды:"
echo "  docker compose ps          # Статус контейнеров"
echo "  docker compose logs -f     # Все логи"
echo "  docker logs bot -f         # Логи бота"
echo "  ./diagnose_and_fix.sh      # Диагностика"