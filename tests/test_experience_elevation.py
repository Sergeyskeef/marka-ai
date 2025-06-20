import time
import pytest
from langchain_api.memory.memory_manager import MemoryManager

@pytest.fixture(scope="function")
def mm():
    return MemoryManager()

@pytest.fixture(scope="function")
def session_id():
    return f"pytest_elevate_{int(time.time())}"

def cleanup_experience(exp, session_id):
    # Удаляем все Experience с elevated=False и session_id != текущий
    all_exp = exp._fetch_objects_with_id(limit=100, filters=None, return_properties=["session_id", "elevated"])
    for e in all_exp:
        if e.get("elevated") is False and e.get("session_id") != session_id and e.get("id"):
            try:
                exp.collection.data.delete(e["id"])
            except Exception:
                pass

def wait_for_elevated(exp, session_id, summary, max_attempts=7, sleep_sec=1):
    for attempt in range(max_attempts):
        all_exp = exp._fetch_objects_with_id(limit=100, filters=None, return_properties=["summary", "elevated", "session_id", "id"])
        found = [e for e in all_exp if e.get("session_id") == session_id and e.get("summary") == summary]
        print(f"[wait_for_elevated] attempt={attempt+1}, found: {[{'id': e.get('id'), 'elevated': e.get('elevated')} for e in found]}")
        if found and all(e.get("elevated") is True for e in found):
            return found
        time.sleep(sleep_sec)
    # Если после всех попыток есть хотя бы один elevated=False, делаем прямой fetch по id
    if found and any(e.get("elevated") is not True for e in found):
        for e in found:
            if e.get("elevated") is not True and e.get("id"):
                single = exp._fetch_objects_with_id(limit=1, filters=None, return_properties=["summary", "elevated", "session_id", "id"])
                for obj in single:
                    if str(obj.get("id")) == str(e.get("id")):
                        print(f"[wait_for_elevated][SMART] id={e.get('id')}, elevated={obj.get('elevated')}")
                        if obj.get("elevated") is True:
                            e["elevated"] = True
        # Финальная пауза для eventual consistency
        time.sleep(3)
        # Ещё раз fetch по id
        for e in found:
            if e.get("elevated") is not True and e.get("id"):
                single = exp._fetch_objects_with_id(limit=1, filters=None, return_properties=["summary", "elevated", "session_id", "id"])
                for obj in single:
                    if str(obj.get("id")) == str(e.get("id")):
                        print(f"[wait_for_elevated][FINAL] id={e.get('id')}, elevated={obj.get('elevated')}")
                        if obj.get("elevated") is True:
                            e["elevated"] = True
        if all(e.get("elevated") is True for e in found):
            print("[wait_for_elevated][FINAL] elevated=True после финальной паузы")
            return found
        print(f"[wait_for_elevated][WARNING] Не все elevated=True: {[{'id': e.get('id'), 'elevated': e.get('elevated')} for e in found]}")
    return found

def test_repeat_cluster_elevation(mm, session_id):
    exp = mm.memory_registry.get("Experience")
    insight = mm.memory_registry.get("Insight")
    cleanup_experience(exp, session_id)
    summary = "Повторяющийся опыт для кластеризации"
    for i in range(3):
        exp.insert({
            "summary": summary,
            "source_ids": [f"src_repeat_{i}"],
            "timestamp": mm._get_rfc3339_timestamp(),
            "session_id": session_id
        })
    time.sleep(5)
    mm.automate_experience_elevation_scenarios(batch_size=10)
    time.sleep(2)
    found = wait_for_elevated(exp, session_id, summary)
    assert found, "Experience не найден (кластеризация)"
    assert all(e.get("elevated") is True for e in found), "Не все Experience были подняты (кластеризация)"
    time.sleep(1)
    all_insights = insight.collection.query.fetch_objects(limit=20, return_properties=["insight", "source_ids", "timestamp"]).objects
    print(f"[INSIGHT DEBUG] all_insights: {[getattr(ins, 'properties', ins) for ins in all_insights]}")
    # Проверяем, что есть инсайт, в котором есть все source_ids и session_id
    required_sources = {session_id, "src_repeat_0", "src_repeat_1", "src_repeat_2"}
    assert any(required_sources.issubset(set(getattr(ins, 'properties', ins).get('source_ids', []))) for ins in all_insights), "Insight не создан (кластеризация)"

