#!/bin/bash

echo "🔒 ЗАЩИТА REDIS ОТ ВНЕШНИХ АТАК"
echo "================================"
echo ""

# Проверяем, что Redis работает
if ! docker ps | grep -q marka-redis; then
    echo "❌ Redis контейнер не запущен"
    exit 1
fi

echo "⚠️  ВНИМАНИЕ: Обнаружена попытка взлома Redis!"
echo "Кто-то пытается превратить ваш Redis в slave-репликацию."
echo ""

echo "🛡️ Применяем защиту..."

# 1. Отключаем команду SLAVEOF
docker exec marka-redis redis-cli CONFIG SET rename-command "SLAVEOF ''"
docker exec marka-redis redis-cli CONFIG SET rename-command "REPLICAOF ''"

# 2. Устанавливаем пароль, если не установлен
if [ -f .env ] && grep -q "REDIS_PASSWORD=" .env; then
    REDIS_PASSWORD=$(grep "REDIS_PASSWORD=" .env | cut -d'=' -f2)
    echo "🔑 Устанавливаем пароль для Redis..."
    docker exec marka-redis redis-cli CONFIG SET requirepass "$REDIS_PASSWORD"
else
    echo "⚠️  REDIS_PASSWORD не найден в .env файле"
    echo "Добавьте в .env:"
    echo "REDIS_PASSWORD=your_secure_password_here"
fi

# 3. Отключаем опасные команды
echo "🚫 Отключаем опасные команды..."
docker exec marka-redis redis-cli CONFIG SET rename-command "FLUSHDB ''"
docker exec marka-redis redis-cli CONFIG SET rename-command "FLUSHALL ''"
docker exec marka-redis redis-cli CONFIG SET rename-command "CONFIG ''"

# 4. Сохраняем конфигурацию
docker exec marka-redis redis-cli BGSAVE

echo ""
echo "✅ Redis защищен!"
echo ""
echo "📋 Рекомендации:"
echo "1. Убедитесь, что порт 6379 закрыт во внешнем файрволе"
echo "2. Используйте только внутреннюю сеть Docker (marka_net)"
echo "3. Регулярно обновляйте Redis"
echo ""
echo "🔍 Проверка текущих подключений:"
docker exec marka-redis redis-cli CLIENT LIST