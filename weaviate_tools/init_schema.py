# weaviate_tools/init_schema.py

import os
import httpx
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.config import Property, DataType, Configure
import logging
import sys, pathlib; sys.path.append(str(pathlib.Path(__file__).parent)); sys.path.append(str(pathlib.Path(__file__).parent.parent))
from langchain_api.utils.openai_proxy_client import get_proxy_config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Настраиваем прокси для OpenAI
proxies = get_proxy_config()
logging.info(f"Прокси для HTTP: {proxies.get('http', 'не настроен')}")
logging.info(f"Прокси для HTTPS: {proxies.get('https', 'не настроен')}")

# Инициализируем клиент
connection_params = ConnectionParams.from_params(
    http_host="weaviate",
    http_port=8080,
    http_secure=False,
    grpc_host="weaviate",
    grpc_port=50051,
    grpc_secure=False
)

client = WeaviateClient(connection_params=connection_params)
client.connect()

def create_class(name, properties, vectorizer_config=None):
    try:
        if client.collections.exists(name):
            client.collections.delete(name)
            logging.info(f"Удалён существующий класс: {name}")
        else:
            logging.info(f"Класс {name} не найден — создаём новый.")
        
        client.collections.create(
            name=name,
            properties=properties,
            vectorizer_config=vectorizer_config or Configure.Vectorizer.text2vec_openai(),
            description=f"Класс {name} для проекта МАРК"
        )
        logging.info(f"✅ Класс {name} создан.")
    except Exception as e:
        logging.error(f"Ошибка при создании класса {name}: {e}")

# Диалоговая память (STM / LTM)
create_class("Memory", [
    Property(name="sender", data_type=DataType.TEXT),
    Property(name="message", data_type=DataType.TEXT),
    Property(name="timestamp", data_type=DataType.DATE),
    Property(name="importance", data_type=DataType.NUMBER),
    Property(name="session_id", data_type=DataType.TEXT),
    Property(name="tags", data_type=DataType.TEXT_ARRAY),
    Property(name="needs_reflection", data_type=DataType.BOOL),
    Property(name="rubric_score", data_type=DataType.NUMBER),
    Property(name="rubric_summary", data_type=DataType.TEXT),
    Property(name="rubric_justification", data_type=DataType.TEXT),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Опыт (важные случаи, инсайты)
create_class("Experience", [
    Property(name="summary", data_type=DataType.TEXT),
    Property(name="source_ids", data_type=DataType.TEXT_ARRAY),
    Property(name="timestamp", data_type=DataType.DATE),
    Property(name="session_id", data_type=DataType.TEXT),
    Property(name="elevated", data_type=DataType.BOOL),
    Property(name="manual_elevate", data_type=DataType.BOOL),
    Property(name="rubric_score", data_type=DataType.NUMBER),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Документы
create_class("Document", [
    Property(name="text", data_type=DataType.TEXT),
    Property(name="filename", data_type=DataType.TEXT),
    Property(name="timestamp", data_type=DataType.DATE),
    Property(name="content_hash", data_type=DataType.TEXT),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Инсайты
create_class("Insight", [
    Property(name="insight", data_type=DataType.TEXT),
    Property(name="source_ids", data_type=DataType.TEXT_ARRAY),
    Property(name="timestamp", data_type=DataType.DATE),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Персонажи
create_class("Persona", [
    Property(name="name", data_type=DataType.TEXT),
    Property(name="description", data_type=DataType.TEXT),
    Property(name="traits", data_type=DataType.TEXT),
    Property(name="timestamp", data_type=DataType.DATE),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Факты пользователя
create_class("UserFacts", [
    Property(name="user_id", data_type=DataType.TEXT),
    Property(name="key", data_type=DataType.TEXT),
    Property(name="value", data_type=DataType.TEXT),
    Property(name="confidence", data_type=DataType.NUMBER),
    Property(name="timestamp", data_type=DataType.DATE),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Память для retrieval-блока ChatGPTMemory
create_class("ChatGPTMemory", [
    Property(name="text", data_type=DataType.TEXT),
    Property(name="timestamp", data_type=DataType.DATE),
    Property(name="session_id", data_type=DataType.TEXT),
    Property(name="content_hash", data_type=DataType.TEXT),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Логи критика (CriticLog)
create_class("CriticLog", [
    Property(name="action", data_type=DataType.TEXT),  # тип действия: анализ, подъём, ошибка, snapshot
    Property(name="details", data_type=DataType.TEXT), # подробности (json/dict в строке)
    Property(name="timestamp", data_type=DataType.DATE),
    Property(name="session_id", data_type=DataType.TEXT),
    Property(name="status", data_type=DataType.TEXT),  # success/error
    Property(name="error_message", data_type=DataType.TEXT),
    Property(name="source_ids", data_type=DataType.TEXT_ARRAY), # ссылки на объекты (Experience/Insight/Memory)
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

# Системная память (SystemMemory)
create_class("SystemMemory", [
    Property(name="type", data_type=DataType.TEXT),
    Property(name="content", data_type=DataType.TEXT),
    Property(name="filename", data_type=DataType.TEXT),
    Property(name="timestamp", data_type=DataType.DATE),
    Property(name="version", data_type=DataType.TEXT),
    Property(name="priority", data_type=DataType.NUMBER),
], vectorizer_config=Configure.Vectorizer.text2vec_openai())

logging.info("🎉 Все классы успешно созданы.")

# Закрываем соединения
client.close()
