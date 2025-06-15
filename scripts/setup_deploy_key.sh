#!/bin/bash

# Скрипт для настройки ключа деплоя

set -e  # Останавливаем выполнение при ошибке

# Создаем директорию для ключей
mkdir -p deploy_keys

# Генерируем новый ключ
echo "Генерация нового SSH ключа для деплоя..."
ssh-keygen -t ed25519 -f deploy_keys/deploy_key -N "" -C "marka-deploy"

# Выводим инструкции
echo -e "\n=== ИНСТРУКЦИИ ==="
echo -e "\n1. Добавьте публичный ключ на сервер:"
echo "   Выполните на сервере:"
echo "   echo '$(cat deploy_keys/deploy_key.pub)' >> /home/deploy/.ssh/authorized_keys"
echo
echo "2. Добавьте приватный ключ в GitHub Secrets:"
echo "   - Откройте репозиторий на GitHub"
echo "   - Перейдите в Settings -> Secrets and variables -> Actions"
echo "   - Нажмите 'New repository secret'"
echo "   - Name: SERVER_SSH_KEY"
echo "   - Value: (вставьте содержимое файла deploy_keys/deploy_key)"
echo
echo "3. Проверьте права на сервере:"
echo "   sudo chown -R deploy:deploy /home/deploy/.ssh"
echo "   sudo chmod 700 /home/deploy/.ssh"
echo "   sudo chmod 600 /home/deploy/.ssh/authorized_keys"
echo
echo "4. Проверьте подключение:"
echo "   ssh -i deploy_keys/deploy_key deploy@ваш_сервер"
echo
echo "=== СОДЕРЖИМОЕ КЛЮЧЕЙ ==="
echo -e "\nПубличный ключ (добавить на сервер):"
cat deploy_keys/deploy_key.pub
echo -e "\nПриватный ключ (добавить в GitHub Secrets):"
cat deploy_keys/deploy_key 