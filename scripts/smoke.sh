#!/bin/bash

# Smoke test script for Mark mini-MVP
# Проверяет основные сервисы за 30 секунд
# Возвращает 0 если всё ок, иначе 1

set -e

echo "🚀 Запуск smoke test для Mark mini-MVP..."

# Проверка health endpoint
echo "📊 Проверка health endpoint..."
if ! curl -sf http://localhost:8000/health > /dev/null; then
    echo "❌ Health endpoint недоступен"
    exit 1
fi
echo "✅ Health endpoint работает"

# Проверка tools endpoint
echo "🛠️ Проверка tools endpoint..."
if ! curl -sf http://localhost:8000/tools | grep -q "run_code"; then
    echo "❌ Tools endpoint не содержит run_code"
    exit 1
fi
echo "✅ Tools endpoint работает"

# Проверка memory endpoint
echo "🧠 Проверка memory endpoint..."
if ! curl -sf -X POST http://localhost:8000/memory \
    -H "Content-Type: application/json" \
    -d '{"text":"ping"}' > /dev/null; then
    echo "❌ Memory endpoint недоступен"
    exit 1
fi
echo "✅ Memory endpoint работает"

echo "🎉 Все smoke тесты прошли успешно!"
echo "✅ Mark mini-MVP готов к работе"
exit 0 