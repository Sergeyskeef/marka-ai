#!/bin/bash
# Автоматические исправления для проекта Марк

echo "🔧 Применение исправлений..."

# 1. Исправление импортов в telegram_bot
echo "📦 Исправление импортов..."

# Создаем __init__.py где необходимо
touch /workspace/langchain_api/telegram_bot/__init__.py
touch /workspace/langchain_api/telegram_bot/handlers/__init__.py
touch /workspace/langchain_api/telegram_bot/services/__init__.py
touch /workspace/langchain_api/telegram_bot/middleware/__init__.py
touch /workspace/langchain_api/telegram_bot/keyboards/__init__.py

# 2. Обновляем Dockerfile для правильных импортов
echo "🐳 Обновление Dockerfile..."
cat > /workspace/langchain_api/telegram_bot/Dockerfile.fixed << 'EOF'
FROM python:3.10-slim
WORKDIR /app

# Копируем весь проект
COPY . /app/langchain_api/

# Устанавливаем зависимости
WORKDIR /app/langchain_api
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir python-telegram-bot==21.0 aiohttp[speedups]

# Устанавливаем PYTHONPATH для корректных импортов
ENV PYTHONPATH=/app/langchain_api

# Запускаем бота из корня langchain_api
WORKDIR /app/langchain_api
CMD ["python", "-m", "telegram_bot.main"]
EOF

echo "✅ Исправления готовы!"
echo ""
echo "Для применения:"
echo "1. mv /workspace/langchain_api/telegram_bot/Dockerfile.fixed /workspace/langchain_api/telegram_bot/Dockerfile"
echo "2. docker compose build bot"
echo "3. docker compose up -d bot"
