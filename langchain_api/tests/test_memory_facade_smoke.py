import asyncio
import pytest

@pytest.mark.asyncio
async def test_facade_store_and_search():
    import os, sys
    sys.path.append('/srv/mark/langchain_api')
    os.environ['MARK_MEMORY_FACADE'] = '1'
    from core.memory.memory_manager import memory_manager

    text = 'SMOKE: facade memory save & search'
    res = await memory_manager.add_episode(text, {'user_id':'test'})
    assert res.get('success') is True

    found = await memory_manager.hybrid_search(query='facade memory', user_id='test', k=5)
    assert isinstance(found, list)
    assert any(text in (it.get('text') or '') for it in found)
