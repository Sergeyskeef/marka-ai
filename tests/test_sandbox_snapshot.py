import pytest
from langchain_api.memory.memory_manager import MemoryManager
import uuid
import time

@pytest.fixture(scope="module")
def memory_manager():
    return MemoryManager()

def test_create_snapshot(memory_manager):
    snap_id = memory_manager.create_snapshot(session_id="test_session", object_types=["Memory"], with_state=True, meta="test meta")
    assert snap_id, "Snapshot не создан"

def test_list_snapshots(memory_manager):
    snaps = memory_manager.list_snapshots(session_id="test_session")
    assert snaps, "Список снапшотов пуст"
    assert any("snapshot_id" in s for s in snaps), "Нет snapshot_id в результатах"

def test_restore_snapshot(memory_manager):
    snaps = memory_manager.list_snapshots(session_id="test_session")
    snap_obj = snaps[0]
    restored = memory_manager.restore_snapshot(snap_obj["snapshot_id"])
    assert restored, "restore_snapshot не вернул объект"
    assert restored["snapshot_id"] == snap_obj["snapshot_id"]

def test_diff_snapshots(memory_manager):
    snaps = memory_manager.list_snapshots(session_id="test_session")
    snap_obj = snaps[0]
    diff = memory_manager.diff_snapshots(snap_obj["snapshot_id"], snap_obj["snapshot_id"])
    assert "added" in diff and "removed" in diff and "changed" in diff, "diff_snapshots не вернул diff"

def test_rollback_restore(memory_manager):
    mem = memory_manager.memory_registry.get("Memory")
    unique_id = str(uuid.uuid4())
    session_id = f"rollback_test_{unique_id}"
    msg = {"sender": "user", "message": f"rollback test {unique_id}", "timestamp": memory_manager._get_rfc3339_timestamp(), "importance": 0.0, "session_id": session_id}
    mem_id = mem.insert(msg)
    assert mem_id, "Не удалось добавить объект в Memory"
    snap_id = memory_manager.create_snapshot(session_id=session_id, object_types=["Memory"], with_state=True, meta="rollback test")
    assert snap_id, "Snapshot не создан для rollback"
    time.sleep(2)
    snap_check = memory_manager.restore_snapshot(snap_id)
    assert snap_check is not None, "Снапшот не найден сразу после создания"
    mem.collection.data.delete_by_id(mem_id)
    time.sleep(2)
    from weaviate.classes.query import Filter
    filters = Filter.by_id().contains_any([mem_id])
    found = mem.collection.query.fetch_objects(filters=filters, limit=1).objects
    assert not found, "Объект не был удалён из Memory (по id)"
    snap = memory_manager.restore_snapshot(snap_id)
    import json
    state = json.loads(snap["object_states"])
    restored_objs = state.get("Memory", [])
    restored = any(o.get("message") == msg["message"] for o in restored_objs)
    assert restored, "Объект не восстановлен из снапшота (state)" 