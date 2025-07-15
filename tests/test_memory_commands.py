from langchain_api.memory_logic import (
    memory_analyze_logic,
    memory_delete_logic,
    memory_save_logic,
    memory_update_logic,
)


class DummyMemoryManager:
    def __init__(self, data=None):
        self.data = data or []
        self.last_inserted = None
        self.last_updated = None
        self.last_deleted = None
    def insert(self, obj):
        self.data.append(obj)
        self.last_inserted = obj
        return len(self.data)
    def update(self, obj_id, obj):
        self.last_updated = (obj_id, obj)
        return True if obj_id == '1' else False
    def delete(self, obj_id):
        self.last_deleted = obj_id
        return True if obj_id == '1' else False
    def snapshot(self):
        return {"snapshot": self.data}

class DummyMemory:
    def __init__(self, data=None):
        self.memory_manager = type('mm', (), {'memory_registry': {'Experience': DummyMemoryManager(data)}})()

def test_memory_save_success():
    memory = DummyMemory([])
    result = memory_save_logic('experience', 'Тестовая запись', memory)
    assert 'Объект сохранён' in result
    assert memory.memory_manager.memory_registry['Experience'].last_inserted['summary'] == 'Тестовая запись'

def test_memory_save_unsupported_type():
    memory = DummyMemory([])
    result = memory_save_logic('unknown', 'Тест', memory)
    assert result is None

def test_memory_update_success():
    memory = DummyMemory([])
    result = memory_update_logic('experience', '1', {'summary': 'Обновлено'}, memory)
    assert 'обновлён' in result
    assert memory.memory_manager.memory_registry['Experience'].last_updated == ('1', {'summary': 'Обновлено'})

def test_memory_update_fail():
    memory = DummyMemory([])
    result = memory_update_logic('experience', '2', {'summary': 'Обновлено'}, memory)
    assert 'Не удалось обновить' in result

def test_memory_delete_success():
    memory = DummyMemory([])
    result = memory_delete_logic('experience', '1', memory)
    assert 'удалён' in result
    assert memory.memory_manager.memory_registry['Experience'].last_deleted == '1'

def test_memory_delete_fail():
    memory = DummyMemory([])
    result = memory_delete_logic('experience', '2', memory)
    assert 'Не удалось удалить' in result

def test_memory_analyze():
    memory = DummyMemory([
        {'summary': 'A'},
        {'summary': 'B'},
        {'summary': 'A'}
    ])
    result = memory_analyze_logic(memory)
    assert 'дубликатов' in result
    assert '- Experience:' in result
