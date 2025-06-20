"""
Тесты для MemoryClass-обёрток (insert/search/snapshot для всех коллекций).

Как запускать:
    # Запускать ТОЛЬКО внутри Docker-контейнера app, чтобы все импорты и окружение совпадали с боевым.
    # Из корня проекта:
    docker compose -f langchain_api/docker-compose.yml exec app pytest langchain_api/tests/test_memoryclass_wrappers.py --maxfail=3 --disable-warnings -v

    # Или для всех тестов:
    docker compose -f langchain_api/docker-compose.yml exec app pytest langchain_api/tests/ --maxfail=3 --disable-warnings -v

    # Если файл не виден — пересобрать контейнеры:
    docker compose -f langchain_api/docker-compose.yml build
    docker compose -f langchain_api/docker-compose.yml up -d

Шаблон для новых тестов:
    - Все тесты должны начинаться с test_...
    - Использовать только публичные интерфейсы (MemoryClass-обёртки).
    - Не использовать прямые обращения к Weaviate SDK.
    - Для новых коллекций — копировать структуру этого файла.
"""
import sys
sys.path.append('/app/langchain_api')
sys.path.append('/app')
import pytest
import time
from langchain_api.memory.memory_manager import MemoryManager, InsightMemoryWrapper, MemoryMemoryWrapper, PersonaMemoryWrapper, UserFactsMemoryWrapper, ChatGPTMemoryWrapper, CriticLogMemoryWrapper

def get_test_manager():
    return MemoryManager()

def test_insight_insert_and_search():
    mm = get_test_manager()
    wrapper = InsightMemoryWrapper(mm)
    session_id = f"test_session_{int(time.time())}"
    data = {
        "insight": "Это инсайт для теста",
        "source_ids": [session_id],
        "timestamp": mm._get_rfc3339_timestamp()
    }
    insight_id = wrapper.insert(data)
    assert insight_id is not None, "Insight insert failed"
    # Диагностика: выводим все объекты
    all_objs = wrapper.collection.query.fetch_objects(limit=10).objects
    print(f"[DEBUG][Insight] Все объекты: {[getattr(obj, 'properties', obj) for obj in all_objs]}")
    # Диагностика: фильтр по source_ids
    from weaviate.classes.query import Filter
    filter_obj = Filter.by_property("source_ids").contains_any([session_id])
    filtered = wrapper.collection.query.fetch_objects(filters=filter_obj, limit=10).objects
    print(f"[DEBUG][Insight] Поиск по source_ids={session_id}: {[getattr(obj, 'properties', obj) for obj in filtered]}")
    results = wrapper.search(
        "инсайт",
        limit=3,
        filter_by={"source_ids": [session_id]},
        fallback_to_filter=True
    )
    assert any(session_id in r.get("source_ids", []) for r in results), "Inserted insight not found in search"

def test_insight_snapshot():
    mm = get_test_manager()
    wrapper = InsightMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list)

def test_memory_insert_and_search():
    mm = get_test_manager()
    wrapper = MemoryMemoryWrapper(mm)
    session_id = f"test_session_{int(time.time())}"
    data = {
        "sender": "user",
        "message": "Тестовое сообщение",
        "timestamp": mm._get_rfc3339_timestamp(),
        "importance": 0.1,
        "session_id": session_id
    }
    memory_id = wrapper.insert(data)
    assert memory_id is not None, "Memory insert failed"
    # Диагностика: выводим все объекты
    all_objs = wrapper.collection.query.fetch_objects(limit=10).objects
    print(f"[DEBUG][Memory] Все объекты: {[getattr(obj, 'properties', obj) for obj in all_objs]}")
    # Диагностика: фильтр по session_id
    from weaviate.classes.query import Filter
    filter_obj = Filter.by_property("session_id").equal(session_id)
    filtered = wrapper.collection.query.fetch_objects(filters=filter_obj, limit=10).objects
    print(f"[DEBUG][Memory] Поиск по session_id={session_id}: {[getattr(obj, 'properties', obj) for obj in filtered]}")
    for attempt in range(5):
        time.sleep(5)
        results = wrapper.search(
            "тестовое",
            limit=3,
            filter_by={"session_id": session_id},
            fallback_to_filter=True
        )
        if any(session_id == r.get("session_id") for r in results):
            break
    else:
        assert False, "Inserted memory not found in search (даже через 2 минуты)"

