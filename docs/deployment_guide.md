# Руководство по развертыванию - Марк

## Обзор

Это руководство поможет вам развернуть систему Марка в различных средах: от локальной разработки до продакшн-развертывания.

## Требования к системе

### Минимальные требования

- **CPU:** 2 ядра
- **RAM:** 4 GB
- **Диск:** 20 GB свободного места
- **ОС:** Linux (Ubuntu 20.04+), macOS, Windows с WSL2

### Рекомендуемые требования

- **CPU:** 4+ ядра
- **RAM:** 8+ GB
- **Диск:** 50+ GB SSD
- **Сеть:** Стабильное интернет-соединение

### Программные зависимости

- **Docker:** 20.10+
- **Docker Compose:** 2.0+
- **Python:** 3.9+ (для разработки)
- **Git:** 2.30+

## Быстрый старт (Docker)

### 1. Клонирование репозитория

```bash
git clone https://github.com/sergey/marka.git
cd marka
```

### 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл:

```env
# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Weaviate
WEAVIATE_URL=http://weaviate:8080

# Логирование
LOG_LEVEL=INFO

# Песочница
SANDBOX_TIMEOUT=15
SANDBOX_MEMORY_LIMIT=512m

# Мониторинг
ENABLE_METRICS=true
ENABLE_ALERTS=true
```

### 3. Запуск системы

```bash
# Переход в директорию с правильным docker-compose
cd langchain_api

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f app
```

### 4. Проверка работоспособности

```bash
# Проверка здоровья системы (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"

# Проверка доступности (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/ping').json())"

# Тест чата (из контейнера)
docker exec app python -c "import requests; print(requests.post('http://localhost:8000/chat/ask', json={'question': 'Привет! Как дела?'}).json())"
```

## Локальная разработка

### 1. Подготовка окружения

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка базы данных

```bash
# Переход в директорию с правильным docker-compose
cd langchain_api

# Запуск только Weaviate
docker-compose up -d weaviate

# Ожидание готовности Weaviate
sleep 10

# Проверка подключения (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://weaviate:8080/v1/.well-known/ready').json())"
```

### 3. Запуск приложения

```bash
# Запуск в режиме разработки
uvicorn langchain_api.main:app --reload --host 0.0.0.0 --port 8000

# Или через Python
python -m langchain_api.main
```

### 4. Настройка Telegram бота

1. Создайте бота через @BotFather в Telegram
2. Получите токен бота
3. Добавьте токен в `.env` файл
4. Запустите бота:

```bash
python -m langchain_api.telegram_bot.bot
```

## Продакшн развертывание

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER
```

### 2. Настройка безопасности

```bash
# Создание пользователя для приложения
sudo useradd -r -s /bin/false marka

# Создание директории для данных
sudo mkdir -p /opt/marka
sudo chown marka:marka /opt/marka

# Настройка firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3. Настройка Nginx (опционально)

```bash
# Установка Nginx
sudo apt install nginx -y

# Создание конфигурации
sudo nano /etc/nginx/sites-available/marka
```

