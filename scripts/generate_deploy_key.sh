#!/bin/bash

# Скрипт для генерации SSH ключа для деплоя

set -e  # Останавливаем выполнение при ошибке

# Создаем директорию для ключей
mkdir -p deploy_keys

# Генерируем SSH ключ
ssh-keygen -t ed25519 -f deploy_keys/deploy_key -N "" -C "marka-deploy"

# Выводим публичный ключ
echo "Публичный ключ (добавьте его в /home/deploy/.ssh/authorized_keys на сервере):"
cat deploy_keys/deploy_key.pub

echo -e "\nПриватный ключ (добавьте его в GitHub Secrets как SERVER_SSH_KEY):"
cat deploy_keys/deploy_key

echo -e "\nСохраните эти ключи в безопасном месте!"
echo "Публичный ключ нужно добавить на сервер"
echo "Приватный ключ нужно добавить в GitHub Secrets" 