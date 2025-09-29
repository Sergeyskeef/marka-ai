import httpx
import os
import json
import time
import logging
from .config import settings
from .models_memory import MemoryMetadata
from typing import Optional, Dict, Any

logger = logging.getLogger("mark-mcp.memory")

try:
    import redis.asyncio as redis
except Exception:
    redis = None

_redis = None
def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    url = os.getenv("REDIS_URL")
    if not url or not redis:
        return None
    _redis = redis.from_url(url, encoding="utf-8", decode_responses=True)
    return _redis

_client: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
	"""
	Singleton AsyncClient with connection pooling and retries.
	"""
	global _client
	if _client is None:
		transport = httpx.AsyncHTTPTransport(retries=3)  # httpx 0.28+ backoff
		_client = httpx.AsyncClient(
			base_url=settings.graphiti_url,
			timeout=settings.request_timeout_s,
			transport=transport,
			headers={"Accept": "application/json"},
		)
	return _client


async def memory_search(query: str, limit: int = 10) -> dict:
	start = time.perf_counter()
	rds = _get_redis()
	key = f"mem:search:{query}:{limit}"
	if rds:
		cached = await rds.get(key)
		if cached:
			elapsed = (time.perf_counter() - start) * 1000
			logger.info("memory_search cache_hit query=%r limit=%d ms=%.1f", query, limit, elapsed)
			return json.loads(cached)
	
	client = _get_client()
	r = await client.get("/nodes", params={"search": query, "limit": limit})
	elapsed = (time.perf_counter() - start) * 1000
	
	if r.status_code != 200:
		logger.error("memory_search error query=%r limit=%d status=%d ms=%.1f", query, limit, r.status_code, elapsed)
		return {"items": [], "total": 0, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
	
	data = r.json()
	items = []
	for node in data.get("nodes", []):
		if node.get("type") == "Episode":
			props = node.get("properties", {})
			items.append({
				"id": node.get("id"),
				"text": props.get("msg", ""),
				"metadata": {k: v for k, v in props.items() if k != "msg"},
			})
	result = {"items": items, "total": len(items)}
	if rds:
		await rds.setex(key, 60, json.dumps(result, ensure_ascii=False))
	
	logger.info("memory_search ok query=%r limit=%d ms=%.1f", query, limit, elapsed)
	return result


async def memory_upsert(text: str, metadata: dict | None = None) -> dict:
	start = time.perf_counter()
	# Валидируем метаданные
	validated_metadata = {}
	if metadata:
		meta = MemoryMetadata(**(metadata or {})).model_dump(exclude_none=True)
		validated_metadata.update(meta)
	
	payload: Dict[str, Any] = {
		"id": None,  # let server assign if supported, else ignore
		"type": "Episode",
		"properties": {"msg": text, **validated_metadata},
	}
	client = _get_client()
	r = await client.post("/nodes", json=payload)
	elapsed = (time.perf_counter() - start) * 1000
	
	if r.status_code not in (200, 201, 409):
		logger.error("memory_upsert error text_len=%d status=%d ms=%.1f", len(text), r.status_code, elapsed)
		return {"success": False, "status": r.status_code, "error": r.text[:500]}
	
	logger.info("memory_upsert ok text_len=%d ms=%.1f", len(text), elapsed)
	return {"success": True, "data": r.json() if r.content else {}}