Конфигурация Nginx:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /metrics/prometheus {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/marka /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 4. Настройка SSL (опционально)

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получение SSL сертификата
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление
sudo crontab -e
# Добавить строку:
# 0 12 * * * /usr/bin/certbot renew --quiet
```

### 5. Настройка мониторинга

```bash
# Создание конфигурации Prometheus
mkdir -p /opt/marka/monitoring
```

`/opt/marka/monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'marka'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics/prometheus'
    scrape_interval: 15s

  - job_name: 'node_exporter'
    static_configs:
      - targets: ['localhost:9100']
```

### 6. Настройка systemd

```bash
# Создание сервиса
sudo nano /etc/systemd/system/marka.service
```

Конфигурация сервиса:

```ini
[Unit]
Description=Mark - Осознанный цифровой компаньон
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/marka
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
User=marka
Group=marka

[Install]
WantedBy=multi-user.target
```

```bash
# Активация сервиса
sudo systemctl daemon-reload
sudo systemctl enable marka
sudo systemctl start marka
```

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию | Обязательная |
|------------|----------|--------------|--------------|
| `OPENAI_API_KEY` | Ключ API OpenAI | - | Да |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - | Нет |
| `WEAVIATE_URL` | URL Weaviate | http://weaviate:8080 | Нет |
| `LOG_LEVEL` | Уровень логирования | INFO | Нет |
| `SANDBOX_TIMEOUT` | Таймаут песочницы (сек) | 15 | Нет |
| `SANDBOX_MEMORY_LIMIT` | Лимит памяти песочницы | 512m | Нет |
| `ENABLE_METRICS` | Включение метрик | true | Нет |
| `ENABLE_ALERTS` | Включение алертов | true | Нет |

### Конфигурация Docker Compose

Основные сервисы в `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: ./langchain_api
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - WEAVIATE_URL=http://weaviate:8080
    depends_on:
      - weaviate
    volumes:
      - ./logs:/app/logs
      - ./sandbox:/sandbox
    restart: unless-stopped

  weaviate:
    image: semitechnologies/weaviate:1.22.4
    ports:
      - "8080:8080"
    environment:
      - QUERY_DEFAULTS_LIMIT=25
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
      - DEFAULT_VECTORIZER_MODULE=none
      - ENABLE_MODULES=text2vec-openai
      - CLUSTER_HOSTNAME=node1
    volumes:
      - weaviate_data:/var/lib/weaviate
    restart: unless-stopped

volumes:
  weaviate_data:
```

## Мониторинг и логирование

### Логирование

Логи сохраняются в директории `logs/`:

```bash
# Просмотр логов приложения
tail -f logs/app.log

# Просмотр логов через Docker
docker-compose logs -f app

# Просмотр логов песочницы
tail -f logs/sandbox_awakenings.log
```

### Метрики

Метрики доступны по адресу `/metrics/prometheus`:

```bash
# Получение метрик (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/metrics/prometheus').text[:500])"

# Сводка метрик (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/metrics/summary').json())"
```

### Алерты

Система алертов автоматически создает уведомления:

```bash
# Создание алерта (из контейнера)
docker exec app python -c "import requests; print(requests.post('http://localhost:8000/alerts/create', json={'severity': 'warning', 'message': 'Высокая нагрузка на систему', 'source': 'system_monitor'}).json())"

# Просмотр алертов (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/alerts/summary').json())"
```

## Резервное копирование

### Автоматическое резервное копирование

Создайте скрипт для резервного копирования:

```bash
#!/bin/bash
# /opt/marka/backup.sh

BACKUP_DIR="/opt/marka/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Создание резервной копии данных Weaviate
docker-compose exec weaviate tar czf /tmp/weaviate_backup_$DATE.tar.gz /var/lib/weaviate
docker cp marka_weaviate_1:/tmp/weaviate_backup_$DATE.tar.gz $BACKUP_DIR/

# Создание резервной копии логов
tar czf $BACKUP_DIR/logs_backup_$DATE.tar.gz logs/

# Создание резервной копии конфигурации
tar czf $BACKUP_DIR/config_backup_$DATE.tar.gz .env docker-compose.yml

# Удаление старых резервных копий (старше 30 дней)
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Резервное копирование завершено: $DATE"
```

```bash
# Добавление в cron
chmod +x /opt/marka/backup.sh
crontab -e
# Добавить строку для ежедневного резервного копирования в 2:00:
# 0 2 * * * /opt/marka/backup.sh
```

## Обновление системы

### Обновление через Git

```bash
# Остановка сервисов
docker-compose down

# Получение обновлений
git pull origin main

# Пересборка и запуск
docker-compose up -d --build

# Проверка работоспособности (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
```

### Обновление через Docker

```bash
# Обновление образов
docker-compose pull

# Перезапуск с новыми образами
docker-compose up -d

# Очистка старых образов
docker image prune -f
```

## Troubleshooting

### Проблема: Приложение не запускается

**Диагностика:**
```bash
# Проверка логов
docker-compose logs app

# Проверка переменных окружения
docker-compose config

# Проверка портов
netstat -tlnp | grep 8000
```

**Решение:**
1. Проверьте переменные окружения в `.env`
2. Убедитесь, что порт 8000 свободен
3. Проверьте права доступа к директориям

### Проблема: Weaviate не подключается

**Диагностика:**
```bash
# Проверка состояния Weaviate
docker-compose ps weaviate

# Проверка логов Weaviate
docker-compose logs weaviate

# Проверка доступности (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://weaviate:8080/v1/.well-known/ready').json())"
```

**Решение:**
1. Перезапустите Weaviate: `docker-compose restart weaviate`
2. Проверьте доступность порта 8080
3. Убедитесь, что у Weaviate есть права на запись в volume

### Проблема: Telegram бот не отвечает

**Диагностика:**
```bash
# Проверка токена бота
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe

# Проверка логов бота
docker-compose logs app | grep telegram
```

**Решение:**
1. Проверьте правильность токена бота
2. Убедитесь, что бот не заблокирован
3. Проверьте настройки webhook (если используется)

### Проблема: Высокое потребление ресурсов

**Диагностика:**
```bash
# Мониторинг ресурсов
docker stats

# Проверка метрик (из контейнера)
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/metrics/summary').json())"

# Анализ логов
tail -f logs/app.log | grep -i error
```

**Решение:**
1. Ограничьте ресурсы в `docker-compose.yml`
2. Настройте ротацию логов
3. Проверьте настройки кэширования

### Проблема: Ошибки в песочнице

**Диагностика:**
```bash
# Проверка состояния песочницы
docker-compose exec app ls -la /sandbox

# Проверка логов песочницы
tail -f logs/sandbox_awakenings.log

# Тест песочницы (из контейнера)
docker exec app python -c "import requests; print(requests.post('http://localhost:8000/sandbox/exec', json={'command': 'echo test'}).json())"
```

**Решение:**
1. Перезапустите контейнер приложения
2. Проверьте права доступа к `/sandbox`
3. Убедитесь, что Docker работает корректно

## Производительность

### Оптимизация

1. **Кэширование:**
   - Настройте Redis для кэширования
   - Используйте CDN для статических файлов

2. **База данных:**
   - Оптимизируйте запросы к Weaviate
   - Настройте индексы

3. **Мониторинг:**
   - Настройте алерты на высокую нагрузку
   - Мониторьте использование ресурсов

### Масштабирование

1. **Горизонтальное масштабирование:**
   - Используйте load balancer
   - Настройте несколько инстансов приложения

2. **Вертикальное масштабирование:**
   - Увеличьте ресурсы сервера
   - Оптимизируйте настройки Docker

## Безопасность

### Рекомендации

1. **Сетевая безопасность:**
   - Используйте HTTPS
   - Настройте firewall
   - Ограничьте доступ к API

2. **Аутентификация:**
   - Добавьте API ключи
   - Настройте OAuth2
   - Используйте JWT токены

3. **Мониторинг безопасности:**
   - Логируйте все запросы
   - Мониторьте подозрительную активность
   - Регулярно обновляйте зависимости

## Поддержка

### Полезные команды

```bash
# Полная диагностика системы
curl http://localhost:8000/health

# Проверка всех сервисов
docker-compose ps

# Просмотр всех логов
docker-compose logs

# Очистка системы
docker system prune -f

# Перезапуск всех сервисов
docker-compose restart
```

### Контакты

- **Документация:** [GitHub Wiki](https://github.com/sergey/marka/wiki)
- **Issues:** [GitHub Issues](https://github.com/sergey/marka/issues)
- **Discussions:** [GitHub Discussions](https://github.com/sergey/marka/discussions) 