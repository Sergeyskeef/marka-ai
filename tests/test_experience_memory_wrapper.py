import sys
sys.path.append('/app/langchain_api')
sys.path.append('/app')
with open("/app/sys_path.log", "w") as f:
    f.write("PYTHONPATH: " + str(sys.path) + "\n")

import pytest
import time
from langchain_api.memory.memory_manager import MemoryManager, ExperienceMemoryWrapper

def get_test_manager():
    # Можно вынести в pytest fixture при необходимости
    return MemoryManager()

def test_experience_insert_and_search():
    mm = get_test_manager()
    wrapper = ExperienceMemoryWrapper(mm)
    session_id = f"test_session_{int(time.time())}"
    data = {
        "summary": "Q: Какой сегодня день?\nA: Сегодня пятница!",
        "source_ids": ["test_id_1", "test_id_2"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    }
    # Insert
    experience_id = wrapper.insert(data)
    assert experience_id is not None, "Experience insert failed"
    # Search
    results = wrapper.search("пятница", limit=3)
    assert any(session_id == r.get("session_id") for r in results), "Inserted experience not found in search"

def test_experience_snapshot():
    mm = get_test_manager()
    wrapper = ExperienceMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list) 