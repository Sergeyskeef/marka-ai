#!/bin/bash

echo "🔒 ЗАЩИТА REDIS ОТ ВНЕШНИХ АТАК v2"
echo "===================================="
echo ""

# Проверяем, что Redis работает
if ! docker ps | grep -q marka-redis; then
    echo "❌ Redis контейнер не запущен"
    exit 1
fi

echo "⚠️  ВНИМАНИЕ: Обнаружена попытка взлома Redis!"
echo "Атакующие IP: 47.93.126.234, 115.190.75.178, 115.190.22.39"
echo ""

# 1. Проверяем текущий статус
echo "📊 Текущий статус репликации:"
docker exec marka-redis redis-cli INFO replication | grep -E "role:|connected_slaves:|master_host:"

# 2. Отключаем репликацию
echo ""
echo "🛡️ Отключаем репликацию..."
docker exec marka-redis redis-cli SLAVEOF NO ONE

# 3. Добавляем пароль в .env если его нет
if [ -f .env ]; then
    if ! grep -q "REDIS_PASSWORD=" .env; then
        echo ""
        echo "⚠️  Добавляем REDIS_PASSWORD в .env..."
        REDIS_PASS=$(openssl rand -base64 32)
        echo "REDIS_PASSWORD=$REDIS_PASS" >> .env
        echo "✅ Пароль добавлен в .env"
    fi
fi

# 4. Обновляем docker-compose.yml для Redis с паролем
echo ""
echo "📝 Рекомендуемая конфигурация для docker-compose.yml:"
echo ""
echo "  redis:"
echo "    image: redis:7-alpine"
echo "    container_name: marka-redis"
echo "    command: redis-server --requirepass \${REDIS_PASSWORD:-defaultpass} --bind 127.0.0.1 ::1"
echo "    ports:"
echo "      - \"127.0.0.1:6379:6379\"  # Только локальный доступ!"
echo "    volumes:"
echo "      - redis_data:/data"
echo "    healthcheck:"
echo "      test: [\"CMD\", \"redis-cli\", \"--pass\", \"\${REDIS_PASSWORD:-defaultpass}\", \"ping\"]"
echo ""

# 5. Проверяем файрвол
echo "🔥 Проверка файрвола..."
if command -v ufw &> /dev/null; then
    echo "UFW статус:"
    sudo ufw status | grep 6379 || echo "✅ Порт 6379 не открыт в UFW"
else
    echo "⚠️  UFW не установлен"
fi

if command -v iptables &> /dev/null; then
    echo ""
    echo "iptables правила для порта 6379:"
    sudo iptables -L -n | grep 6379 || echo "✅ Нет открытых правил для 6379"
fi

# 6. Блокируем атакующие IP
echo ""
echo "🚫 Блокировка атакующих IP..."
ATTACKER_IPS="47.93.126.234 115.190.75.178 115.190.22.39"

for ip in $ATTACKER_IPS; do
    if command -v ufw &> /dev/null; then
        sudo ufw deny from $ip comment "Redis attacker" 2>/dev/null && echo "✅ Заблокирован $ip через UFW"
    fi
    
    if command -v iptables &> /dev/null; then
        sudo iptables -A INPUT -s $ip -j DROP 2>/dev/null && echo "✅ Заблокирован $ip через iptables"
    fi
done

# 7. Проверяем результат
echo ""
echo "🔍 Финальная проверка:"
docker exec marka-redis redis-cli INFO replication | grep "role:master"
if [ $? -eq 0 ]; then
    echo "✅ Redis работает как master (не slave)!"
else
    echo "❌ Проверьте статус Redis!"
fi

echo ""
echo "📋 ВАЖНЫЕ РЕКОМЕНДАЦИИ:"
echo "1. Перезапустите Redis с новой конфигурацией:"
echo "   docker compose down redis"
echo "   docker compose up -d redis"
echo ""
echo "2. Обновите конфигурацию приложения для использования пароля Redis"
echo ""
echo "3. СРОЧНО закройте порт 6379 для внешнего доступа!"
echo "   Используйте только 127.0.0.1:6379 в docker-compose.yml"
echo ""
echo "4. Рассмотрите использование VPN или SSH туннеля для доступа"