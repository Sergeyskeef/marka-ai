#!/bin/bash

echo "🔧 Исправление .env файла"
echo "========================"
echo ""

# Создаем резервную копию
cp .env .env.backup
echo "✅ Создана резервная копия .env.backup"

# Собираем ключ в одну строку
FULL_KEY="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"

# Создаем временный файл с исправленным ключом
echo "📝 Исправляю формат ключа..."

# Читаем .env построчно и исправляем
while IFS= read -r line; do
    if [[ $line == OPENAI_API_KEY=* ]]; then
        echo "OPENAI_API_KEY=$FULL_KEY" >> .env.fixed
        # Пропускаем следующие 2 строки (продолжение ключа)
        read -r
        read -r
    else
        echo "$line" >> .env.fixed
    fi
done < .env

# Заменяем старый файл
mv .env.fixed .env

echo "✅ Ключ исправлен!"
echo ""
echo "🔍 Проверка:"
grep "OPENAI_API_KEY" .env | cut -c1-50
echo ""
echo "📋 Теперь нужно перезапустить приложение:"
echo "   docker restart app"