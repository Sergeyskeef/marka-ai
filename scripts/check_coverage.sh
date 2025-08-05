#!/bin/bash

# Скрипт для проверки покрытия кода тестами

echo "🧪 Запуск тестов с измерением покрытия..."

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверяем наличие pytest и coverage
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ pytest не установлен. Установите: pip install pytest pytest-cov${NC}"
    exit 1
fi

# Запускаем тесты с покрытием
echo "Запуск pytest..."
pytest --cov=. --cov-report=term-missing --cov-report=html --cov-report=xml -v

# Получаем процент покрытия
COVERAGE=$(coverage report | grep TOTAL | awk '{print $4}' | sed 's/%//')

if [ -z "$COVERAGE" ]; then
    echo -e "${RED}❌ Не удалось вычислить покрытие${NC}"
    exit 1
fi

# Выводим результат
echo ""
echo "📊 Результаты покрытия:"
echo "========================"

# Определяем цвет в зависимости от покрытия
if (( $(echo "$COVERAGE >= 80" | bc -l) )); then
    COLOR=$GREEN
    STATUS="Отлично!"
elif (( $(echo "$COVERAGE >= 60" | bc -l) )); then
    COLOR=$GREEN
    STATUS="Хорошо"
elif (( $(echo "$COVERAGE >= 50" | bc -l) )); then
    COLOR=$YELLOW
    STATUS="Удовлетворительно"
else
    COLOR=$RED
    STATUS="Недостаточно"
fi

echo -e "Общее покрытие: ${COLOR}${COVERAGE}%${NC} - ${STATUS}"

# Проверяем минимальное требование (50%)
if (( $(echo "$COVERAGE < 50" | bc -l) )); then
    echo -e "${RED}❌ Покрытие ниже минимального требования (50%)${NC}"
    echo "📈 Необходимо добавить больше тестов!"
    exit 1
else
    echo -e "${GREEN}✅ Покрытие соответствует минимальным требованиям${NC}"
fi

echo ""
echo "📁 HTML отчет сохранен в: htmlcov/index.html"
echo "📄 XML отчет сохранен в: coverage.xml"

# Опционально открываем HTML отчет
if command -v xdg-open &> /dev/null; then
    read -p "Открыть HTML отчет в браузере? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        xdg-open htmlcov/index.html
    fi
elif command -v open &> /dev/null; then
    read -p "Открыть HTML отчет в браузере? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        open htmlcov/index.html
    fi
fi