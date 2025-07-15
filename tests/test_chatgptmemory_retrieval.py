import pytest
from langchain_api.memory.memory_manager import MemoryManager
import time

def test_chatgptmemory_retrieval():
    mm = MemoryManager()
    wrapper = mm.memory_registry.get("ChatGPTMemory")
    # Уникальный тестовый текст
    test_text = f"Уникальный тестовый чанк для проверки retrieval {int(time.time())}"
    # Вставляем чанк
    obj_id = wrapper.insert({
        "text": test_text,
        "timestamp": "2025-05-30T12:00:00Z",
        "session_id": "test_session"
    })
    assert obj_id, "Не удалось вставить тестовый чанк в ChatGPTMemory!"
    # Даем индексации немного времени (если нужно)
    time.sleep(2)
    # Векторный поиск (near_text)
    results = wrapper.search("тестовый чанк", limit=5)
    found = any(test_text in (r.get("text") or "") for r in results)
    print(f"[DEBUG] near_text results: {results}")
    assert found, f"Чанк не найден через near_text! Результаты: {results}"
        print("[TEST] Retrieval по ChatGPTMemory через near_text работает корректно.") 