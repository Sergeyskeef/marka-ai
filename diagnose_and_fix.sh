#!/bin/bash

echo "🔧 Диагностика и исправление проблем с контейнерами..."
echo ""

# Функция для проверки переменной в .env
check_env_var() {
    local var_name=$1
    if [ -f ".env" ]; then
        if grep -q "^${var_name}=" .env && ! grep -q "^${var_name}=$" .env && ! grep -q "^${var_name}=your_" .env; then
            return 0
        fi
    fi
    return 1
}

# 1. Проверяем .env файл
echo "📄 Проверка конфигурации..."
if [ ! -f ".env" ]; then
    echo "❌ .env файл не найден!"
    if [ -f ".env.example" ]; then
        echo "📝 Создаю .env из примера..."
        cp .env.example .env
        echo "✅ .env создан. Пожалуйста, отредактируйте его и добавьте:"
        echo "   - OPENAI_API_KEY"
        echo "   - BOT_TOKEN (если нужен Telegram бот)"
        echo "   - NEO4J_PASSWORD"
    fi
else
    echo "✅ .env файл найден"
fi

# 2. Проверяем необходимые переменные
echo ""
echo "🔑 Проверка ключей API..."

MISSING_VARS=()

if ! check_env_var "OPENAI_API_KEY"; then
    echo "❌ OPENAI_API_KEY не установлен или пустой"
    MISSING_VARS+=("OPENAI_API_KEY")
else
    echo "✅ OPENAI_API_KEY установлен"
fi

if ! check_env_var "BOT_TOKEN"; then
    echo "⚠️  BOT_TOKEN не установлен (бот не будет работать)"
    MISSING_VARS+=("BOT_TOKEN")
else
    echo "✅ BOT_TOKEN установлен"
fi

if ! check_env_var "NEO4J_PASSWORD"; then
    echo "⚠️  NEO4J_PASSWORD не установлен (используется значение по умолчанию)"
else
    echo "✅ NEO4J_PASSWORD установлен"
fi

# 3. Проверяем логи проблемных контейнеров
echo ""
echo "📋 Анализ ошибок..."

# Проверяем бота
BOT_STATUS=$(docker ps --filter "name=bot" --format "{{.Status}}")
if [[ $BOT_STATUS == *"Restarting"* ]]; then
    echo ""
    echo "🤖 Telegram Bot - ОШИБКА (перезапускается)"
    echo "Последние логи:"
    docker logs bot --tail 10 2>&1 | grep -E "(ERROR|Error|error|Exception|Traceback)" | head -5
    
    if ! check_env_var "BOT_TOKEN"; then
        echo "💡 Решение: Добавьте BOT_TOKEN в .env файл"
    fi
fi

# Проверяем graphiti
GRAPHITI_STATUS=$(docker ps --filter "name=graphiti" --format "{{.Status}}")
if [[ $GRAPHITI_STATUS == *"Restarting"* ]]; then
    echo ""
    echo "🧠 Graphiti - ОШИБКА (перезапускается)"
    echo "Последние логи:"
    docker logs graphiti --tail 10 2>&1 | grep -E "(ERROR|Error|error|Exception|Traceback)" | head -5
fi

# 4. Предложения по исправлению
echo ""
echo "📝 Рекомендации:"

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo ""
    echo "1. Отредактируйте .env файл и установите следующие переменные:"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
fi

echo ""
echo "2. Если бот не нужен, можете остановить его:"
echo "   docker stop bot"
echo ""
echo "3. Для перезапуска всех сервисов:"
echo "   docker compose down"
echo "   docker compose up -d"
echo ""
echo "4. Для работы без бота, закомментируйте сервис 'bot' в docker-compose.yml"

# 5. Проверка работающих сервисов
echo ""
echo "✅ Статус работающих сервисов:"
echo ""

# API
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "🟢 API (FastAPI) - работает на http://localhost:8000"
else
    echo "🔴 API (FastAPI) - не отвечает"
fi

# Neo4j
if curl -s http://localhost:7474 > /dev/null 2>&1; then
    echo "🟢 Neo4j UI - доступен на http://localhost:7474"
else
    echo "🔴 Neo4j UI - не отвечает"
fi

# Redis
if docker exec marka-redis redis-cli ping > /dev/null 2>&1; then
    echo "🟢 Redis - работает"
else
    echo "🔴 Redis - не отвечает"
fi

echo ""
echo "🎯 Готово!"