import os

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
