#!/bin/bash

# Скрипт для первого деплоя

set -e  # Останавливаем выполнение при ошибке

# Проверяем наличие необходимых переменных
if [ -z "$DOCKERHUB_USERNAME" ]; then
    echo "Ошибка: DOCKERHUB_USERNAME не установлен"
    exit 1
fi

# Создаем .env файл
echo "Создание .env файла..."
cat > .env << EOL
OPENAI_API_KEY=${OPENAI_API_KEY}
ENVIRONMENT=production
WEAVIATE_HTTP_HOST=weaviate
WEAVIATE_HTTP_PORT=8080
WEAVIATE_GRPC_HOST=weaviate
WEAVIATE_GRPC_PORT=50051
EOL

# Создаем docker-compose.yml
echo "Создание docker-compose.yml..."
cat > docker-compose.yml << EOL
version: '3.8'

services:
  app:
    image: ${DOCKERHUB_USERNAME}/marka:latest
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ENVIRONMENT=production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    depends_on:
      - weaviate

  weaviate:
    image: semitechnologies/weaviate:1.24.1
    ports:
      - "8080:8080"
    environment:
      - QUERY_DEFAULTS_LIMIT=25
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
      - DEFAULT_VECTORIZER_MODULE=text2vec-openai
      - ENABLE_MODULES=text2vec-openai
      - OPENAI_APIKEY=${OPENAI_API_KEY}
      - CLUSTER_HOSTNAME=node1
    volumes:
      - weaviate_data:/var/lib/weaviate
    restart: unless-stopped

volumes:
  weaviate_data:
EOL

# Запускаем контейнеры
echo "Запуск контейнеров..."
docker compose up -d

# Ждем готовности приложения
echo "Ожидание готовности приложения..."
for i in {1..30}; do
    if curl -s -f http://localhost:8000/health > /dev/null; then
        echo "Приложение успешно запущено!"
        exit 0
    fi
    echo "Попытка $i/30..."
    sleep 10
done

echo "Ошибка: приложение не запустилось за отведенное время"
exit 1 