#!/usr/bin/env bash
# Скрипт для наполнения песочницы (sandbox) свежей копией проекта
# Запускать ТОЛЬКО ИЗ КОРНЯ ПРОЕКТА (~/marka): bash langchain_api/scripts/fill_sandbox.sh

set -e

# Проверка директории запуска
if [[ ! -d "langchain_api" || ! -f "langchain_api/scripts/fill_sandbox.sh" ]]; then
  echo "❌ Скрипт нужно запускать из корня проекта (где лежит папка langchain_api)!"
  exit 1
fi

# ВНИМАНИЕ: Ранее скрипт удалял том песочницы. Теперь мы сохраняем данные.
# Если нужно принудительно очистить песочницу, передайте флаг --reset.
VOLUME_NAME="dev_sandbox"
RESET=false
for arg in "$@"; do
  if [[ "$arg" == "--reset" ]]; then
    RESET=true
  fi
done

if [[ "$RESET" == true ]]; then
  echo "🧹 Принудительная очистка тома $VOLUME_NAME (по флагу --reset)..."
  docker volume rm "$VOLUME_NAME" 2>/dev/null || true
else
  echo "ℹ️ Сохраняем существующие данные тома $VOLUME_NAME (без очистки)."
fi

# Копируем весь проект в песочницу (исключая .git, __pycache__, .pytest_cache, logs)
echo "📦 Копируем проект в песочницу (в том $VOLUME_NAME)..."
docker run --rm -v "$(pwd)":/src -v "$VOLUME_NAME":/workspace alpine sh -c "cd /src && tar cf - . --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='logs' | tar xf - -C /workspace"

echo "✅ Песочница готова! Теперь можно запускать сервисы внутри контейнера sandbox." 