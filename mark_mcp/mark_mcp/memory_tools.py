"""High level helpers for the Graphiti memory API."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from .config import settings
from .models_memory import MemoryMetadata

logger = logging.getLogger("mark-mcp.memory")

try:  # pragma: no cover - redis is optional at runtime
    import redis.asyncio as redis
except Exception:  # pragma: no cover - missing dependency during tests
    redis = None  # type: ignore


_redis_client: Optional["redis.Redis"] = None
_http_client: Optional[httpx.AsyncClient] = None


def _get_redis() -> Optional["redis.Redis"]:
    """Return a cached Redis client if REDIS_URL is configured."""

    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL")
    if not url or redis is None:
        return None
    _redis_client = redis.from_url(url, encoding="utf-8", decode_responses=True)
    return _redis_client


def _get_http_client() -> httpx.AsyncClient:
    """Singleton AsyncClient with connection pooling and retries."""

    global _http_client
    if _http_client is None:
        transport = httpx.AsyncHTTPTransport(retries=3)
        _http_client = httpx.AsyncClient(
            base_url=settings.graphiti_url,
            timeout=settings.request_timeout_s,
            transport=transport,
            headers={"Accept": "application/json"},
        )
    return _http_client


async def memory_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """Search the episodic memory service and normalise the response."""

    start = time.perf_counter()
    cache = _get_redis()
    cache_key = f"mem:search:{query}:{limit}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                "memory_search cache_hit query=%r limit=%d ms=%.1f", query, limit, elapsed
            )
            return json.loads(cached)

    client = _get_http_client()
    response = await client.get("/nodes", params={"search": query, "limit": limit})
    elapsed = (time.perf_counter() - start) * 1000

    if response.status_code != 200:
        logger.error(
            "memory_search error query=%r limit=%d status=%d ms=%.1f",
            query,
            limit,
            response.status_code,
            elapsed,
        )
        return {
            "items": [],
            "total": 0,
            "error": f"HTTP {response.status_code}: {response.text[:200]}",
        }

    data = response.json()
    items = []
    for node in data.get("nodes", []):
        if node.get("type") != "Episode":
            continue
        props = node.get("properties", {})
        items.append(
            {
                "id": node.get("id"),
                "text": props.get("msg", ""),
                "metadata": {k: v for k, v in props.items() if k != "msg"},
            }
        )

    result = {"items": items, "total": len(items)}
    if cache:
        await cache.setex(cache_key, 60, json.dumps(result, ensure_ascii=False))

    logger.info("memory_search ok query=%r limit=%d ms=%.1f", query, limit, elapsed)
    return result


async def memory_upsert(text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist a new memory Episode in Graphiti."""

    start = time.perf_counter()
    validated_metadata = {}
    if metadata:
        validated_metadata.update(
            MemoryMetadata(**metadata).model_dump(exclude_none=True)
        )

    payload: Dict[str, Any] = {
        "id": None,
        "type": "Episode",
        "properties": {"msg": text, **validated_metadata},
    }

    client = _get_http_client()
    response = await client.post("/nodes", json=payload)
    elapsed = (time.perf_counter() - start) * 1000

    if response.status_code not in {200, 201, 409}:
        logger.error(
            "memory_upsert error text_len=%d status=%d ms=%.1f",
            len(text),
            response.status_code,
            elapsed,
        )
        return {
            "success": False,
            "status": response.status_code,
            "error": response.text[:500],
        }

    logger.info("memory_upsert ok text_len=%d ms=%.1f", len(text), elapsed)
    return {"success": True, "data": response.json() if response.content else {}}
