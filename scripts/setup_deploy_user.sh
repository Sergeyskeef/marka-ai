#!/bin/bash

# Скрипт для настройки пользователя deploy

set -e  # Останавливаем выполнение при ошибке

# Проверка root прав
if [ "$EUID" -ne 0 ]; then 
    echo "Этот скрипт должен быть запущен с правами root"
    exit 1
fi

# Создание пользователя
echo "Создание пользователя deploy..."
useradd -m -s /bin/bash deploy

# Создание директорий
echo "Создание директорий..."
mkdir -p /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys

# Добавление в группу docker
echo "Добавление в группу docker..."
usermod -aG docker deploy

# Установка прав
echo "Установка прав..."
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

echo "Пользователь deploy успешно создан!"
echo "Теперь добавьте ваш публичный ключ в /home/deploy/.ssh/authorized_keys" 