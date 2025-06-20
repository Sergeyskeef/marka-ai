import os
import httpx
import logging
from typing import Optional, Dict, Any, Union
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from openai import OpenAI

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_proxy_config() -> Dict[str, str]:
    """Получает настройки прокси из переменных окружения."""
    http_proxy = os.getenv("HTTP_PROXY", "")
    https_proxy = os.getenv("HTTPS_PROXY", "")
    
    if not (http_proxy or https_proxy):
        logging.warning("ВНИМАНИЕ: Переменные HTTP_PROXY и HTTPS_PROXY не найдены!")
        return {}
    
    proxies = {}
    if http_proxy:
        proxies["http://"] = http_proxy
        logging.info(f"Настроен HTTP прокси: {http_proxy.split('@')[1] if '@' in http_proxy else http_proxy}")
    if https_proxy:
        proxies["https://"] = https_proxy
        logging.info(f"Настроен HTTPS прокси: {https_proxy.split('@')[1] if '@' in https_proxy else https_proxy}")
    
    return proxies

def get_httpx_client(timeout: float = 60.0) -> Optional[httpx.Client]:
    """Создает httpx клиент с настроенным прокси и таймаутом.
    
    Args:
        timeout: Таймаут для HTTP запросов в секундах
        
    Returns:
        httpx.Client или None если прокси не настроен
    """
    proxies = get_proxy_config()
    proxy_url = None
    if proxies.get("https://"):
        proxy_url = proxies["https://"]
    elif proxies.get("http://"):
        proxy_url = proxies["http://"]
    if not proxy_url:
        logging.warning("Прокси не настроен, возвращаем None")
        return None
    # Создаем клиент с proxy и таймаутом
    try:
        client = httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            follow_redirects=True
        )
        logging.info(f"✅ HTTP клиент с proxy создан успешно (таймаут: {timeout}с)")
        return client
    except Exception as e:
        logging.error(f"❌ Ошибка при создании HTTP клиента: {e}")
        return None

def create_openai_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    org_id: Optional[str] = None,
    timeout: float = 60.0
) -> OpenAI:
    """Создает клиент OpenAI с настроенным прокси.
    
    Args:
        base_url: Базовый URL для API OpenAI (опционально)
        api_key: API ключ OpenAI (по умолчанию берется из переменных окружения)
        org_id: ID организации в OpenAI (опционально)
        timeout: Таймаут для HTTP запросов в секундах
        
    Returns:
        OpenAI: Клиент OpenAI с настроенным прокси
    """
    http_client = get_httpx_client(timeout=timeout)
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    org_id = org_id or os.getenv("OPENAI_ORG_ID")
    
    if not api_key:
        logging.error("❌ OPENAI_API_KEY не найден в переменных окружения!")
    
    # Базовые параметры
    params = {
        "api_key": api_key
    }
    
    # Добавляем опциональные параметры если они указаны
    if base_url:
        params["base_url"] = base_url
    if org_id:
        params["organization"] = org_id
    
    # Если прокси не настроен, вернем клиент по умолчанию
    if http_client is None:
        logging.warning("Создаем клиент OpenAI без прокси")
        return OpenAI(**params)
    
    # Добавляем http_client если он создан
    params["http_client"] = http_client
    logging.info(f"✅ Создаем клиент OpenAI с настроенным прокси (таймаут: {timeout}с)")
    
    return OpenAI(**params)

def embeddings(
    model: str = "text-embedding-3-small",
    dimensions: Optional[int] = None,
    timeout: float = 60.0
) -> OpenAIEmbeddings:
    """Создает объект эмбеддингов с настроенным прокси.
    
    Args:
        model: Модель для эмбеддингов
        dimensions: Размерность векторов (опционально)
        timeout: Таймаут для HTTP запросов в секундах
        
    Returns:
        OpenAIEmbeddings: Объект эмбеддингов с настроенным прокси
    """
    http_client = get_httpx_client(timeout=timeout)
    api_key = os.getenv("OPENAI_API_KEY")
    
    # Базовые параметры
    params = {
        "model": model,
        "openai_api_key": api_key
    }
    
    # Добавляем размерность, если она указана
    if dimensions:
        params["dimensions"] = dimensions
    
    # Добавляем httpx клиент, если он создан
    if http_client is not None:
        params["client"] = http_client
        logging.info(f"✅ Создан объект эмбеддингов с прокси для модели {model} (таймаут: {timeout}с)")
    else:
        logging.warning(f"Создан объект эмбеддингов без прокси для модели {model}")
    
    return OpenAIEmbeddings(**params)

# 👉 теперь возвращаем ChatOpenAI с proxy_client внутри

# ---------------------------------------------------------
# Публичный клиент через прокси (не затираем модуль openai)
# ---------------------------------------------------------
proxy_client = OpenAI(
    api_key     = os.getenv("OPENAI_API_KEY"),
    base_url    = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    http_client = httpx.Client(proxy=os.getenv("HTTP_PROXY"), timeout=30),
)

# ---------------------------------------------------------
# Chat‑модель для всех цепочек проекта
# ---------------------------------------------------------
def chat_model(
    model: str = "gpt-4.1-mini",
    temperature: float = 0.3,
    max_tokens: int = 2000,
    timeout: float = 60.0,
):
    return ChatOpenAI(
        model_name=model,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=timeout,
    )

# Создаем глобальный клиент OpenAI для использования в проекте
openai_client = create_openai_client()

# Глобальный объект эмбеддингов для всего проекта
embeddings = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))

# Экспортируем chat_model, openai_client, embeddings для использования в других модулях
__all__ = ["chat_model", "openai_client", "embeddings"]
