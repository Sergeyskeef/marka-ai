#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Массовое обновление user_id для всех объектов в Weaviate через REST PATCH.
Добавляет user_id = "310647615" во все объекты коллекций Document, ChatGPTMemory и других, если потребуется.
Использует 4 потока и только PATCH по user_id (без пересчёта embedding).
"""

import os
import requests
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import logging
import concurrent.futures

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_ID = "310647615"
COLLECTIONS = ["Document", "ChatGPTMemory"]
THREADS = 4

WEAVIATE_HOST = os.getenv("WEAVIATE_HTTP_HOST", "localhost")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_HTTP_PORT", "8080"))
WEAVIATE_URL = f"http://{WEAVIATE_HOST}:{WEAVIATE_PORT}"


def patch_user_id(class_name, uuid):
    url = f"{WEAVIATE_URL}/v1/objects/{class_name}/{uuid}"
    data = {"properties": {"user_id": USER_ID}}
    try:
        resp = requests.patch(url, json=data, timeout=30)
        if resp.status_code == 204:
            return True
        elif resp.status_code == 200:
            return True
        else:
            logging.error(f"PATCH {url} failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logging.error(f"PATCH {url} exception: {e}")
        return False


def update_user_id_in_collection(collection_name):
    logging.info(f"Обновление коллекции: {collection_name}")
    connection_params = ConnectionParams(
        http={"host": WEAVIATE_HOST, "port": WEAVIATE_PORT, "secure": False},
        grpc={"host": os.getenv("WEAVIATE_GRPC_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")), "secure": False},
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    collection = client.collections.get(collection_name)
    objects = collection.query.fetch_objects(limit=10000).objects
    updated = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = []
        for obj in objects:
            uuid = getattr(obj, 'uuid', None)
            props = getattr(obj, 'properties', obj)
            if props.get("user_id") == USER_ID:
                continue
            futures.append(executor.submit(patch_user_id, collection_name, uuid))
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                updated += 1
    logging.info(f"Всего обновлено в {collection_name}: {updated}")
    client.close()


def main():
    for col in COLLECTIONS:
        update_user_id_in_collection(col)
    logging.info("Массовое обновление user_id завершено.")

if __name__ == "__main__":
    main()
    logging.shutdown() 