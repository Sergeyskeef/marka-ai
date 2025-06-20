#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка большой памяти в Weaviate (Chatgptmemory) с батчами, overlap и фильтрацией мусора."""

import os
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

BATCH_SIZE = 50
FILENAME = os.path.abspath(os.path.join(os.path.dirname(__file__), 'docs/Вся память.txt'))
COLLECTION_NAME = 'ChatGPTMemory'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/upload_chatgptmemory.log'),
        logging.StreamHandler()
    ]
)

def get_md5(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_rfc3339_timestamp():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def is_garbage_chunk(chunk):
    if not chunk or len(chunk.strip()) < 50:
        return True
    letters = sum(c.isalpha() for c in chunk)
    if letters / max(1, len(chunk)) < 0.3:
        return True
    if sum(c in '\\|/[]{}<>@#$%^&*_~' for c in chunk) / max(1, len(chunk)) > 0.5:
        return True
    return False

def split_into_chunks_with_overlap(text, max_chunk_size=800, min_chunk_size=500, overlap_size=100):
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
    final_chunks = []
    for i, chunk in enumerate(merged):
        if i == 0:
            final_chunks.append(chunk)
        else:
            prev = final_chunks[-1]
            overlap = prev[-overlap_size:]
            match = re.search(r'([.!?])[^.!?]*$', overlap)
            if match:
                start = overlap.find(match.group(1)) + 1
                overlap = overlap[start:]
            chunk_with_overlap = (overlap + ' ' + chunk).strip()
            final_chunks.append(chunk_with_overlap)
    filtered = [c for c in final_chunks if not is_garbage_chunk(c)]
    return filtered

def document_exists(collection, content_hash):
    try:
        filter_obj = Filter.by_property("content_hash").equal(content_hash)
        result = collection.query.fetch_objects(filters=filter_obj, limit=1)
        return len(result.objects) > 0
    except Exception as e:
        logging.error(f"Ошибка при проверке дубликатов: {e}")
        return False

def upload_chatgptmemory():
    http_client = httpx.Client(timeout=120.0)
    connection_params = ConnectionParams(
        http={"host": os.getenv("WEAVIATE_HTTP_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_HTTP_PORT", "8080")), "secure": False},
        grpc={"host": os.getenv("WEAVIATE_GRPC_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")), "secure": False},
        http_client=http_client
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    if not client.collections.exists(COLLECTION_NAME):
        logging.info(f"Создаю коллекцию {COLLECTION_NAME}...")
        vectorizer_config = Configure.Vectorizer.text2vec_openai()
        client.collections.create(
            name=COLLECTION_NAME,
            vectorizer_config=vectorizer_config,
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="filename", data_type=DataType.TEXT),
                Property(name="timestamp", data_type=DataType.DATE),
                Property(name="content_hash", data_type=DataType.TEXT),
                Property(name="chunk_id", data_type=DataType.INT),
                Property(name="session_id", data_type=DataType.TEXT)
            ]
        )
        logging.info(f"✅ Создан класс {COLLECTION_NAME}")
    collection = client.collections.get(COLLECTION_NAME)
    stats = {"processed": 0, "uploaded": 0, "duplicates": 0, "errors": 0, "garbage": 0}
    if not os.path.exists(FILENAME):
        logging.error(f"Файл не найден: {FILENAME}")
        return
    logging.info(f"Используется файл памяти: {FILENAME}")
    with open(FILENAME, 'r', encoding='utf-8') as f:
        text = f.read()
    chunks = split_into_chunks_with_overlap(text)
    logging.info(f"Файл {FILENAME}: {len(chunks)} чанков после фильтрации")
    batch = []
    chunk_iter = tqdm(enumerate(chunks), total=len(chunks), desc="Чанки", leave=True) if TQDM_AVAILABLE else enumerate(chunks)
    for idx, chunk in chunk_iter:
        stats["processed"] += 1
        content_hash = get_md5(chunk)
        if document_exists(collection, content_hash):
            stats["duplicates"] += 1
            continue
        try:
            emb = embeddings.embed_documents([chunk])[0]
            doc_data = {
                "text": chunk,
                "filename": os.path.basename(FILENAME),
                "timestamp": get_rfc3339_timestamp(),
                "content_hash": content_hash,
                "chunk_id": idx,
                "session_id": "default",
                "user_id": "310647615"
            }
            batch.append((doc_data, emb))
            if len(batch) >= BATCH_SIZE:
                for doc, vec in batch:
                    try:
                        collection.data.insert(properties=doc, vector=vec)
                        stats["uploaded"] += 1
                    except Exception as e:
                        logging.error(f"Ошибка при загрузке чанка {doc['chunk_id']}: {e}")
                        stats["errors"] += 1
                batch = []
        except Exception as e:
            logging.error(f"Ошибка при обработке чанка {idx}: {e}")
            stats["errors"] += 1
    # Загрузить остатки
    for doc, vec in batch:
        try:
            collection.data.insert(properties=doc, vector=vec)
            stats["uploaded"] += 1
        except Exception as e:
            logging.error(f"Ошибка при загрузке чанка {doc['chunk_id']}: {e}")
            stats["errors"] += 1
    logging.info(f"Итог: обработано {stats['processed']}, загружено {stats['uploaded']}, дубликатов {stats['duplicates']}, ошибок {stats['errors']}")
    print(f"loaded: {stats['uploaded']}, skipped: {stats['duplicates']} duplicates, errors: {stats['errors']}")
    if http_client:
        http_client.close()
    client.close()

if __name__ == "__main__":
    upload_chatgptmemory() 