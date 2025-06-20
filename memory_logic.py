import time

def memory_search_logic(mem_type: str, query: str, memory) -> str:
    if mem_type in ["experience", "memory", "insight", "persona", "userfacts", "chatgptmemory"]:
        search_method = getattr(memory.memory_manager.memory_registry.get(mem_type.capitalize()), "search", None)
        if search_method:
            found = search_method(query, limit=5)
            if not found:
                return f"По запросу '{query}' ничего не найдено в {mem_type}."
            text = f"Результаты поиска в {mem_type} по запросу '{query}':\n"
            for i, item in enumerate(found, 1):
                text += f"{i}. {item.get('summary', str(item))[:400]}\n"
            return text[:4000]
        else:
            return f"Тип памяти '{mem_type}' не поддерживает поиск."
    return None

def memory_save_logic(mem_type: str, data: str, memory) -> str:
    if mem_type in ["experience", "memory", "insight", "persona", "userfacts", "chatgptmemory"]:
        insert_method = getattr(memory.memory_manager.memory_registry.get(mem_type.capitalize()), "insert", None)
        if insert_method:
            obj = {"summary": data, "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ')}
            inserted_id = insert_method(obj)
            return f"✅ Объект сохранён в {mem_type} (id: {inserted_id})"
        else:
            return f"Тип памяти '{mem_type}' не поддерживает сохранение."
    return None

def memory_update_logic(mem_type: str, obj_id: str, data: dict, memory) -> str:
    if mem_type in ["experience", "memory", "insight", "userfacts", "chatgptmemory"]:
        update_method = getattr(memory.memory_manager.memory_registry.get(mem_type.capitalize()), "update", None)
        if update_method:
            ok = update_method(obj_id, data)
            if ok:
                return f"✅ Объект {obj_id} в {mem_type} обновлён."
            else:
                return f"❌ Не удалось обновить объект {obj_id} в {mem_type}."
        else:
            return f"Тип памяти '{mem_type}' не поддерживает обновление."
    return f"Тип памяти '{mem_type}' не поддерживает обновление через API."

def memory_delete_logic(mem_type: str, obj_id: str, memory) -> str:
    if mem_type in ["experience", "memory", "insight", "userfacts", "chatgptmemory"]:
        delete_method = getattr(memory.memory_manager.memory_registry.get(mem_type.capitalize()), "delete", None)
        if delete_method:
            ok = delete_method(obj_id)
            if ok:
                return f"🗑️ Объект {obj_id} из {mem_type} удалён."
            else:
                return f"❌ Не удалось удалить объект {obj_id} из {mem_type}."
        else:
            return f"Тип памяти '{mem_type}' не поддерживает удаление."
    return f"Тип памяти '{mem_type}' не поддерживает удаление через API."

def memory_analyze_logic(memory) -> str:
    report = ["\U0001F9E0 Самоанализ памяти:\n"]
    try:
        exp = memory.memory_manager.memory_registry.get("Experience")
        all_exp = exp.snapshot().get("snapshot", []) if exp else []
        summaries = [e.get("summary", "") for e in all_exp]
        dups = len(summaries) - len(set(summaries))
        report.append(f"- Experience: найдено {dups} дубликатов из {len(summaries)} записей.")
    except Exception as e:
        report.append(f"- Experience: ошибка анализа ({e})")
    report.append("\n(В будущем анализ будет глубже: поиск устаревших, неиспользуемых, неактуальных данных и оптимизация)")
    return "\n".join(report) 