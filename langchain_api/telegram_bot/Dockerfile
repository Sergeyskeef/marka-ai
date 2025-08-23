FROM python:3.10-slim
WORKDIR /app

# Копируем весь проект langchain_api
COPY . /app/langchain_api/

# Устанавливаем зависимости
WORKDIR /app/langchain_api
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir python-telegram-bot==21.0 aiohttp[speedups]

# Устанавливаем PYTHONPATH для корректных импортов
ENV PYTHONPATH=/app/langchain_api

# Запускаем бота как модуль Python
WORKDIR /app/langchain_api
CMD ["python", "-m", "telegram_bot.main"]
