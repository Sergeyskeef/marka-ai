#!/bin/bash

# Скрипт для автоматического деплоя приложения

set -e  # Останавливаем выполнение при ошибке

# Конфигурация
DOCKER_IMAGE="${DOCKERHUB_USERNAME}/marka"
DEPLOY_DIR="/home/sergey/marka"
BACKUP_DIR="${DEPLOY_DIR}/backups"
LOG_FILE="${DEPLOY_DIR}/logs/deploy.log"

# Создаем необходимые директории
mkdir -p "${BACKUP_DIR}"
mkdir -p "${DEPLOY_DIR}/logs"

# Функция для логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Функция для создания бэкапа
create_backup() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="${BACKUP_DIR}/backup_${timestamp}.tar.gz"
    
    log "Создание бэкапа в ${backup_file}"
    tar -czf "${backup_file}" -C "${DEPLOY_DIR}" .
    log "Бэкап создан успешно"
}

# Функция для проверки здоровья приложения
check_health() {
    local max_retries=5
    local retry_count=0
    local health_status=0
    
    log "Проверка здоровья приложения..."
    
    while [ ${retry_count} -lt ${max_retries} ]; do
        if curl -s -f "http://localhost:8000/health" > /dev/null; then
            health_status=1
            break
        fi
        
        retry_count=$((retry_count + 1))
        log "Попытка ${retry_count}/${max_retries} не удалась, ожидание..."
        sleep 10
    done
    
    if [ ${health_status} -eq 0 ]; then
        log "ОШИБКА: Приложение не прошло проверку здоровья"
        return 1
    fi
    
    log "Приложение успешно прошло проверку здоровья"
    return 0
}

# Основной процесс деплоя
main() {
    log "Начало процесса деплоя"
    
    # Создаем бэкап
    create_backup
    
    # Останавливаем текущие контейнеры
    log "Остановка текущих контейнеров"
    cd "${DEPLOY_DIR}"
    docker compose down || true
    
    # Получаем последний образ
    log "Получение последнего образа ${DOCKER_IMAGE}"
    docker pull "${DOCKER_IMAGE}:latest"
    
    # Запускаем новые контейнеры
    log "Запуск новых контейнеров"
    docker compose up -d
    
    # Проверяем здоровье
    if ! check_health; then
        log "ОШИБКА: Деплой не удался, откат к предыдущей версии"
        docker compose down
        docker compose up -d
        exit 1
    fi
    
    log "Деплой успешно завершен"
}

# Запускаем основной процесс
main 