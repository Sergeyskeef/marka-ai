#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тест для проверки работы LLM."""

import os
import sys
import httpx
import logging
from openai import OpenAI
from langchain.schema import SystemMessage, HumanMessage

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_proxy_config():
    """Получает настройки прокси из переменных окружения."""
    http_proxy = os.getenv("HTTP_PROXY", "")
    https_proxy = os.getenv("HTTPS_PROXY", "")
    
    if not (http_proxy or https_proxy):
        print("ВНИМАНИЕ: Переменные HTTP_PROXY и HTTPS_PROXY не найдены!")
        return {}
    
    proxies = {}
    if http_proxy:
        proxies["http://"] = http_proxy
    if https_proxy:
        proxies["https://"] = https_proxy
    
    return proxies

def get_httpx_client():
    """Создает httpx клиент с настроенным прокси."""
    proxies = get_proxy_config()
    if not proxies:
        return None
    # Берем первую строку из словаря (http или https)
    proxy_url = next(iter(proxies.values()))
    return httpx.Client(proxy=proxy_url)

def create_openai_client():
    """Создает клиент OpenAI с настроенным прокси."""
    http_client = get_httpx_client()
    
    # Если прокси не настроен, вернем клиент по умолчанию
    if http_client is None:
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        http_client=http_client
    )

def chat_with_gpt(prompt, model="gpt-4.1-mini"):
    """Простая функция для общения с GPT."""
    http_client = None
    try:
        http_client = get_httpx_client()
        if http_client is None:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        else:
            client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                http_client=http_client
            )
        response = client.chat.completions.create(
            model=model,
            messages=[
                SystemMessage(content="Ты — Марк, осознанный ИИ-компаньон.").dict(),
                HumanMessage(content=prompt).dict()
            ],
            temperature=0.3,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка: {e}"
    finally:
        if http_client:
            http_client.close()

if __name__ == "__main__":
    # Загружаем переменные окружения из .env файла
    # Считываем API_KEY из .env файла
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = value.strip('"\'')
    
    # Получаем запрос
    query = sys.argv[1] if len(sys.argv) > 1 else "Кто такой Марк?"
    
    print(f"Запрос: {query}")
    print("-" * 80)
    
    # Отправляем запрос
    answer = chat_with_gpt(query)
    
    print(f"Ответ: {answer}")
    print("-" * 80) 