#!/bin/bash
# Script to verify all fixes are working

echo "🔍 Проверка исправлений Mark AI..."
echo "================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to langchain_api directory
cd /workspace/langchain_api || exit 1

# 1. Check if Field import is fixed
echo -e "\n1. Проверка импорта Field в config.py:"
if grep -q "from pydantic import Field" app/config.py; then
    echo -e "${GREEN}✅ Field импортирован корректно${NC}"
else
    echo -e "${RED}❌ Field не импортирован!${NC}"
fi

# 2. Check docker-compose.yml paths
echo -e "\n2. Проверка путей в docker-compose.yml:"
if grep -q "working_dir: /app/langchain_api" ../docker-compose.yml; then
    echo -e "${GREEN}✅ Working directory исправлен${NC}"
else
    echo -e "${RED}❌ Working directory не исправлен!${NC}"
fi

if grep -q 'command: \["python", "-m", "telegram_bot.main"\]' ../docker-compose.yml; then
    echo -e "${GREEN}✅ Command исправлен${NC}"
else
    echo -e "${RED}❌ Command не исправлен!${NC}"
fi

# 3. Check .env.example exists
echo -e "\n3. Проверка .env.example:"
if [ -f "../.env.example" ]; then
    lines=$(wc -l < ../.env.example)
    echo -e "${GREEN}✅ .env.example существует ($lines строк)${NC}"
else
    echo -e "${RED}❌ .env.example не найден!${NC}"
fi

# 4. Check security audit script
echo -e "\n4. Проверка скрипта security audit:"
if [ -f "scripts/security_audit_modules.py" ]; then
    echo -e "${GREEN}✅ Security audit скрипт создан${NC}"
else
    echo -e "${RED}❌ Security audit скрипт не найден!${NC}"
fi

# 5. Check test coverage script
echo -e "\n5. Проверка скрипта test coverage:"
if [ -f "scripts/improve_test_coverage.py" ]; then
    echo -e "${GREEN}✅ Test coverage скрипт создан${NC}"
else
    echo -e "${RED}❌ Test coverage скрипт не найден!${NC}"
fi

# 6. Test bot build (without running)
echo -e "\n6. Проверка сборки бота:"
echo "   Выполняю: docker compose build bot"
if docker compose -f ../docker-compose.yml build bot > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Бот собирается успешно${NC}"
else
    echo -e "${RED}❌ Ошибка сборки бота!${NC}"
fi

# 7. Check if services are running
echo -e "\n7. Проверка запущенных сервисов:"
running_services=$(docker ps --format "table {{.Names}}" | tail -n +2)
if [ -n "$running_services" ]; then
    echo -e "${GREEN}✅ Запущенные сервисы:${NC}"
    echo "$running_services" | while read service; do
        echo "   - $service"
    done
else
    echo -e "${YELLOW}⚠️  Нет запущенных сервисов${NC}"
fi

# 8. Check bot status specifically
echo -e "\n8. Статус бота:"
bot_status=$(docker ps -a --filter "name=bot" --format "{{.Status}}" | head -1)
if [ -n "$bot_status" ]; then
    if [[ "$bot_status" == *"Up"* ]]; then
        echo -e "${GREEN}✅ Бот работает: $bot_status${NC}"
    else
        echo -e "${RED}❌ Бот не работает: $bot_status${NC}"
        echo "   Последние логи:"
        docker logs bot --tail 5 2>&1 | sed 's/^/   /'
    fi
else
    echo -e "${YELLOW}⚠️  Бот не найден${NC}"
fi

echo -e "\n================================="
echo "📊 Резюме проверки завершено"
echo ""
echo "💡 Следующие шаги:"
echo "1. Если бот не работает: docker compose down && docker compose up -d"
echo "2. Запустить security audit: cd langchain_api && python scripts/security_audit_modules.py"
echo "3. Проверить покрытие тестами: cd langchain_api && python scripts/improve_test_coverage.py"