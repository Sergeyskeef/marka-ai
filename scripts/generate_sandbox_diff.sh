#!/usr/bin/env bash
# Скрипт для генерации diff-отчёта между песочницей и основной директорией
# Запускать из корня проекта: bash langchain_api/scripts/generate_sandbox_diff.sh

set -e

REPORT="sandbox_diff_report.txt"

# Проверка директории запуска
if [[ ! -d "langchain_api" || ! -f "langchain_api/scripts/generate_sandbox_diff.sh" ]]; then
  echo "❌ Скрипт нужно запускать из корня проекта (где лежит папка langchain_api)!"
  exit 1
fi

# Получаем diff между основной директорией и песочницей (в контейнере sandbox) с фильтрацией лишних файлов
echo "🔍 Генерируем diff между основной директорией и песочницей (только исходники и важные конфиги)..."
docker compose -f langchain_api/docker-compose.yml exec sandbox bash -c "cd /workspace && diff -ruN \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='logs' \
  --exclude='*.log' \
  --exclude='*.db' \
  --exclude='*.json' \
  --exclude='*.graphml' \
  --exclude='*.cache' \
  --exclude='*.pyc' \
  --exclude='*.pkl' \
  --exclude='*.sqlite' \
  --exclude='*.parquet' \
  --exclude='*.csv' \
  --exclude='*.md' \
  --exclude='*.ipynb' \
  langchain_api /src/langchain_api || true" > $REPORT

# Логируем событие
python3 langchain_api/scripts/log_sandbox_event.py DIFF "Сгенерирован diff-отчёт между песочницей и основной директорией (фильтрован)" SUCCESS

# Логируем событие в дневник пробуждения
python3 langchain_api/scripts/log_awakening_event.py DIFF "Сгенерирован diff-отчёт между песочницей и основной директорией" SUCCESS

echo "✅ Diff-отчёт сохранён в $REPORT (фильтрован)" 