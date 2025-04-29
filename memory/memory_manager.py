import os
import requests

class MemoryManager:
    """
    HTTP-реализация менеджера диалоговой памяти для Weaviate.
    Не требует ключей, использует анонимный доступ.
    """

    def __init__(self):
        # Базовый URL Weaviate (без завершающего "/")
        weaviate_url = os.getenv("WEAVIATE_HTTP_URL", "http://weaviate:8080").rstrip('/')
        if not weaviate_url:
            raise ValueError("Не задана переменная окружения WEAVIATE_HTTP_URL")
        self.url = weaviate_url

        # Проверяем готовность сервера
        try:
            # Попробуем стандартный endpoint
            r = requests.get(f"{self.url}/.well-known/ready", timeout=5)
            if r.status_code != 200:
                # Альтернативный путь в новых версиях
                r = requests.get(f"{self.url}/v1/.well-known/ready", timeout=5)
            if r.status_code not in (200, 204):
                raise ConnectionError(f"Weaviate недоступен (статус {r.status_code})")
        except requests.RequestException as e:
            raise ConnectionError(f"Weaviate не доступен по {self.url}: {e}")

        # Убедимся, что класс Memory существует
        self._ensure_memory_class()

    def _ensure_memory_class(self):
        """Создаёт в схеме класс Memory, если он ещё не добавлен."""
        r = requests.get(f"{self.url}/v1/schema", timeout=5)
        r.raise_for_status()
        schema = r.json()
        existing = [c["class"] for c in schema.get("classes", [])]
        if "Memory" not in existing:
            payload = {
                "class": "Memory",
                "description": "Диалоговая память: Q/A из чата и Telegram",
                "vectorizer": "text2vec-openai",
                "properties": [
                    {"name": "sender",    "dataType": ["string"], "description": "user или assistant"},
                    {"name": "message",   "dataType": ["text"],   "description": "Текст сообщения"},
                    {"name": "timestamp", "dataType": ["date"],   "description": "Временная метка"}
                ]
            }
            r2 = requests.post(f"{self.url}/v1/schema", json=payload)
            r2.raise_for_status()

    def add_message(self, sender: str, message: str, timestamp: str):
        """
        Сохраняет одно сообщение в класс Memory.
        :param sender: 'user' или 'assistant'
        :param message: текст сообщения
        :param timestamp: ISO-строка, например '2025-04-26T10:15:00Z'
        """
        obj = {
            "class": "Memory",
            "properties": {
                "sender":    sender,
                "message":   message,
                "timestamp": timestamp
            }
        }
        r = requests.post(f"{self.url}/v1/objects", json=obj)
        r.raise_for_status()

    def query_relevant(self, query: str, top_k: int = 5):
        """
        Семантический поиск по Memory через GraphQL.
        :param query: текст запроса
        :param top_k: количество возвращаемых записей
        :return: список словарей с полями sender, message, timestamp
        """
        gql = {
            "query": (
                '{ Get { Memory('
                f'nearText: {{concepts: ["{query}"]}}, '
                f'limit: {top_k}'
                ') { sender message timestamp } } }'
            )
        }
        r = requests.post(f"{self.url}/v1/graphql", json=gql)
        r.raise_for_status()
        data = r.json().get("data", {}).get("Get", {}).get("Memory", [])
        return data
