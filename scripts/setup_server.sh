#!/bin/bash

# Скрипт для настройки сервера для CI/CD

set -e  # Останавливаем выполнение при ошибке

# Проверка root прав
if [ "$EUID" -ne 0 ]; then 
    echo "Этот скрипт должен быть запущен с правами root"
    exit 1
fi

# Установка Docker
echo "Установка Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Установка Docker Compose
echo "Установка Docker Compose..."
apt-get update
apt-get install -y docker-compose-plugin

# Создание пользователя deploy
echo "Создание пользователя deploy..."
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash deploy
    usermod -aG docker deploy
fi

# Настройка SSH
echo "Настройка SSH..."
mkdir -p /home/deploy/.ssh
touch /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Создание директорий для приложения
echo "Создание директорий для приложения..."
mkdir -p /home/sergey/marka/{logs,backups}
chown -R sergey:sergey /home/sergey/marka

# Настройка прав для Docker
echo "Настройка прав для Docker..."
usermod -aG docker sergey

# Создание systemd сервиса для автоматического перезапуска
echo "Создание systemd сервиса..."
cat > /etc/systemd/system/marka.service << EOL
[Unit]
Description=Marka Application
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/sergey/marka
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=sergey
Group=sergey

[Install]
WantedBy=multi-user.target
EOL

# Перезагрузка systemd
systemctl daemon-reload
systemctl enable marka.service

echo "Настройка сервера завершена!"
echo "Теперь добавьте ваш публичный SSH ключ в /home/deploy/.ssh/authorized_keys" 