def test_memory_snapshot():
    mm = get_test_manager()
    wrapper = MemoryMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list)

def test_persona_insert_and_search():
    mm = get_test_manager()
    wrapper = PersonaMemoryWrapper(mm)
    name = f"Persona_{int(time.time())}"
    data = {
        "name": name,
        "description": "Тестовая персона",
        "traits": "дружелюбный",
        "timestamp": mm._get_rfc3339_timestamp()
    }
    persona_id = wrapper.insert(data)
    assert persona_id is not None, "Persona insert failed"
    results = wrapper.search(
        name,
        limit=3,
        filter_by={"name": name},
        fallback_to_filter=True
    )
    assert any(name == r.get("name") for r in results), "Inserted persona not found in search"

def test_persona_snapshot():
    mm = get_test_manager()
    wrapper = PersonaMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list)

def test_userfacts_insert_and_search():
    mm = get_test_manager()
    wrapper = UserFactsMemoryWrapper(mm)
    user_id = f"user_{int(time.time())}"
    data = {
        "user_id": user_id,
        "key": "test_key",
        "value": "test_value",
        "confidence": 1.0,
        "timestamp": mm._get_rfc3339_timestamp()
    }
    userfact_id = wrapper.insert(data)
    assert userfact_id is not None, "UserFacts insert failed"
    for attempt in range(5):
        time.sleep(5)
        results = wrapper.search(
            "test_value",
            limit=3,
            filter_by={"user_id": user_id},
            fallback_to_filter=True
        )
        if any(user_id == r.get("user_id") for r in results):
            break
    else:
        assert False, "Inserted userfact not found in search (даже через 2 минуты)"

def test_userfacts_snapshot():
    mm = get_test_manager()
    wrapper = UserFactsMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list)

def test_chatgptmemory_insert_and_search():
    mm = get_test_manager()
    wrapper = ChatGPTMemoryWrapper(mm)
    session_id = f"cgpt_{int(time.time())}"
    data = {
        "text": "Тест CGPT memory",
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    }
    cgpt_id = wrapper.insert(data)
    assert cgpt_id is not None, "ChatGPTMemory insert failed"
    results = wrapper.search(
        "CGPT",
        limit=3,
        filter_by={"session_id": session_id},
        fallback_to_filter=True
    )
    assert any(session_id == r.get("session_id") for r in results), "Inserted CGPT memory not found in search"

def test_chatgptmemory_snapshot():
    mm = get_test_manager()
    wrapper = ChatGPTMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list)

def test_criticlog_insert_and_search():
    mm = get_test_manager()
    wrapper = CriticLogMemoryWrapper(mm)
    session_id = f"criticlog_{int(time.time())}"
    data = {
        "action": "analyze",
        "details": "{\"info\": \"test\"}",
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id,
        "status": "success",
        "error_message": "",
        "source_ids": [session_id]
    }
    log_id = wrapper.insert(data)
    assert log_id is not None, "CriticLog insert failed"
    # Диагностика: выводим все объекты
    all_objs = wrapper.collection.query.fetch_objects(limit=10).objects
    print(f"[DEBUG][CriticLog] Все объекты: {[getattr(obj, 'properties', obj) for obj in all_objs]}")
    # Диагностика: фильтр по source_ids
    from weaviate.classes.query import Filter
    filter_obj = Filter.by_property("source_ids").contains_any([session_id])
    filtered = wrapper.collection.query.fetch_objects(filters=filter_obj, limit=10).objects
    print(f"[DEBUG][CriticLog] Поиск по source_ids={session_id}: {[getattr(obj, 'properties', obj) for obj in filtered]}")
    results = wrapper.search(
        "analyze",
        limit=3,
        filter_by={"source_ids": [session_id]},
        fallback_to_filter=True
    )
    assert any(session_id in r.get("source_ids", []) for r in results), "Inserted CriticLog not found in search"

