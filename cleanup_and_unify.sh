#!/bin/bash
set -e

echo "🧹 Начинаем очистку и унификацию проекта..."

# 1. Сохраняем .gitignore
git add .gitignore
git commit -m "Update .gitignore with comprehensive rules" || true

# 2. Переносим новые модули в langchain_api
echo "📦 Переносим новые модули..."
mkdir -p langchain_api/app/prompts
mkdir -p langchain_api/app/api
mkdir -p langchain_api/app/agents

# Копируем если существуют
[ -d "app/prompts" ] && cp -r app/prompts/* langchain_api/app/prompts/ 2>/dev/null || true
[ -f "app/config.py" ] && cp app/config.py langchain_api/app/ 2>/dev/null || true
[ -f "app/api/prompts_api.py" ] && cp app/api/prompts_api.py langchain_api/app/api/ 2>/dev/null || true
[ -f "app/agents/mark_agent.py" ] && cp app/agents/mark_agent.py langchain_api/app/agents/ 2>/dev/null || true
[ -f "app/agents/chat_handler.py" ] && cp app/agents/chat_handler.py langchain_api/app/agents/ 2>/dev/null || true

# Копируем новые скрипты
echo "📝 Копируем скрипты проверки..."
for script in health_check.py security_audit.py load_test.py pre_production_check.py deploy.sh smoke_tests.py; do
    [ -f "scripts/$script" ] && cp "scripts/$script" "langchain_api/scripts/" 2>/dev/null || true
done

# 3. Объединяем requirements.txt
echo "📋 Объединяем зависимости..."
if [ -f "requirements.txt" ] && [ -f "langchain_api/requirements.txt" ]; then
    cat requirements.txt langchain_api/requirements.txt | sort -u > /tmp/unified_req.txt
    # Добавляем недостающие
    echo "requests==2.32.3" >> /tmp/unified_req.txt
    echo "locust==2.20.0" >> /tmp/unified_req.txt
    echo "psutil==5.9.8" >> /tmp/unified_req.txt
    echo "colorama==0.4.6" >> /tmp/unified_req.txt
    sort -u /tmp/unified_req.txt > langchain_api/requirements.txt
fi

# 4. Удаляем дубликаты и мусор
echo "🗑️ Удаляем дубликаты..."
# Удаляем дублирующиеся директории
for dir in core sandbox tests telegram_bot utils memory monitoring templates migrations configs examples extras prompts docs; do
    [ -d "$dir" ] && rm -rf "$dir" 2>/dev/null || true
done

# Удаляем старые файлы
rm -f main.py.old_broken pytest.ini pyproject.toml 2>/dev/null || true
rm -f '=0.4' '=4.4.0' '=4.5.0' 2>/dev/null || true

# Удаляем Python файлы в корне (кроме тестовых)
find . -maxdepth 1 -name "*.py" -not -name "test_*.py" -delete 2>/dev/null || true

# Удаляем shell скрипты в корне (кроме текущего)
find . -maxdepth 1 -name "*.sh" -not -name "cleanup_and_unify.sh" -delete 2>/dev/null || true

# Удаляем json файлы (кроме важных)
find . -maxdepth 1 -name "*.json" -not -name "marka_passport.json" -delete 2>/dev/null || true

# 5. Исправляем docker-compose
echo "🐳 Обновляем docker-compose..."
if [ -f "langchain_api/docker-compose.yml" ]; then
    sed -i 's|\.:/app/langchain_api|.:/app|g' langchain_api/docker-compose.yml
fi

# 6. Создаем правильный .env.example
echo "📄 Создаем .env.example..."
cat > .env.example << 'EOF'
# OpenAI
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5-mini
OPENAI_TEMPERATURE=0.7

# Telegram Bot
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
BOT_DEV_MODE=true
ADMIN_USERS=

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password

# Redis
REDIS_URL=redis://localhost:6379

# Graphiti
GRAPHITI_URL=http://localhost:8005

# API
API_BASE_URL=http://localhost:8000
EOF

# 7. Очищаем app/ если она больше не нужна
if [ -d "app" ]; then
    # Проверяем, остались ли там уникальные файлы
    remaining=$(find app -type f -name "*.py" 2>/dev/null | wc -l)
    if [ "$remaining" -eq 0 ] || [ "$remaining" -le 2 ]; then
        rm -rf app
    fi
fi

echo "✅ Очистка завершена!"
echo ""
echo "📁 Структура проекта:"
ls -la | grep -E "^d|^-.*\.(md|txt|yml|yaml|json)$|\.env|\.git"
echo ""
echo "📦 Основной код теперь в: langchain_api/"
echo ""
echo "🚀 Следующие шаги:"
echo "1. git add -A"
echo "2. git commit -m 'Major cleanup: unified project structure'"
echo "3. git push origin feature/agent-optimization-research"
echo "4. cd langchain_api && docker compose up -d"