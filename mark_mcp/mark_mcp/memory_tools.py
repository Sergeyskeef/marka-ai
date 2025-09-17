import httpx
from .config import settings


async def memory_search(query: str, limit: int = 10) -> dict:
	async with httpx.AsyncClient(base_url=settings.graphiti_url, timeout=settings.request_timeout_s) as client:
		r = await client.get("/nodes", params={"search": query, "limit": limit})
		if r.status_code != 200:
			return {"items": [], "total": 0, "error": f"HTTP {r.status_code}"}
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
		return {"items": items, "total": len(items)}


async def memory_upsert(text: str, metadata: dict | None = None) -> dict:
	payload = {
		"id": None,  # let server assign if supported, else ignore
		"type": "Episode",
		"properties": {"msg": text, **(metadata or {})},
	}
	async with httpx.AsyncClient(base_url=settings.graphiti_url, timeout=settings.request_timeout_s) as client:
		r = await client.post("/nodes", json=payload)
		if r.status_code not in (200, 201, 409):
			return {"success": False, "status": r.status_code, "error": r.text}
		return {"success": True, "data": r.json() if r.content else {}}
