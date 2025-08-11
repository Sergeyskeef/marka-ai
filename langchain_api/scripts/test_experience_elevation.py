import time

from core.memory.memory_manager import MemoryManager

mm = MemoryManager()
exp = mm.memory_registry.get("Experience")
insight = mm.memory_registry.get("Insight")

session_id = f"test_elevate_{int(time.time())}"
now = mm._get_rfc3339_timestamp()

# 1. Повторяемость (кластеризация)
for i in range(3):
    exp.insert({
        "summary": "Повторяющийся опыт для кластеризации",
        "source_ids": [f"src_repeat_{i}"],
        "timestamp": now,
        "session_id": session_id
    })
# 2. Ошибка (ключевые слова)
exp.insert({
    "summary": "Ошибка: что-то пошло не так!",
    "source_ids": ["src_error"],
    "timestamp": now,
    "session_id": session_id
})
# 3. Ошибка (rubric_score < 0.5)
exp.insert({
    "summary": "Случай с низким баллом",
    "source_ids": ["src_error_score"],
    "timestamp": now,
    "session_id": session_id,
    "rubric_score": 0.3
})
# 4. Успех (ключевые слова)
exp.insert({
    "summary": "Успешно решено!",
    "source_ids": ["src_success"],
    "timestamp": now,
    "session_id": session_id
})
# 5. Успех (rubric_score > 0.8)
exp.insert({
    "summary": "Высокий балл за выполнение",
    "source_ids": ["src_success_score"],
    "timestamp": now,
    "session_id": session_id,
    "rubric_score": 0.95
})
# 6. Аномалия (outlier)
exp.insert({
    "summary": "Уникальный случай, не похожий на другие 1234567890!",
    "source_ids": ["src_outlier"],
    "timestamp": now,
    "session_id": session_id
})
# 7. Ручной триггер
exp.insert({
    "summary": "Ручной подъём опыта",
    "source_ids": ["src_manual"],
    "timestamp": now,
    "session_id": session_id,
    "manual_elevate": True
})

print("Вставлено 7 Experience. Ждём автоматизации...")
# Даем время на асинхронную обработку (если есть)
time.sleep(10)

# Запускаем автоматизацию явно (на всякий случай)
mm.automate_experience_elevation_scenarios(batch_size=20)

# Проверяем результаты
all_exp = exp._fetch_objects_with_id(limit=20, filters=None, return_properties=["summary", "elevated", "session_id", "rubric_score", "manual_elevate"])
print("\n=== Experience (после автоматизации) ===")
for e in all_exp:
    if e.get("session_id") == session_id:
        print(f"id={e.get('id')}, elevated={e.get('elevated')}, summary={e.get('summary')}, rubric_score={e.get('rubric_score')}, manual_elevate={e.get('manual_elevate')}")

all_insights = insight.collection.query.fetch_objects(limit=10, return_properties=["insight", "source_ids", "timestamp"]).objects
print("\n=== Insight (созданные) ===")
for ins in all_insights:
    print(getattr(ins, 'properties', ins))
