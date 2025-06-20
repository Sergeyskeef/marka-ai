import logging
from langchain_api.memory.memory_manager import MemoryManager

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    mm = MemoryManager()
    mm._ensure_connected()
    collections = ["Memory", "Experience", "Insight", "UserFacts"]
    for col in collections:
        try:
            c = mm.client.collections.get(col)
            objs = c.query.fetch_objects(limit=1000, return_properties=["uuid"]).objects
            uuids = [obj.uuid for obj in objs]
            for uuid in uuids:
                c.data.delete(uuid=uuid)
            logging.info(f"✅ Очищена коллекция {col} ({len(uuids)} объектов удалено)")
        except Exception as e:
            logging.error(f"Ошибка при очистке {col}: {e}")
    logging.info("Все коллекции очищены.")
    logging.shutdown() 