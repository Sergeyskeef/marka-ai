FROM python:3.10-slim
WORKDIR /bot
COPY telegram_bot/requirements-bot.txt .
RUN pip install --no-cache-dir -r requirements-bot.txt
COPY telegram_bot/ .
CMD ["python", "bot.py"]
