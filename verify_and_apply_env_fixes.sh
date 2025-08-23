#!/bin/bash

echo "🔧 ПРОВЕРКА И ПРИМЕНЕНИЕ ИСПРАВЛЕНИЙ .env"
echo "========================================="
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка наличия .env
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Файл .env не найден!${NC}"
    exit 1
fi

echo "📋 Проверка конфигурации:"
echo ""

# Проверка критических переменных
check_var() {
    local var_name=$1
    local var_value=$(grep "^${var_name}=" .env | cut -d'=' -f2-)
    
    if [ -z "$var_value" ]; then
        echo -e "${RED}❌ ${var_name} - НЕ УСТАНОВЛЕН${NC}"
        return 1
    else
        # Скрываем часть значения для безопасности
        if [[ "$var_name" == *"KEY"* ]] || [[ "$var_name" == *"TOKEN"* ]] || [[ "$var_name" == *"PASSWORD"* ]]; then
            echo -e "${GREEN}✅ ${var_name} - установлен (${#var_value} символов)${NC}"
        else
            echo -e "${GREEN}✅ ${var_name} = ${var_value}${NC}"
        fi
        return 0
    fi
}

# Проверяем все критические переменные
echo "🔑 Основные переменные:"
check_var "OPENAI_API_KEY"
check_var "OPENAI_MODEL"
check_var "TELEGRAM_BOT_TOKEN"
check_var "REDIS_PASSWORD"

echo ""
echo "🌐 Прокси настройки:"
check_var "HTTP_PROXY"
check_var "HTTPS_PROXY"
check_var "NO_PROXY"

echo ""
echo "🔗 URL сервисов:"
check_var "NEO4J_URI"
check_var "REDIS_URL"
check_var "GRAPHITI_URL"
check_var "LANGSERVE_URL"

echo ""
echo "🔍 Проверка портов в docker-compose.yml:"

# Проверка соответствия портов
GRAPHITI_PORT_ENV=$(grep "GRAPHITI_API_PORT=" .env | cut -d'=' -f2)
GRAPHITI_PORT_COMPOSE=$(grep -A5 "graphiti:" docker-compose.yml | grep "GRAPHITI_API_PORT" | grep -oE '[0-9]+')

if [ "$GRAPHITI_PORT_ENV" == "$GRAPHITI_PORT_COMPOSE" ]; then
    echo -e "${GREEN}✅ Порт Graphiti согласован: $GRAPHITI_PORT_ENV${NC}"
else
    echo -e "${YELLOW}⚠️  Порт Graphiti не согласован: .env=$GRAPHITI_PORT_ENV, docker-compose=$GRAPHITI_PORT_COMPOSE${NC}"
fi

echo ""
echo "📊 Итоговая статистика:"

# Подсчет переменных
TOTAL_VARS=$(grep -E "^[A-Z_]+=" .env | wc -l)
echo "  Всего переменных: $TOTAL_VARS"

# Проверка дубликатов
DUPLICATES=$(grep -E "^[A-Z_]+=" .env | cut -d'=' -f1 | sort | uniq -d)
if [ -z "$DUPLICATES" ]; then
    echo -e "  ${GREEN}✅ Дубликаты не найдены${NC}"
else
    echo -e "  ${RED}❌ Найдены дубликаты: $DUPLICATES${NC}"
fi

echo ""
echo "🚀 Применение настроек:"
echo ""

# Перезапуск сервисов с новыми настройками
echo "Перезапускаем сервисы для применения новых настроек..."
docker compose restart app bot redis

echo ""
echo "✅ Готово!"
echo ""
echo "📝 Рекомендации:"
echo "  1. Проверьте логи сервисов: docker compose logs -f app bot redis"
echo "  2. Протестируйте бота в Telegram"
echo "  3. Убедитесь, что Redis защищен паролем"
echo ""
echo "🔐 Для проверки Redis с паролем:"
echo "  docker exec -it marka-redis redis-cli --pass \$(grep REDIS_PASSWORD .env | cut -d'=' -f2) ping"