import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging

from core.memory.memory_manager import MemoryManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

memory_manager = MemoryManager()
mem_col = memory_manager.client.collections.get("Memory")

BATCH_SIZE = 100

def main():
    offset = 0
    updated = 0
    try:
        while True:
            result = mem_col.query.fetch_objects(limit=BATCH_SIZE, offset=offset, return_properties=["needs_reflection"])
            objs = result.objects
            if not objs:
                break
            for m in objs:
                props = m.properties
                # Если поле отсутствует или None — обновляем
                if "needs_reflection" not in props or props["needs_reflection"] is None:
                    mem_col.data.update(m.uuid, {"needs_reflection": True})
                    updated += 1
                    logging.info(f"Обновлено сообщение {m.uuid}")
            offset += BATCH_SIZE
        print(f"Готово! Обновлено {updated} сообщений.")
    except Exception as e:
        logging.error(f"Ошибка при массовом обновлении needs_reflection: {e}")
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()
    logging.shutdown()
