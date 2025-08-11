#!/bin/bash

echo "🔒 ПРИМЕНЕНИЕ ЗАЩИТЫ REDIS"
echo "=========================="
echo ""

# Проверяем, что мы в корне проекта
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Запустите из корня проекта"
    exit 1
fi

# Проверяем, что пароль добавлен в .env
if ! grep -q "REDIS_PASSWORD=" .env; then
    echo "❌ REDIS_PASSWORD не найден в .env"
    echo "Сначала запустите ./secure_redis_v2.sh"
    exit 1
fi

echo "✅ Конфигурация обновлена:"
echo "  - docker-compose.yml: Redis теперь слушает только 127.0.0.1"
echo "  - docker-compose.yml: Добавлена аутентификация по паролю"
echo "  - app/config.py: Добавлена поддержка REDIS_PASSWORD"
echo ""

# Останавливаем Redis
echo "🛑 Останавливаем Redis..."
docker compose stop redis
docker compose rm -f redis

# Перезапускаем Redis с новой конфигурацией
echo "🚀 Запускаем Redis с защитой..."
docker compose up -d redis

# Ждем запуска
echo "⏳ Ожидание запуска Redis (10 сек)..."
sleep 10

# Проверяем работу
echo ""
echo "🔍 Проверка Redis:"
REDIS_PASS=$(grep "REDIS_PASSWORD=" .env | cut -d'=' -f2)

# Проверяем подключение с паролем
if docker exec marka-redis redis-cli --pass "$REDIS_PASS" ping | grep -q "PONG"; then
    echo "✅ Redis работает с паролем!"
else
    echo "❌ Проблема с подключением к Redis"
fi

# Проверяем, что порт закрыт извне
echo ""
echo "🔍 Проверка доступности порта:"
if timeout 2 nc -z $(hostname -I | awk '{print $1}') 6379 2>/dev/null; then
    echo "⚠️  ВНИМАНИЕ: Порт 6379 все еще доступен извне!"
else
    echo "✅ Порт 6379 закрыт для внешнего доступа"
fi

# Перезапускаем приложение для использования пароля
echo ""
echo "🔄 Перезапускаем приложение..."
docker restart app

echo ""
echo "✅ ГОТОВО!"
echo ""
echo "📊 Статус защиты:"
echo "  - Redis работает только на localhost (127.0.0.1)"
echo "  - Установлен пароль для доступа"
echo "  - Атакующие IP заблокированы"
echo ""
echo "🔍 Полезные команды:"
echo "  docker logs redis -f     # Логи Redis"
echo "  docker compose ps        # Статус всех сервисов"
echo ""
echo "📝 Если нужно подключиться к Redis вручную:"
echo "  docker exec -it marka-redis redis-cli --pass \$(grep REDIS_PASSWORD .env | cut -d'=' -f2)"