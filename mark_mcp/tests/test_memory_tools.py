import asyncio
import json
import pytest
import respx
from httpx import Response
from mark_mcp.memory_tools import memory_search, memory_upsert

@pytest.mark.asyncio
async def test_memory_search_ok():
    with respx.mock(base_url="http://graphiti:7878") as mock:
        mock.get("/nodes").respond(200, json={"nodes":[
            {"id":"1","type":"Episode","properties":{"msg":"hello","tag":"x"}},
            {"id":"2","type":"Other","properties":{}},
        ]})
        res = await memory_search("hello", limit=2)
        assert res["total"] == 1
        assert res["items"][0]["text"] == "hello"

@pytest.mark.asyncio
async def test_memory_upsert_ok():
    with respx.mock(base_url="http://graphiti:7878") as mock:
        mock.post("/nodes").respond(201, json={"id":"1"})
        res = await memory_upsert("hello", {"source":"test"})
        assert res["success"] is True
