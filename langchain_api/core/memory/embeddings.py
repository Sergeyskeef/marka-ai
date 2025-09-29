from __future__ import annotations
from typing import List
import logging
import os

logger = logging.getLogger(__name__)

# Lazy import to avoid import-time failures if key not set
_client = None

async def _get_client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI()
    return _client

async def embed_text(text: str, *, model: str | None = None, dimensions: int | None = None) -> list[float]:
    """Return embedding for a single text.
    Defaults to text-embedding-3-small.
    """
    model = model or os.getenv('MARK_EMBED_MODEL', 'text-embedding-3-small')
    client = await _get_client()
    resp = await client.embeddings.create(model=model, input=text, dimensions=dimensions) if dimensions else await client.embeddings.create(model=model, input=text)
    return list(resp.data[0].embedding)

async def embed_texts(texts: List[str], *, model: str | None = None, dimensions: int | None = None) -> List[List[float]]:
    model = model or os.getenv('MARK_EMBED_MODEL', 'text-embedding-3-small')
    client = await _get_client()
    if dimensions:
        resp = await client.embeddings.create(model=model, input=texts, dimensions=dimensions)
    else:
        resp = await client.embeddings.create(model=model, input=texts)
    return [list(d.embedding) for d in resp.data]
