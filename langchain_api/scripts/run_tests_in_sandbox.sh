#!/usr/bin/env bash
# Скрипт для автоматического запуска тестов внутри песочницы (sandbox)
# Запускать ТОЛЬКО ИЗ КОРНЯ ПРОЕКТА: bash langchain_api/scripts/run_tests_in_sandbox.sh

set -e

# Проверка директории запуска
if [[ ! -d "langchain_api" || ! -f "langchain_api/scripts/run_tests_in_sandbox.sh" ]]; then
  echo "❌ Скрипт нужно запускать из корня проекта (где лежит папка langchain_api)!"
  exit 1
fi

START_TIME=$(date +%s)

echo "🚪 Входим в контейнер sandbox и запускаем тесты..."
# Запускаем pytest и сохраняем вывод
PYTEST_OUTPUT=$(docker compose -f langchain_api/docker-compose.yml exec sandbox bash -c "cd /workspace/langchain_api && pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir pytest && pytest -v" 2>&1)
EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME-START_TIME))

# Парсим количество тестов и результат
TESTS_TOTAL=$(echo "$PYTEST_OUTPUT" | grep -Eo '[0-9]+ passed' | grep -Eo '^[0-9]+' | head -1)
TESTS_FAILED=$(echo "$PYTEST_OUTPUT" | grep -Eo '[0-9]+ failed' | grep -Eo '^[0-9]+' | head -1)

if [ $EXIT_CODE -eq 0 ]; then
  RESULT="SUCCESS"
  echo "✅ Все тесты в песочнице прошли успешно!"
else
  RESULT="FAIL"
  echo "❌ Тесты в песочнице завершились с ошибкой (код $EXIT_CODE)"
fi

# Логируем событие
python3 langchain_api/scripts/log_sandbox_event.py TEST_RUN "Pytest: $TESTS_TOTAL passed, $TESTS_FAILED failed, $DURATION sec" $RESULT

# Логируем событие в дневник пробуждения
python3 langchain_api/scripts/log_awakening_event.py TESTS "Pytest: $TESTS_TOTAL passed, $TESTS_FAILED failed, $DURATION sec" $RESULT

# Показываем вывод pytest
echo "$PYTEST_OUTPUT"

exit $EXIT_CODE 