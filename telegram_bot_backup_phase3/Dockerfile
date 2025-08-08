FROM python:3.10-slim
WORKDIR /bot

# Копируем весь проект
COPY . /bot/langchain_api/

# Устанавливаем зависимости
WORKDIR /bot/langchain_api
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir python-telegram-bot==21.0 aiohttp[speedups]

# Устанавливаем PYTHONPATH
ENV PYTHONPATH=/bot

# Запускаем бота
CMD ["python", "-c", "import asyncio; from langchain_api.telegram_bot.bot import main; asyncio.run(main())"]
