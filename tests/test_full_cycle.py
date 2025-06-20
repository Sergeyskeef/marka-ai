import time
import pytest
from langchain_api.memory.memory_manager import MemoryManager

def wait_for_elevated(exp, session_id, summary, max_attempts=10, sleep_sec=2):
    for attempt in range(max_attempts):
        all_exp = exp._fetch_objects_with_id(limit=100, filters=None, return_properties=["summary", "elevated", "session_id", "id"])
        found = [e for e in all_exp if e.get("session_id") == session_id and e.get("summary") == summary]
        print(f"[wait_for_elevated] attempt={attempt+1}, found: {[{'id': e.get('id'), 'elevated': e.get('elevated')} for e in found]}")
        if found and all(e.get("elevated") is True for e in found):
            return found
        time.sleep(sleep_sec)
    return found

def cleanup_experience(exp, summaries):
    # Удаляет все Experience с указанными summary (для чистоты теста)
    all_exp = exp._fetch_objects_with_id(limit=200, filters=None, return_properties=["summary", "elevated", "session_id", "id"])
    for s in summaries:
        for e in all_exp:
            if e.get("summary") == s:
                try:
                    exp.collection.data.delete_by_id(str(e.get("id")))
                    print(f"[cleanup_experience] Удалён Experience: id={e.get('id')}, summary={s}")
                except Exception as ex:
                    print(f"[cleanup_experience] Ошибка при удалении: {ex}")

def test_full_experience_to_insight_cycle():
    mm = MemoryManager()
    exp = mm.memory_registry.get("Experience")
    insight = mm.memory_registry.get("Insight")
    criticlog = mm.memory_registry.get("CriticLog")
    session_id = f"fullcycle_{int(time.time())}"
    # --- Очистка старых Experience с такими же summary ---
    summary_cluster = "Интеграционный опыт для кластеризации"
    summary_error = "Ошибка: что-то пошло не так!"
    summary_success = "Успешно решено!"
    summary_rubric_error = "Случай с низким баллом"
    summary_rubric_success = "Высокий балл за выполнение"
    summary_manual = "Только ручной подъём"
    cleanup_experience(exp, [summary_cluster, summary_error, summary_success, summary_rubric_error, summary_rubric_success, summary_manual])
    # --- Дальше тест без изменений ---
    # 1. Кластеризация (5 похожих Experience)
    summary_cluster = "Интеграционный опыт для кластеризации"
    for i in range(5):
        exp.insert({
            "summary": summary_cluster,
            "source_ids": [f"src_cluster_{i}"],
            "timestamp": mm._get_rfc3339_timestamp(),
            "session_id": session_id
        })
    # 2. Ошибка (ключевое слово)
    summary_error = "Ошибка: что-то пошло не так!"
    exp.insert({
        "summary": summary_error,
        "source_ids": ["src_error"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    })
    # 3. Успех (ключевое слово)
    summary_success = "Успешно решено!"
    exp.insert({
        "summary": summary_success,
        "source_ids": ["src_success"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id
    })
    # 4. rubric_score (низкий)
    summary_rubric_error = "Случай с низким баллом"
    exp.insert({
        "summary": summary_rubric_error,
        "source_ids": ["src_rubric_error"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id,
        "rubric_score": 0.2
    })
    # 5. rubric_score (высокий)
    summary_rubric_success = "Высокий балл за выполнение"
    exp.insert({
        "summary": summary_rubric_success,
        "source_ids": ["src_rubric_success"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id,
        "rubric_score": 0.95
    })
    # 6. manual_elevate
    summary_manual = "Только ручной подъём"
    manual_id = exp.insert({
        "summary": summary_manual,
        "source_ids": ["src_manual"],
        "timestamp": mm._get_rfc3339_timestamp(),
        "session_id": session_id,
        "manual_elevate": True
    })
    # Проверяем, как реально сохранился объект
    manual_objs = exp._fetch_objects_with_id(limit=5, filters=None, return_properties=["id", "summary", "manual_elevate", "elevated", "session_id"])
    print(f"[DEBUG][manual_elevate] После insert: {[obj for obj in manual_objs if obj.get('id') == manual_id or obj.get('summary') == summary_manual]}")
    # Ждём, чтобы автоматизация сработала (обычно триггер на 5+ Experience)
    print("[TEST] Ждём автоматизации подъёма Experience → Insight...")
    time.sleep(10)
    # Запускаем автоматизацию с увеличенным batch_size
    mm.automate_experience_elevation_scenarios(batch_size=10)
    # Проверяем, что все Experience стали elevated=True
    for summary in [summary_cluster, summary_error, summary_success, summary_rubric_error, summary_rubric_success, summary_manual]:
        found = wait_for_elevated(exp, session_id, summary)
        assert found, f"Experience не найден: {summary}"
        assert all(e.get("elevated") is True for e in found), f"Experience не elevated: {summary}"
    # Проверяем, что инсайты созданы
    all_insights = insight.collection.query.fetch_objects(limit=50, return_properties=["insight", "source_ids", "timestamp"]).objects
    insights = [getattr(ins, 'properties', ins) for ins in all_insights if session_id in str(getattr(ins, 'properties', ins))]
    print(f"[TEST] Найдено инсайтов для session_id={session_id}: {len(insights)}")
    assert insights, "Insight не создан ни по одному сценарию!"
    # Проверяем, что retrieval по инсайту работает
    for summary in [summary_cluster, summary_error, summary_success, summary_rubric_error, summary_rubric_success, summary_manual]:
        results = insight.search(summary, limit=5, filter_by={"source_ids": [session_id]}, fallback_to_filter=True)
        assert any(session_id in str(r) for r in results), f"Insight не найден retrieval: {summary}"
    # Проверяем, что CriticLog содержит логи
    logs = criticlog.search("elevate_analyze", limit=20, filter_by={"session_id": session_id}, fallback_to_filter=True)
    print(f"[TEST] Логи CriticLog для session_id={session_id}: {len(logs)}")
    assert logs, "CriticLog не содержит логи автоматизации!"
    print("[TEST] Интеграционный тест полного цикла ПРОЙДЕН успешно!") 