def test_error_keyword_elevation(mm, session_id):
    exp = mm.memory_registry.get("Experience")
    insight = mm.memory_registry.get("Insight")
    cleanup_experience(exp, session_id)
    summary = "Ошибка: что-то пошло не так!"
    exp.insert({
        "summary": summary,
        "source_ids": ["src_error"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    })
    time.sleep(5)
    mm.automate_experience_elevation_scenarios(batch_size=5)
    time.sleep(2)
    found = wait_for_elevated(exp, session_id, summary)
    assert found, "Experience не найден (ошибка)"
    assert found[0].get("elevated") is True, "Experience не был поднят (ошибка)"
    time.sleep(1)
    all_insights = insight.collection.query.fetch_objects(limit=10, return_properties=["insight", "source_ids", "timestamp"]).objects
    print(f"[INSIGHT DEBUG] all_insights: {[getattr(ins, 'properties', ins) for ins in all_insights]}")
    assert any('src_error' in getattr(ins, 'properties', ins).get('source_ids', []) for ins in all_insights), "Insight не создан (ошибка)"

def test_rubric_score_error_elevation(mm, session_id):
    exp = mm.memory_registry.get("Experience")
    insight = mm.memory_registry.get("Insight")
    # Очищаем старые объекты
    cleanup_experience(exp, session_id)
    summary = "Ошибка при выполнении теста (rubric_score)"
    exp_id = exp.insert({
        "summary": summary,
        "rubric_score": 0.3,
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    })
    print(f"[DEBUG][test] Вставлен Experience id: {exp_id}")
    time.sleep(5)
    mm.automate_experience_elevation_scenarios(batch_size=10)
    time.sleep(2)
    # Проверяем, что elevated стал True
    all_exp = exp._fetch_objects_with_id(limit=100, filters=None, return_properties=["id", "elevated", "summary", "session_id"])
    found = [obj for obj in all_exp if obj.get("id") == exp_id]
    print(f"[DEBUG][test] Experience после подъёма: {found}")
    assert found and found[0].get("elevated") is True, f"Experience не был поднят: {found}"

def test_success_keyword_elevation(mm, session_id):
    exp = mm.memory_registry.get("Experience")
    insight = mm.memory_registry.get("Insight")
    cleanup_experience(exp, session_id)
    summary = "Успешно решено!"
    exp.insert({
        "summary": summary,
        "source_ids": ["src_success"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    })
    time.sleep(5)
    mm.automate_experience_elevation_scenarios(batch_size=5)
    time.sleep(2)
    found = wait_for_elevated(exp, session_id, summary)
    assert found, "Experience не найден (успех)"
    assert found[0].get("elevated") is True, "Experience не был поднят (успех)"
    time.sleep(1)
    all_insights = insight.collection.query.fetch_objects(limit=10, return_properties=["insight", "source_ids", "timestamp"]).objects
    print(f"[INSIGHT DEBUG] all_insights: {[getattr(ins, 'properties', ins) for ins in all_insights]}")
    assert any('src_success' in getattr(ins, 'properties', ins).get('source_ids', []) for ins in all_insights), "Insight не создан (успех)"

def test_rubric_score_success_elevation(mm, session_id):
    exp = mm.memory_registry.get("Experience")
    insight = mm.memory_registry.get("Insight")
    cleanup_experience(exp, session_id)
    summary = "Высокий балл за выполнение"
    exp.insert({
        "summary": summary,
        "source_ids": ["src_success_score"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id,
        "rubric_score": 0.95
    })
    time.sleep(5)
    mm.automate_experience_elevation_scenarios(batch_size=5)
    time.sleep(2)
    found = wait_for_elevated(exp, session_id, summary)
    assert found, "Experience не найден (rubric_score success)"
    assert found[0].get("elevated") is True, "Experience не был поднят (rubric_score success)"
    time.sleep(1)
    all_insights = insight.collection.query.fetch_objects(limit=10, return_properties=["insight", "source_ids", "timestamp"]).objects
    print(f"[INSIGHT DEBUG] all_insights: {[getattr(ins, 'properties', ins) for ins in all_insights]}")
    assert any(session_id in str(getattr(ins, 'properties', ins)) for ins in all_insights), "Insight не создан (rubric_score success)"

def test_manual_elevate_guaranteed(mm, session_id):
    exp = mm.memory_registry.get("Experience")
    cleanup_experience(exp, session_id)
    summary = "Только ручной подъём"
    exp.insert({
        "summary": summary,
        "source_ids": ["src_manual_pytest"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id,
        "manual_elevate": True
    })
    time.sleep(5)
    mm.automate_experience_elevation_scenarios(batch_size=5)
    time.sleep(2)
    found = wait_for_elevated(exp, session_id, summary)
    assert found, "manual_elevate Experience не найден"
    assert found[0].get("elevated") is True, "manual_elevate Experience не был поднят!" 