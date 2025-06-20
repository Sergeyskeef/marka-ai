#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка ядра в Weaviate c дедупликацией по md5."""

import os
import glob
import logging
import hashlib
import httpx
from datetime import datetime
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.config import Property, DataType, Configure
from langchain_api.utils.openai_proxy_client import embeddings
from weaviate.collections.classes.filters import Filter
import re
import sys
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/upload.log'),
        logging.StreamHandler()
    ]
)

def get_document_md5(content):
    """Создает MD5-хеш из содержимого документа."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def document_exists(collection, content_hash):
    """Проверяет, существует ли документ с таким же хешем в коллекции."""
    try:
        # Для weaviate-client 4.14.1 используем filters=Filter.by_property(...).equal(...)
        filter_obj = Filter.by_property("content_hash").equal(content_hash)
        result = collection.query.fetch_objects(filters=filter_obj, limit=1)
        return len(result.objects) > 0
    except Exception as e:
        logging.error(f"Ошибка при проверке дубликатов: {e}")
        return False

def get_rfc3339_timestamp():
    """Возвращает текущую дату в формате RFC3339 без дробной части секунд."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def is_garbage_chunk(chunk):
    """
    Фильтрует мусорные чанки:
    - слишком короткие (< min_chunk_size // 2)
    - содержат мало букв
    - состоят в основном из спецсимволов
    - пустые или только пробелы
    """
    if not chunk or len(chunk.strip()) < 50:
        return True
    # Меньше 30% букв
    letters = sum(c.isalpha() for c in chunk)
    if letters / max(1, len(chunk)) < 0.3:
        return True
    # Много спецсимволов
    if sum(c in '\\|/[]{}<>@#$%^&*_~' for c in chunk) / max(1, len(chunk)) > 0.5:
        return True
    return False

