FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for better caching
COPY requirements.txt telegram_bot/requirements.txt* ./
COPY telegram_bot/requirements.txt* ./telegram_bot/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir python-telegram-bot==21.0 aiohttp[speedups]

# Copy the rest of the application
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Set working directory to telegram_bot
WORKDIR /app/telegram_bot

# Run the bot
CMD ["python", "main.py"]
