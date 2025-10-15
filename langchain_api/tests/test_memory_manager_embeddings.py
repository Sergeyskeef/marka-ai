import os
from typing import Any

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from core.memory.memory_manager import MemoryManager


class DummyResult:
    def __init__(self, payload: dict):
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_hybrid_search_uses_embed_text(monkeypatch):
    payload = {
        "id": "1",
        "text": "result",
        "score": 0.9,
        "source": "graphiti",
        "metadata": {},
    }

    captured: dict = {}

    async def fake_embed(text: str, **_: dict):
        captured["text"] = text
        return [0.1, 0.2, 0.3]

    class DummyEngine:
        def __init__(self, adapter):  # pragma: no cover - adapter not used in test
            self.adapter = adapter

        async def search(self, **kwargs):
            captured["filters"] = kwargs.get("filters") or {}
            return [DummyResult(payload)]

    monkeypatch.setattr("core.memory.memory_manager.embed_text", fake_embed)
    monkeypatch.setattr("core.memory.memory_manager.HybridSearchEngine", DummyEngine)

    manager = MemoryManager()

    results = await manager.hybrid_search("query", user_id="user")

    assert captured["text"] == "query"
    assert captured["filters"]["query_embedding"] == [0.1, 0.2, 0.3]
    assert results == [payload]


@pytest.mark.asyncio
async def test_hybrid_search_fallback_without_embeddings(monkeypatch):
    payload = {
        "id": "2",
        "text": "result",
        "score": 0.8,
        "source": "graphiti",
        "metadata": {},
    }

    filters_holder: dict = {}

    async def failing_embed(*_, **__):
        raise RuntimeError("boom")

    class DummyEngine:
        def __init__(self, adapter):  # pragma: no cover - adapter not used in test
            self.adapter = adapter

        async def search(self, **kwargs):
            filters_holder.update(kwargs.get("filters") or {})
            return [DummyResult(payload)]

    monkeypatch.setattr("core.memory.memory_manager.embed_text", failing_embed)
    monkeypatch.setattr("core.memory.memory_manager.HybridSearchEngine", DummyEngine)

    manager = MemoryManager()

    results = await manager.hybrid_search("query", user_id="user")

    assert "query_embedding" not in filters_holder
    assert results == [payload]


@pytest.mark.asyncio
async def test_hybrid_search_applies_metadata_filters(monkeypatch):
    items = [
        {
            "id": "1",
            "text": "kept",
            "similarity": 0.9,
            "metadata": {"user_id": "user", "type": "note"},
        },
        {
            "id": "2",
            "text": "filtered-by-user",
            "similarity": 0.95,
            "metadata": {"user_id": "other", "type": "note"},
        },
        {
            "id": "3",
            "text": "filtered-by-type",
            "similarity": 0.88,
            "metadata": {"user_id": "user", "type": "task"},
        },
    ]

    class DummyGraphitiAdapter:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        async def search_episodes(self, query: str, limit: int, user_id: str | None = None):
            self.calls.append({"query": query, "limit": limit, "user_id": user_id})
            return {"items": items, "total": len(items)}

    async def fake_embed(*_, **__):
        return []

    dummy_adapter = DummyGraphitiAdapter()
    monkeypatch.setattr("core.memory.memory_manager.graphiti_adapter", dummy_adapter)
    monkeypatch.setattr("core.memory.memory_manager.embed_text", fake_embed)

    manager = MemoryManager()

    results = await manager.hybrid_search(
        "query",
        user_id="user",
        filters={"metadata": {"user_id": "user", "type": "note"}},
    )

    assert dummy_adapter.calls and dummy_adapter.calls[0]["user_id"] == "user"
    assert [r["id"] for r in results] == ["1"]
    assert results[0]["metadata"]["type"] == "note"


@pytest.mark.asyncio
async def test_hybrid_search_time_window_and_dedup(monkeypatch):
    import time
    from datetime import timedelta

    now = time.time()
    items = [
        {
            "id": "1",
            "text": "older-duplicate",
            "similarity": 0.6,
            "metadata": {"user_id": "user", "created_at": now - 120},
        },
        {
            "id": "1",
            "text": "newer-duplicate",
            "similarity": 0.95,
            "metadata": {"user_id": "user", "created_at": now - 30},
        },
        {
            "id": "2",
            "text": "too-old",
            "similarity": 0.99,
            "metadata": {"user_id": "user", "created_at": now - 60 * 60 * 24},
        },
    ]

    class DummyGraphitiAdapter:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        async def search_episodes(self, query: str, limit: int, user_id: str | None = None):
            self.calls.append({"query": query, "limit": limit, "user_id": user_id})
            return {"items": items, "total": len(items)}

    async def fake_embed(*_, **__):
        return []

    dummy_adapter = DummyGraphitiAdapter()
    monkeypatch.setattr("core.memory.memory_manager.graphiti_adapter", dummy_adapter)
    monkeypatch.setattr("core.memory.memory_manager.embed_text", fake_embed)

    manager = MemoryManager()

    results = await manager.hybrid_search(
        "query",
        user_id="user",
        time_window=timedelta(minutes=5),
    )

    assert dummy_adapter.calls and dummy_adapter.calls[0]["user_id"] == "user"
    assert len(results) == 1
    assert results[0]["id"] == "1"
    assert results[0]["text"] == "newer-duplicate"
