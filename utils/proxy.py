from .openai_proxy_client import get_proxy_config, get_httpx_client

def setup_proxy(timeout: float = 60.0):
    """Настраивает прокси для HTTP клиента.
    
    Args:
        timeout: Таймаут для HTTP запросов в секундах
        
    Returns:
        httpx.Client или None если прокси не настроен
    """
    return get_httpx_client(timeout=timeout) 