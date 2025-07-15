import time

from langchain_api.memory.memory_manager import MemoryManager

mm = MemoryManager()
exp = mm.memory_registry.get("Experience")
insight = mm.memory_registry.get("Insight")

session_id = f"test_manual_elevate_{int(time.time())}"
now = mm._get_rfc3339_timestamp()

# Вставляем только один Experience с ручным триггером
exp.insert({
    "summary": "Уникальный ручной опыт для проверки manual_elevate",
    "source_ids": ["src_manual_unique"],
    "timestamp": now,
    "session_id": session_id,
    "manual_elevate": True
})

print("Вставлен 1 Experience с manual_elevate=True. Ждём автоматизации...")
time.sleep(10)

# Запускаем автоматизацию явно
mm.automate_experience_elevation_scenarios(batch_size=5)

# Проверяем результат
all_exp = exp._fetch_objects_with_id(limit=5, filters=None, return_properties=["summary", "elevated", "session_id", "manual_elevate"])
print("\n=== Experience (после автоматизации) ===")
for e in all_exp:
    if e.get("session_id") == session_id:
        print(f"id={e.get('id')}, elevated={e.get('elevated')}, summary={e.get('summary')}, manual_elevate={e.get('manual_elevate')}")
        assert e.get("elevated") is True, "manual_elevate Experience не был поднят!"
print("\nПроверка manual_elevate: OK!")
