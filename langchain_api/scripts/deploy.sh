#!/bin/bash
#
# Скрипт деплоя Mark AI на продакшен сервер
# Использование: ./deploy.sh [staging|production]
#

set -e  # Останавливаемся при любой ошибке

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Конфигурация
ENVIRONMENT=${1:-staging}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROJECT_NAME="mark-ai"

# Проверка окружения
if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
    echo -e "${RED}❌ Неверное окружение: $ENVIRONMENT${NC}"
    echo "Использование: ./deploy.sh [staging|production]"
    exit 1
fi

echo -e "${BLUE}🚀 Деплой Mark AI на $ENVIRONMENT${NC}"
echo -e "${BLUE}Время: $(date)${NC}"

# 1. Предпродакшен проверка
echo -e "\n${YELLOW}📋 Шаг 1: Предпродакшен проверка${NC}"
if ! python scripts/pre_production_check.py; then
    echo -e "${RED}❌ Предпродакшен проверка не пройдена!${NC}"
    exit 1
fi

# 2. Создание backup конфигурации
echo -e "\n${YELLOW}📦 Шаг 2: Создание backup${NC}"
BACKUP_DIR="backups/${TIMESTAMP}"
mkdir -p "$BACKUP_DIR"

# Сохраняем текущую конфигурацию
cp .env "$BACKUP_DIR/.env.backup" 2>/dev/null || true
cp -r data/ "$BACKUP_DIR/data.backup" 2>/dev/null || true
echo -e "${GREEN}✅ Backup создан в $BACKUP_DIR${NC}"

# 3. Сборка Docker образов
echo -e "\n${YELLOW}🐳 Шаг 3: Сборка Docker образов${NC}"
cd langchain_api
docker compose build --no-cache
docker compose push  # Если используется registry
cd ..

# 4. Применение конфигурации окружения
echo -e "\n${YELLOW}⚙️  Шаг 4: Применение конфигурации${NC}"
if [ "$ENVIRONMENT" == "production" ]; then
    cp .env.production .env
    export BOT_DEV_MODE=false
else
    cp .env.staging .env
    export BOT_DEV_MODE=true
fi

# 5. Запуск миграций
echo -e "\n${YELLOW}🔄 Шаг 5: Миграции (если есть)${NC}"
# Здесь можно добавить миграции для Neo4j или других БД
echo "Миграции не требуются"

# 6. Остановка старой версии
echo -e "\n${YELLOW}🛑 Шаг 6: Остановка старой версии${NC}"
cd langchain_api
docker compose down --remove-orphans
cd ..

# 7. Запуск новой версии
echo -e "\n${YELLOW}▶️  Шаг 7: Запуск новой версии${NC}"
cd langchain_api
docker compose up -d

# Ждем запуска контейнеров
echo "Ожидание запуска контейнеров..."
sleep 10

# 8. Health check после деплоя
echo -e "\n${YELLOW}🏥 Шаг 8: Health check${NC}"
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f http://localhost:8001/health >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Сервис запущен и работает${NC}"
        break
    else
        echo "Ожидание запуска сервиса... ($((RETRY_COUNT+1))/$MAX_RETRIES)"
        sleep 2
        RETRY_COUNT=$((RETRY_COUNT+1))
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}❌ Сервис не запустился!${NC}"
    echo "Откат к предыдущей версии..."
    
    # Откат
    docker compose down
    cp "$BACKUP_DIR/.env.backup" .env
    docker compose up -d
    
    exit 1
fi

# 9. Smoke тесты
echo -e "\n${YELLOW}🔥 Шаг 9: Smoke тесты${NC}"
python scripts/smoke_tests.py || {
    echo -e "${RED}❌ Smoke тесты не прошли!${NC}"
    # Здесь можно добавить откат
    exit 1
}

# 10. Мониторинг
echo -e "\n${YELLOW}📊 Шаг 10: Настройка мониторинга${NC}"
# Проверяем метрики Prometheus
if curl -f http://localhost:8001/metrics >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Метрики Prometheus доступны${NC}"
else
    echo -e "${YELLOW}⚠️  Метрики Prometheus не доступны${NC}"
fi

# Логи
cd ..
echo -e "\n${BLUE}📋 Последние логи:${NC}"
cd langchain_api
docker compose logs --tail=50
cd ..

# Итоговый отчет
echo -e "\n${GREEN}✅ ДЕПЛОЙ УСПЕШНО ЗАВЕРШЕН!${NC}"
echo -e "${BLUE}📊 Итоговая информация:${NC}"
echo "  - Окружение: $ENVIRONMENT"
echo "  - Время деплоя: $(date)"
echo "  - Backup: $BACKUP_DIR"
echo "  - Версия: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

echo -e "\n${BLUE}📋 Дальнейшие действия:${NC}"
echo "  1. Проверьте логи: docker compose -f langchain_api/docker-compose.yml logs -f"
echo "  2. Проверьте метрики: http://localhost:8001/metrics"
echo "  3. Проверьте API документацию: http://localhost:8001/docs"
echo "  4. Протестируйте бота в Telegram"

# Уведомление (опционально)
# curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
#      -d "chat_id=$ADMIN_CHAT_ID" \
#      -d "text=✅ Mark AI успешно задеплоен на $ENVIRONMENT!"

exit 0