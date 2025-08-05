"""
GraphitiMemoryAdapter - HTTP-клиент для работы с Graphiti Memory API
"""

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _from_neo_value(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v

def parse_node(raw: dict) -> dict:
    props = {k: _from_neo_value(v) for k, v in raw.items()}
    return {"text": props.pop("msg"), "metadata": props}

class GraphitiMemoryAdapter:
    """Адаптер для работы с Graphiti Memory через HTTP API"""

    def __init__(self, base_url: str = "http://graphiti:7878"):
        self.base_url = base_url.rstrip('/')
        self.client = None
        logger.info(f"🧠 GraphitiMemoryAdapter инициализирован: {base_url}")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получает или создает HTTP клиент"""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                http2=True
            )
        return self.client

    async def health_check(self) -> dict[str, Any]:
        """Проверяет здоровье Graphiti"""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Graphiti health: {data.get('status')}")
                return data
            else:
                logger.error(f"❌ Graphiti health check failed: {response.status_code}")
                return {"status": "error", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"❌ Graphiti health check error: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def create_episode(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Создает новый эпизод в Graphiti"""
        try:
            # Создаем уникальный ID для узла
            import uuid
            node_id = str(uuid.uuid4())

            # Формируем payload согласно схеме Graphiti
            # Neo4j принимает только примитивные типы в properties
            properties = {
                "msg": text,
                "created_at": int(time.time()),  # Используем created_at вместо timestamp
                "test_run": False,
                "pytest_test": False
            }

            # Добавляем метаданные, сериализуя сложные типы
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str | int | float | bool):
                        properties[key] = value
                        logger.info(f"Добавляем метаданное {key}: {value}")
                    elif isinstance(value, list):
                        # Сериализуем списки в JSON строку
                        properties[key] = json.dumps(value)
                        logger.info(f"Сериализуем список {key}: {value}")
                    elif value is None:
                        # Пропускаем None значения
                        continue
                    else:
                        # Сериализуем сложные типы в JSON строку
                        properties[key] = json.dumps(value)
                        logger.info(f"Сериализуем метаданное {key}: {value}")

            payload = {
                "id": node_id,
                "type": "Episode",
                "properties": properties
            }

            logger.info(f"Отправляем payload: {json.dumps(payload, indent=2)}")

            # Отправляем запрос
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/nodes",
                json=payload
            )

            if response.status_code == 201:  # Graphiti возвращает 201 для создания
                response_data = response.json()
                logger.info(f"✅ Эпизод создан в Graphiti: {text[:50]}...")
                return {"success": True, "id": node_id, "data": response_data}
            else:
                error_text = response.text
                logger.error(f"❌ Ошибка создания эпизода: {response.status_code} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {error_text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка создания эпизода: {str(e)}")
            return {"success": False, "error": str(e)}

    async def search_episodes(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Ищет эпизоды в Graphiti с использованием полнотекстового поиска"""
        try:
            # Используем полнотекстовый поиск через Graphiti API
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/nodes",
                params={"search": query, "limit": limit}
            )
            
            if response.status_code == 200:
                data = response.json()
                episodes = []

                for node in data.get("nodes", []):
                    if node.get("type") == "Episode":
                        parsed = parse_node(node.get("properties", {}))
                        similarity = node.get("score", 1.0)
                        episodes.append({
                            "id": node.get("id"),
                            "text": parsed["text"],
                            "metadata": parsed["metadata"],
                            "similarity": similarity
                        })

                logger.info(f"🔍 Полнотекстовый поиск в Graphiti: '{query}' -> {len(episodes)} результатов")
                return {"items": episodes, "total": len(episodes)}
            else:
                error_text = response.text
                logger.error(f"❌ Ошибка поиска: {response.status_code} - {error_text}")
                return {"items": [], "total": 0, "error": f"HTTP {response.status_code}: {error_text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {str(e)}")
            return {"items": [], "total": 0, "error": str(e)}

    async def get_episode(self, episode_id: str) -> dict[str, Any]:
        """Получает эпизод по ID"""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/nodes/{episode_id}")
            
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                error_text = response.text
                logger.error(f"❌ Ошибка получения эпизода {episode_id}: {response.status_code} - {error_text}")
                return {"error": f"HTTP {response.status_code}: {error_text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка получения эпизода {episode_id}: {str(e)}")
            return {"error": str(e)}

    async def list_episodes(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Получает список эпизодов"""
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/nodes",
                params={"limit": limit, "offset": offset}
            )
            
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                error_text = response.text
                logger.error(f"❌ Ошибка получения списка эпизодов: {response.status_code} - {error_text}")
                return {"items": [], "total": 0, "error": f"HTTP {response.status_code}: {error_text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка эпизодов: {str(e)}")
            return {"items": [], "total": 0, "error": str(e)}

    async def close(self):
        """Закрывает HTTP сессию"""
        if self.client:
            await self.client.aclose()
            self.client = None
        logger.info("🔒 GraphitiMemoryAdapter закрыт")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Глобальный экземпляр адаптера
graphiti_adapter = GraphitiMemoryAdapter()
