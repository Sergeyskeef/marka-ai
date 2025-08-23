#!/bin/bash

echo "🔍 Проверка ошибок в контейнерах..."
echo ""

# Проверяем логи bot
echo "📱 Telegram Bot логи:"
echo "========================"
docker logs bot --tail 20
echo ""

# Проверяем логи graphiti
echo "🧠 Graphiti логи:"
echo "========================"
docker logs graphiti --tail 20
echo ""

# Проверяем .env файл
echo "📄 Проверка .env файла:"
echo "========================"
if [ -f ".env" ]; then
    echo "✅ .env файл найден"
    # Проверяем ключевые переменные
    if grep -q "BOT_TOKEN=" .env; then
        echo "✅ BOT_TOKEN установлен"
    else
        echo "❌ BOT_TOKEN НЕ установлен"
    fi
    
    if grep -q "OPENAI_API_KEY=" .env; then
        echo "✅ OPENAI_API_KEY установлен"
    else
        echo "❌ OPENAI_API_KEY НЕ установлен"
    fi
    
    if grep -q "NEO4J_PASSWORD=" .env; then
        echo "✅ NEO4J_PASSWORD установлен"
    else
        echo "❌ NEO4J_PASSWORD НЕ установлен"
    fi
else
    echo "❌ .env файл НЕ найден!"
    echo "   Создайте его командой: cp .env.example .env"
fi

echo ""
echo "💡 Подсказки:"
echo "- Если BOT_TOKEN не установлен, бот не сможет запуститься"
echo "- Если OPENAI_API_KEY не установлен, API не будет работать"
echo "- Проверьте логи выше для деталей ошибок"