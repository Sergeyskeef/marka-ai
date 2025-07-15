import time
import uuid

from langchain_api.memory.memory_manager import MemoryManager

TEST_QUESTION = "Тестовый вопрос для проверки рефлексии и важно сохранить опыт"
TEST_ANSWER = "Тестовый ответ ассистента, требующий анализа"
IMPORTANT_KEYWORDS = ["важно", "ошибка", "критично", "❗", "⚠️"]

if __name__ == "__main__":
    print("[TEST] Инициализация MemoryManager...")
    mm = MemoryManager()
    session_id = str(uuid.uuid4())
    print(f"[TEST] Сохраняем диалог с session_id={session_id} и needs_reflection=True...")
    mm.save_dialogue(TEST_QUESTION, TEST_ANSWER, session_id=session_id, needs_reflection=True)
    print("[TEST] Диалог сохранён. Ожидание 10 секунд для асинхронной рефлексии...")
    time.sleep(10)

    # Проверка Memory
    print("[TEST] Проверяем наличие диалога в Memory...")
    try:
        mem_col = mm.client.collections.get("Memory")
        mem_objs = mem_col.query.fetch_objects(limit=20, return_properties=["message", "session_id"]).objects
        found_mem = False
        for obj in mem_objs:
            if obj.properties.get("session_id") == session_id:
                print(f"[SUCCESS] Найден диалог в Memory: {obj.properties.get('message')}")
                found_mem = True
        if not found_mem:
            print(f"[FAIL] Диалог для session_id={session_id} не найден в Memory.")
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке Memory: {e}")

    # Проверка Insight
    print("[TEST] Проверяем наличие инсайта в Insight...")
    try:
        ins_col = mm.client.collections.get("Insight")
        result = ins_col.query.fetch_objects(limit=20, return_properties=["source_ids", "insight"]).objects
        found_insight = False
        for obj in result:
            source_ids = obj.properties.get("source_ids", [])
            if session_id in source_ids:
                print(f"[SUCCESS] Insight найден для session_id={session_id}:\n{obj.properties.get('insight')}")
                found_insight = True
        if not found_insight:
            print(f"[FAIL] Insight для session_id={session_id} не найден.")
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке Insight: {e}")

    # Проверка Experience (если вопрос важный)
    if any(kw in TEST_QUESTION.lower() for kw in IMPORTANT_KEYWORDS):
        print("[TEST] Проверяем наличие опыта в Experience...")
        try:
            exp_col = mm.client.collections.get("Experience")
            result = exp_col.query.fetch_objects(limit=20, return_properties=["session_id", "summary"]).objects
            found_exp = False
            for obj in result:
                if obj.properties.get("session_id") == session_id:
                    print(f"[SUCCESS] Experience найден для session_id={session_id}:\n{obj.properties.get('summary')}")
                    found_exp = True
            if not found_exp:
                print(f"[FAIL] Experience для session_id={session_id} не найден.")
        except Exception as e:
            print(f"[ERROR] Ошибка при проверке Experience: {e}")
    else:
        print("[SKIP] Вопрос не содержит ключевых слов для Experience.")

    print("[TEST] Проверка завершена.")