def split_into_chunks_with_overlap(text, max_chunk_size=800, min_chunk_size=500, overlap_size=100):
    """
    Делит текст на чанки с overlap, не разрывая предложения.
    """
    raw_chunks = [abz.strip() for abz in text.split('\n\n') if abz.strip()]
    chunks = []
    for abz in raw_chunks:
        if len(abz) <= max_chunk_size:
            chunks.append(abz)
        else:
            sentences = re.split(r'(?<=[.!?])\s+', abz)
            buf = ''
            for sent in sentences:
                if len(buf) + len(sent) + 1 <= max_chunk_size:
                    buf += (' ' if buf else '') + sent
                else:
                    if buf:
                        chunks.append(buf.strip())
                    buf = sent
            if buf:
                chunks.append(buf.strip())
    # Объединяем мелкие чанки
    merged = []
    buf = ''
    for ch in chunks:
        if len(ch) < min_chunk_size:
            buf += (' ' if buf else '') + ch
            if len(buf) >= min_chunk_size:
                merged.append(buf.strip())
                buf = ''
        else:
            if buf:
                merged.append(buf.strip())
                buf = ''
            merged.append(ch)
    if buf:
        merged.append(buf.strip())
    merged = [c for c in merged if len(c) >= min_chunk_size // 2]
    # Overlap
    final_chunks = []
    for i, chunk in enumerate(merged):
        if i == 0:
            final_chunks.append(chunk)
        else:
            prev = final_chunks[-1]
            overlap = prev[-overlap_size:]
            # Не разрывать предложение: ищем границу
            match = re.search(r'([.!?])[^.!?]*$', overlap)
            if match:
                start = overlap.find(match.group(1)) + 1
                overlap = overlap[start:]
            chunk_with_overlap = (overlap + ' ' + chunk).strip()
            final_chunks.append(chunk_with_overlap)
    # Фильтруем мусор
    filtered = [c for c in final_chunks if not is_garbage_chunk(c)]
    return filtered

def upload_docs():
    """Загружает документы в Weaviate."""
    # Получаем HTTP клиент БЕЗ прокси для Weaviate
    http_client = httpx.Client(timeout=120.0)
    
    if http_client:
        logging.info("✅ Используем HTTP клиент с настроенным прокси для Weaviate")
    else:
        logging.warning("⚠️ Прокси не настроены, используем прямое подключение к Weaviate")
    
    # Настраиваем подключение к Weaviate
    connection_params = ConnectionParams(
        http={"host": os.getenv("WEAVIATE_HTTP_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_HTTP_PORT", "8080")), "secure": False},
        grpc={"host": os.getenv("WEAVIATE_GRPC_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")), "secure": False},
        # Передаем HTTP клиент напрямую в ConnectionParams
        http_client=http_client
    )
    
    client = WeaviateClient(connection_params=connection_params)
    client.connect()

    # Создаем класс Document, если его нет
    if not client.collections.exists("Document"):
        logging.info("Создаем коллекцию Document...")
        
        # Настраиваем векторайзер OpenAI с прокси
        vectorizer_config = Configure.Vectorizer.text2vec_openai()
        
        # Если есть прокси, добавляем дополнительные настройки для векторизации
        if http_client:
            # В Weaviate 4.x настройка прокси для векторайзера не требуется,
            # так как используется переданный http_client
            logging.info("Используем текущий HTTP клиент для векторизации")
        
        client.collections.create(
            name="Document",
            vectorizer_config=vectorizer_config,
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="filename", data_type=DataType.TEXT),
                Property(name="timestamp", data_type=DataType.DATE),
                Property(name="content_hash", data_type=DataType.TEXT)
            ]
        )
        logging.info("✅ Создан класс Document")
    
    # Получаем коллекцию Document
    collection = client.collections.get("Document")

    # Статистика загрузки
    stats = {"processed": 0, "uploaded": 0, "duplicates": 0, "errors": 0}

    # Загружаем документы
    docs_path = os.path.join(os.path.dirname(__file__), "core_docs")
    encodings = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
    doc_files = glob.glob(os.path.join(docs_path, "*.txt"))
    if not doc_files:
        logging.warning(f"Нет файлов для загрузки в {docs_path}")
        return
    if TQDM_AVAILABLE:
        doc_iter = tqdm(doc_files, desc="Документы")
    else:
        doc_iter = doc_files
    for doc_path in doc_iter:
        stats["processed"] += 1
        for encoding in encodings:
            try:
                with open(doc_path, "r", encoding=encoding) as f:
                    content = f.read()
                # Смысловая сегментация с overlap и фильтрацией
                chunks = split_into_chunks_with_overlap(content)
                logging.info(f"Документ {doc_path}: {len(chunks)} чанков после фильтрации, размеры: {[len(c) for c in chunks]}")
                uploaded_chunks = 0
                skipped_garbage = 0
                chunk_iter = tqdm(enumerate(chunks), total=len(chunks), desc=os.path.basename(doc_path), leave=False) if TQDM_AVAILABLE else enumerate(chunks)
                for idx, chunk in chunk_iter:
                    if is_garbage_chunk(chunk):
                        skipped_garbage += 1
                        continue
                    content_hash = get_document_md5(chunk)
                    if document_exists(collection, content_hash):
                        stats["duplicates"] += 1
                        continue
                    try:
                        response = embeddings.embed_documents([chunk])
                        emb = response[0]
                        timestamp = get_rfc3339_timestamp()
                        doc_data = {
                            "text": chunk,
                            "filename": os.path.basename(doc_path),
                            "timestamp": timestamp,
                            "content_hash": content_hash,
                            "user_id": "310647615"
                        }
                        collection.data.insert(properties=doc_data, vector=emb)
                        uploaded_chunks += 1
                        logging.info(f"Загружен чанк {idx+1}/{len(chunks)} файла {os.path.basename(doc_path)}")
                    except Exception as e:
                        logging.error(f"Ошибка при загрузке чанка {idx+1} файла {doc_path}: {e}")
                        stats["errors"] += 1
                logging.info(f"✅ Загружено чанков: {uploaded_chunks} из {len(chunks)} (файл: {doc_path}, кодировка: {encoding}, пропущено мусора: {skipped_garbage})")
                stats["uploaded"] += uploaded_chunks
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logging.error(f"❌ Ошибка при загрузке {doc_path}: {e}")
                stats["errors"] += 1
                break
    print(f"loaded: {stats['uploaded']}, skipped: {stats['duplicates']} duplicates, garbage: {skipped_garbage}")

    # Закрываем соединение
    if http_client:
        http_client.close()
    client.close()

def clear_document_collection():
    """
    Полностью очищает коллекцию Document в Weaviate.
    """
    http_client = httpx.Client(timeout=120.0)
    connection_params = ConnectionParams(
        http={"host": os.getenv("WEAVIATE_HTTP_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_HTTP_PORT", "8080")), "secure": False},
        grpc={"host": os.getenv("WEAVIATE_GRPC_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051"),), "secure": False},
        http_client=http_client
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    if client.collections.exists("Document"):
        collection = client.collections.get("Document")
        # Получаем все объекты (можно батчами)
        objects = collection.query.fetch_objects(limit=10000)
        ids = [obj.uuid for obj in objects.objects]
        for uuid in ids:
            try:
                collection.data.delete_by_id(uuid)
            except Exception as e:
                logging.error(f"Ошибка при удалении объекта {uuid}: {e}")
        logging.info(f"✅ Очищено {len(ids)} объектов из коллекции Document")
    client.close()
    if http_client:
        http_client.close()

if __name__ == "__main__":
    upload_docs()
