import os
import logging
import httpx
import hashlib
from datetime import datetime
from langchain_community.document_loaders import TextLoader
from langchain_weaviate.vectorstores import WeaviateVectorStore
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from langchain_api.utils.openai_proxy_client import embeddings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/add_docs.log'),
        logging.StreamHandler()
    ]
)

# Загрузка документов с поддержкой различных кодировок
docs = []
encodings = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
docs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core_docs")

for file in os.listdir(docs_path):
    if file.endswith(".txt"):
        path = os.path.join(docs_path, file)
        for encoding in encodings:
            try:
                loader = TextLoader(path, encoding=encoding)
                loaded_docs = loader.load()
                
                # Добавляем метаданные о файле
                for doc in loaded_docs:
                    doc.metadata["filename"] = file
                    doc.metadata["content_hash"] = hashlib.md5(doc.page_content.encode()).hexdigest()
                    
                docs.extend(loaded_docs)
                logging.info(f"✅ Успешно загружен файл {file} с кодировкой {encoding}")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logging.error(f"❌ Ошибка при загрузке {file}: {e}")

logging.info(f"Загружено {len(docs)} документов")

# Настраиваем прокси для OpenAI
proxies = get_proxy_config()
logging.info(f"Прокси для HTTP: {proxies.get('http', 'не настроен')}")
logging.info(f"Прокси для HTTPS: {proxies.get('https', 'не настроен')}")

# Подключение клиента Weaviate v4
client = WeaviateClient(
    connection_params=ConnectionParams.from_params(
        http_host="localhost",
        http_port=8080,
        http_secure=False,
        grpc_host="localhost",
        grpc_port=50051,
        grpc_secure=False
    )
)
client.connect()

# Загрузка векторов через WeaviateVectorStore с прокси-эмбеддингами
embeddings_model = embeddings

try:
    # Добавляем документы только в коллекцию Document
    if client.collections.exists("Document"):
        document_collection = client.collections.get("Document")
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        for doc in docs:
            prop = {
                "text": doc.page_content,
                "filename": doc.metadata.get("filename", ""),
                "timestamp": timestamp,
                "content_hash": doc.metadata.get("content_hash", "")
            }
            
            doc_uuid = doc.metadata.get("content_hash", hashlib.md5(doc.page_content.encode()).hexdigest())
            document_collection.data.insert(properties=prop, uuid=doc_uuid)
            logging.info(f"✅ Документ добавлен в Document: {doc.metadata.get('filename')}")
        
        logging.info("✅ Все документы успешно добавлены в коллекцию Document")
    else:
        logging.error("❌ Коллекция Document не существует, запустите сначала init_schema.py")
    
    logging.info("✅ Документы успешно добавлены в Weaviate.")
except Exception as e:
    logging.error(f"❌ Ошибка при добавлении документов: {e}")
finally:
    client.close()