def test_criticlog_snapshot():
    mm = get_test_manager()
    wrapper = CriticLogMemoryWrapper(mm)
    snap = wrapper.snapshot()
    assert "snapshot" in snap
    assert isinstance(snap["snapshot"], list)

def test_automate_experience_to_insight():
    mm = MemoryManager()
    exp_wrapper = mm.memory_registry.get("Experience")
    insight_wrapper = mm.memory_registry.get("Insight")
    criticlog_wrapper = mm.memory_registry.get("CriticLog")
    session_id = f"autoexp_{int(time.time())}"
    # Вставляем 5 одинаковых Experience
    for i in range(5):
        exp_wrapper.insert({
            "summary": "Похожий кейс для автотеста",  # одинаковый summary
            "source_ids": [f"src_{i}"],
            "timestamp": mm._get_rfc3339_timestamp(),
            "session_id": session_id
        })
    # Диагностика: выводим все Experience после вставки
    all_exp_diag = exp_wrapper._fetch_objects_with_id(limit=100, filters=None)
    print(f"[DEBUG][test] Все Experience после вставки: {[{'id': e.get('id'), 'session_id': e.get('session_id'), 'elevated': e.get('elevated')} for e in all_exp_diag]}")
    # Даем время на автоматизацию (если асинхронно)
    for attempt in range(5):
        time.sleep(6)
    insights = insight_wrapper.search(
        "Похожий кейс",
        limit=5,
        filter_by={"source_ids": [session_id]},
        fallback_to_filter=True
    )
    print(f"[DEBUG][test] Найденные инсайты: {[r.get('source_ids') for r in insights]}")
    found = any(session_id in (r.get("source_ids") or []) or session_id in str(r) for r in insights)
    if found:
        break
    else:
        assert False, "Insight не создан автоматически по новым Experience"
    # Проверяем, что хотя бы один Experience с этим session_id имеет elevated=True
    for attempt in range(5):
        time.sleep(6)
        all_exp = exp_wrapper._fetch_objects_with_id(limit=100, filters=None)
        my_exp = [e for e in all_exp if e.get("session_id") == session_id and e.get("elevated") is True]
        print(f"[DEBUG][test] Experience elevated=True: {len(my_exp)} из {len([e for e in all_exp if e.get('session_id') == session_id])}")
        if my_exp:
            break
    else:
        assert False, "Нет ни одного Experience elevated=True после автоматизации (session_id)"
    # Проверяем, что есть логи в CriticLog
    logs = criticlog_wrapper.search(
        "elevate_analyze",
        limit=5,
        filter_by={"action": "elevate_analyze", "session_id": session_id},
        fallback_to_filter=True
    )
    assert any(session_id in str(r) for r in logs), "Нет логов elevate_analyze в CriticLog"

def test_no_duplicate_insights():
    mm = MemoryManager()
    exp_wrapper = mm.memory_registry.get("Experience")
    insight_wrapper = mm.memory_registry.get("Insight")
    session_id = f"autoexp_nodup_{int(time.time())}"
    # Вставляем 5 похожих Experience
    for i in range(5):
        exp_wrapper.insert({
            "summary": f"Похожий кейс для дублей {i}",
            "source_ids": [f"src_{i}"],
            "timestamp": mm._get_rfc3339_timestamp(),
            "session_id": session_id
        })
    time.sleep(5)
    # Считаем инсайты после первого автозапуска
    insights1 = insight_wrapper.search(
        "Похожий кейс",
        limit=10,
        filter_by={"source_ids": [session_id]},
        fallback_to_filter=True
    )
    count1 = len(insights1)
    assert count1 > 0, "Insight не создан после первого запуска автоматизации"
    # Явно вызываем automate_experience_to_insight ещё раз
    mm.automate_experience_elevation_scenarios()
    time.sleep(3)
    # Считаем инсайты снова
    insights2 = insight_wrapper.search(
        "Похожий кейс",
        limit=10,
        filter_by={"source_ids": [session_id]},
        fallback_to_filter=True
    )
    count2 = len(insights2)
    assert count2 == count1, f"Появились дублирующие инсайты: было {count1}, стало {count2}" 