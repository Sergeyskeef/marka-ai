from langchain_api.memory_logic import memory_search_logic


class DummyMemoryManager:
    def __init__(self, data):
        self.data = data
    def search(self, query, limit=5):
        # Примитивная эмуляция поиска
        return [item for item in self.data if query.lower() in item.get('summary', '').lower()][:limit]

class DummyMemory:
    def __init__(self, data):
        self.memory_manager = type('mm', (), {'memory_registry': {'Experience': DummyMemoryManager(data)}})()

def test_memory_search_found():
    memory = DummyMemory([
        {'summary': 'Архетип Марка'},
        {'summary': 'Другое'}
    ])
    result = memory_search_logic('experience', 'Архетип', memory)
    assert 'Архетип Марка' in result
    assert 'Результаты поиска' in result

def test_memory_search_not_found():
    memory = DummyMemory([
        {'summary': 'Другое'}
    ])
    result = memory_search_logic('experience', 'Архетип', memory)
    assert "ничего не найдено" in result

def test_memory_search_unsupported_type():
    memory = DummyMemory([])
    result = memory_search_logic('unknown', 'Архетип', memory)
    assert result is None
