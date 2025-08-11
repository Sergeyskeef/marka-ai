FROM python:3.10-slim as builder

WORKDIR /app

# Устанавливаем зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем только requirements.txt сначала для кэширования слоя с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pytest pytest-cov ruff

# Финальный образ
FROM python:3.10-slim

WORKDIR /app

# Копируем установленные пакеты из builder
COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Копируем код приложения
COPY . .

# Создаем необходимые директории
RUN mkdir -p /app/logs

# Устанавливаем права
RUN chmod -R 755 /app

# Добавляем путь к модулям в PYTHONPATH
ENV PYTHONPATH=/app

# Проверяем здоровье приложения
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
