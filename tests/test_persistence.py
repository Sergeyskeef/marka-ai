import pytest
import time
import os
from langchain_api.memory.memory_manager import MemoryManager, MemoryMemoryWrapper

TEST_MESSAGE = "Тест на персистентность (memory, weaviate)"
PERSIST_FILE = "/app/langchain_api/tests/persist_id.txt"

@pytest.fixture(scope="module")
def memory_manager():
    return MemoryManager()

def test_insert_memory_and_save_id(memory_manager):
    """
    1. Вставляет уникальный объект в Memory (Weaviate), сохраняет его id и session_id в общий файл.
    2. После этого шага нужно перезапустить контейнер app.
    3. Следующий тест проверит наличие объекта после рестарта.
    """
    wrapper = MemoryMemoryWrapper(memory_manager)
    session_id = f"persist_{int(time.time())}_{os.getpid()}"
    data = {
        "sender": "user",
        "message": TEST_MESSAGE,
        "timestamp": memory_manager._get_rfc3339_timestamp(),
        "importance": 0.1,
        "session_id": session_id
    }
    memory_id = wrapper.insert(data)
    assert memory_id, "Memory insert failed"
    with open(PERSIST_FILE, "w") as f:
        f.write(f"{memory_id}\n{session_id}\n")
    print(f"[TEST][persist] Сохранил id: {memory_id}, session_id: {session_id} в {PERSIST_FILE}")
    print("Теперь перезапусти контейнер app и запусти test_memory_persistence_after_restart")

def test_memory_persistence_after_restart(memory_manager):
    """
    1. Читает id и session_id из общего файла.
    2. Проверяет, что объект с этим id и session_id есть в Memory (Weaviate) после рестарта контейнера.
    3. После проверки удаляет файл persist_id.txt
    """
    assert os.path.exists(PERSIST_FILE), f"Файл {PERSIST_FILE} не найден. Сначала запусти test_insert_memory_and_save_id."
    with open(PERSIST_FILE, "r") as f:
        lines = f.readlines()
    memory_id = lines[0].strip()
    session_id = lines[1].strip()
    wrapper = MemoryMemoryWrapper(memory_manager)
    # Проверяем по id (Weaviate)
    from weaviate.classes.query import Filter
    filter_obj = Filter.by_id().contains_any([memory_id])
    found = wrapper.collection.query.fetch_objects(filters=filter_obj, limit=1).objects
    assert found, f"Объект с id={memory_id} не найден в Weaviate после рестарта контейнера!"
    # Проверяем по session_id (Weaviate)
    filter_obj2 = Filter.by_property("session_id").equal(session_id)
    found2 = wrapper.collection.query.fetch_objects(filters=filter_obj2, limit=10).objects
    assert any(getattr(obj, 'properties', obj).get("message") == TEST_MESSAGE for obj in found2), f"Объект с session_id={session_id} не найден в Weaviate после рестарта!"
    print(f"[TEST][persist] Объект найден после рестарта: id={memory_id}, session_id={session_id}")
    # Чистим файл после проверки
    os.remove(PERSIST_FILE) 