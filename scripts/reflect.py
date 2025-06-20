import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
from langchain_api.memory.memory_manager import MemoryManager
from weaviate import WeaviateClient, ConnectionParams
from langchain_api.utils.openai_proxy_client import chat_model
from weaviate.collections.classes.filters import Filter
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Инициализация памяти и клиента
memory_manager = MemoryManager()
mem_col = memory_manager.client.collections.get("Memory")
ins_col = memory_manager.client.collections.get("Insight")

# LLM-критик (можно заменить на свою модель)
critic_llm = chat_model(model="gpt-4.1-mini", temperature=0.2, max_tokens=512)

async def process_message(m):
    props = m.properties
    critique = await asyncio.to_thread(critic_llm.invoke, f"Исправь ответ:\n{props.get('message','')}")
    logging.info(f"[DEBUG] type(ins_col)={type(ins_col)}; type(ins_col.data)={type(ins_col.data)}")
    ins_col.data.insert({
        "insight": critique.content if hasattr(critique, 'content') else str(critique),
        "source_ids": [m.uuid]
    })
    mem_col.data.update(m.uuid, {"needs_reflection": False})
    logging.info(f"Обработано сообщение {m.uuid}")

async def main_async():
    try:
        filter_obj = Filter.by_property("needs_reflection").equal(True)
        result = mem_col.query.fetch_objects(
            limit=100,
            filters=filter_obj,
            return_properties=["message", "needs_reflection"]
        )
        bad = result.objects
        logging.info(f"Найдено {len(bad)} сообщений для рефлексии")
        if not bad:
            print("Скрипт завершён: нет сообщений для рефлексии.")
            return
        await asyncio.gather(*(process_message(m) for m in bad))
        print("Скрипт завершён.")
    except Exception as e:
        logging.error(f"Ошибка при поиске сообщений для рефлексии: {e}")
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main_async())
    logging.shutdown() 