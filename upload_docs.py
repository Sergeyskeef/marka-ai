#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка ядра в Weaviate c дедупликацией по md5."""

import hashlib, json
from pathlib import Path
from tqdm import tqdm

from langchain.text_splitter import RecursiveCharacterTextSplitter
from utils.openai_proxy_client import embeddings
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams, ProtocolParams

# ── 1. подключение ─────────────────────────────────────────────────────────
client = WeaviateClient(
    connection_params=ConnectionParams(
        http = ProtocolParams(host="weaviate", port=8080, secure=False),
        grpc = ProtocolParams(host="weaviate", port=50051, secure=False),
    )
)
try:
    client.connect(timeout=15)              # ≥ 4.4
except TypeError:
    client.connect()                        # ≤ 4.3

# ── 2. ensure Document class ───────────────────────────────────────────────
if "Document" not in client.collections.list_all():
    client.collections.create_from_dict({
        "class": "Document",
        "vectorizer": "none",
        "vectorIndexConfig": {"distance": "cosine"},
        "properties": [
            {"name": "text",     "dataType": ["text"]},
            {"name": "filename", "dataType": ["text"]},
        ],
    })
    print("✅  Class Document created")

coll = client.collections.get("Document")

# ── 3. собрать существующие UUID ───────────────────────────────────────────
def load_existing_ids():
    """Вернёт set(uuid) — работает и на старых, и на новых версиях клиента."""
    ids = set()
    try:                                    # ≥ 4.10
        for obj in coll.iterator():
            ids.add(getattr(obj, "uuid", getattr(obj, "id", None)))
        return ids
    except Exception:
        pass

    # GraphQL fallback — работает даже на ветке 3.x
    try:
        query = (
            client.query
            .get("Document", ["_additional { id }"])
            .with_limit(2000)               # при большом объёме делаем несколько вызовов
        )
        while True:
            data = query.do()
            docs = data["data"]["Get"]["Document"]
            for d in docs:
                ids.add(d["_additional"]["id"])
            if len(docs) < 2000:
                break                       # последняя страница
            query = query.with_offset(len(ids))
    except Exception as e:
        print(f"⚠️ не удалось получить существующие id: {e}")
    return ids

existing = load_existing_ids()
print(f"🔒 уже в базе: {len(existing)}")

# ── 4. инструменты ─────────────────────────────────────────────────────────
DOCS_DIR = Path(__file__).parent / "core_docs"
splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
embedder = embeddings()

def md5(txt: str) -> str:
    return hashlib.md5(txt.encode()).hexdigest()

have_upsert = hasattr(coll.data, "upsert")
batch, total, new, skip = [], 0, 0, 0

# ── 5. загрузка документов ─────────────────────────────────────────────────
for file in sorted(DOCS_DIR.glob("*.txt")):
    try:
        body = file.read_text(encoding="cp1251")
    except Exception as e:
        print(f"⚠️ {file.name}: {e}")
        continue

    for chunk in tqdm(splitter.split_text(body), desc=file.name):
        total += 1
        uid = md5(chunk)
        if uid in existing:
            skip += 1
            continue

        vec = embedder.embed_query(chunk)
        obj = {"uuid": uid,
               "properties": {"text": chunk, "filename": file.name},
               "vector": vec}

        if have_upsert:                    # ≥ 4.6
            batch.append(obj)
            if len(batch) >= 32:
                coll.data.upsert(batch, return_exists=False)
                new += len(batch)
                batch.clear()
        else:                              # старый клиент
            try:
                coll.data.insert(**obj)
                new += 1
            except Exception as e:
                if "already exists" in str(e):
                    skip += 1
                else:
                    print(f"⚠️ insert error: {e}")

if batch:
    coll.data.upsert(batch, return_exists=False)
    new += len(batch)

print(f"📦 Всего: {total}  ➜ добавлено: {new}  (дубли: {skip})")

# ── 6. тест поиска ─────────────────────────────────────────────────────────
try:
    from langchain_weaviate import WeaviateVectorStore
    vs = WeaviateVectorStore(client=client, index_name="Document",
                             text_key="text", embedding=embedder)
    res = vs.similarity_search("Кто такой Марк?", k=1)
    print("🔍 Найдено:", json.dumps(res[0].page_content[:80], ensure_ascii=False) if res else "ничего")
except Exception as e:
    print(f"⚠️ search error: {e}")

client.close()
