"""
GraphitiMemoryAdapter - HTTP-клиент для работы с Graphiti Memory API
"""

import json
import logging
import time
from typing import Any, Optional

import httpx
from core.error_middleware import RetryableHTTPClient
from core.memory.graphiti_cache import get_cache
import asyncio
import os

# Импортируем Event Bus
try:
    from core.event_bus import event_bus, EventTypes
    EVENT_BUS_AVAILABLE = True
except ImportError:
    EVENT_BUS_AVAILABLE = False

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

    def __init__(self, base_url: str = "http://graphiti:7878", use_cache: bool = True):
        self.base_url = base_url.rstrip('/')
        self.client = None
        self._retry_client = None
        self.use_cache = use_cache
        self._cache = None
        # Семафор для контроля параллелизма (чтобы не получать 429 от LLM провайдера)
        self.semaphore_limit = int(os.getenv('GRAPHITI_SEMAPHORE_LIMIT', '20'))
        self._semaphore = asyncio.Semaphore(self.semaphore_limit)
        logger.info(f"🧠 GraphitiMemoryAdapter инициализирован: {base_url} (cache: {use_cache}, semaphore: {self.semaphore_limit})")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получает или создает оптимизированный HTTP клиент"""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    total=30.0,
                    connect=5.0,
                    pool=30.0,
                    read=10.0,
                    write=10.0
                ),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0
                ),
                http2=True,  # HTTP/2 для мультиплексирования
                follow_redirects=True
            )
        return self.client
    
    async def _get_retry_client(self) -> RetryableHTTPClient:
        """Получает клиент с retry логикой"""
        if self._retry_client is None:
            # Важно передавать base_url, а RetryableHTTPClient теперь лениво инициализирует httpx клиент
            self._retry_client = RetryableHTTPClient(
                base_url=self.base_url,
                timeout=30.0,
                max_retries=3
            )
        return self._retry_client

    async def health_check(self) -> dict[str, Any]:
        """Проверяет здоровье Graphiti"""
        try:
            client = await self._get_retry_client()
            response = await client.get("/health")
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
            client = await self._get_retry_client()
            response = await client.post(
                "/nodes",
                json=payload
            )

            if response.status_code == 201:  # Graphiti возвращает 201 для создания
                response_data = response.json()
                logger.info(f"✅ Эпизод создан в Graphiti: {text[:50]}...")
                
                # Публикуем событие о сохранении в память
                if EVENT_BUS_AVAILABLE:
                    asyncio.create_task(event_bus.publish(
                        EventTypes.MEMORY_STORED,
                        {
                            "episode_id": node_id,
                            "text_preview": text[:100],
                            "metadata": metadata,
                            "size": len(text)
                        },
                        source="GraphitiAdapter"
                    ))
                
                # Инвалидация кеша поиска (новые данные)
                try:
                    if self.use_cache and self._cache is None:
                        self._cache = await get_cache()
                    if self.use_cache and self._cache:
                        await self._cache.invalidate_query_type("search_episodes")
                        # Если есть user_id в метаданных — чистим персональный кеш
                        user_id = None
                        try:
                            user_id = (metadata or {}).get("user_id")
                        except Exception:
                            user_id = None
                        if user_id:
                            await self._cache.invalidate_user_cache(str(user_id))
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось инвалидировать кеш после записи: {e}")

                return {"success": True, "id": node_id, "data": response_data}
            else:
                error_text = response.text
                logger.error(f"❌ Ошибка создания эпизода: {response.status_code} - {error_text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {error_text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка создания эпизода: {str(e)}")
            return {"success": False, "error": str(e)}

    async def create_message(
        self,
        session_id: str,
        role: str,
        text: str,
        metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Создает сообщение чата (узел типа Message) в Graphiti"""
        try:
            import uuid
            import time
            node_id = str(uuid.uuid4())

            properties: dict[str, Any] = {
                "msg": text,
                "session_id": session_id,
                "role": role,
                "created_at": int(time.time()),
            }

            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str | int | float | bool):
                        properties[key] = value
                    elif isinstance(value, list):
                        properties[key] = json.dumps(value)
                    elif value is None:
                        continue
                    else:
                        properties[key] = json.dumps(value)

            payload = {
                "id": node_id,
                "type": "Message",
                "properties": properties
            }

            client = await self._get_retry_client()
            response = await client.post("/nodes", json=payload)
            if response.status_code == 201:
                # Инвалидация кеша поиска
                try:
                    if self.use_cache and self._cache is None:
                        self._cache = await get_cache()
                    if self.use_cache and self._cache:
                        await self._cache.invalidate_query_type("search_episodes")
                        if metadata and metadata.get("user_id"):
                            await self._cache.invalidate_user_cache(str(metadata.get("user_id")))
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось инвалидировать кеш после записи Message: {e}")

                return {"success": True, "id": node_id}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка создания Message: {e}")
            return {"success": False, "error": str(e)}

    async def create_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Создает узел Session в Graphiti (идемпотентно по id)."""
        try:
            properties: dict[str, Any] = {
                "id": session_id,
                "ts_start": int(time.time()),
            }
            if user_id:
                properties["user_id"] = user_id
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str | int | float | bool):
                        properties[key] = value
                    elif isinstance(value, list):
                        properties[key] = json.dumps(value)
                    elif value is None:
                        continue
                    else:
                        properties[key] = json.dumps(value)

            payload = {
                "id": session_id,
                "type": "Session",
                "properties": properties,
            }

            client = await self._get_retry_client()
            response = await client.post("/nodes", json=payload)
            if response.status_code in (201, 409):
                # 201 Created или 409 Conflict (уже существует) считаем успешным идемпотентным созданием
                return {"success": True, "id": session_id}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"❌ Ошибка создания Session: {e}")
            return {"success": False, "error": str(e)}

    async def search_episodes(self, query: str, limit: int = 10, user_id: Optional[str] = None) -> dict[str, Any]:
        """Ищет эпизоды в Graphiti с использованием полнотекстового поиска"""
        try:
            # Проверяем кеш
            if self.use_cache and self._cache is None:
                self._cache = await get_cache()
                
            cache_params = {"query": query, "limit": limit}
            
            if self.use_cache and self._cache:
                cached = await self._cache.get("search_episodes", cache_params, user_id)
                if cached:
                    return cached["result"]
            
            # Используем полнотекстовый поиск через Graphiti API
            client = await self._get_retry_client()
            response = await client.get(
                "/nodes",
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
                result = {"items": episodes, "total": len(episodes)}
                
                # Сохраняем в кеш
                if self.use_cache and self._cache:
                    await self._cache.set("search_episodes", cache_params, result, user_id=user_id)
                    
                return result
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
            client = await self._get_retry_client()
            response = await client.get(f"/nodes/{episode_id}")
            
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
            client = await self._get_retry_client()
            response = await client.get(
                "/nodes",
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
        if self._retry_client:
            await self._retry_client.close()
            self._retry_client = None
        logger.info("🔒 GraphitiMemoryAdapter закрыт")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Глобальный экземпляр адаптера
graphiti_adapter = GraphitiMemoryAdapter()
