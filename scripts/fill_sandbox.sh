#!/usr/bin/env bash
# Скрипт для наполнения песочницы (sandbox) свежей копией проекта
# Запускать ТОЛЬКО ИЗ КОРНЯ ПРОЕКТА (~/marka): bash langchain_api/scripts/fill_sandbox.sh

set -e

# Проверка директории запуска
if [[ ! -d "langchain_api" || ! -f "langchain_api/scripts/fill_sandbox.sh" ]]; then
  echo "❌ Скрипт нужно запускать из корня проекта (где лежит папка langchain_api)!"
  exit 1
fi

# Очищаем volume langchain_api_dev_sandbox
echo "🧹 Очищаем volume langchain_api_dev_sandbox..."
docker volume rm langchain_api_dev_sandbox 2>/dev/null || true

# Копируем весь проект в песочницу (исключая .git, __pycache__, .pytest_cache, logs)
echo "📦 Копируем проект в песочницу..."
docker run --rm -v $(pwd):/src -v langchain_api_dev_sandbox:/workspace alpine sh -c "cd /src && tar cf - . --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='logs' | tar xf - -C /workspace"

echo "✅ Песочница готова! Теперь можно запускать сервисы внутри контейнера sandbox." 