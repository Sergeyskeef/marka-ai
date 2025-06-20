#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка: есть ли объекты без user_id или с user_id != "310647615" в коллекциях Document и ChatGPTMemory.
"""

import os
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.query import Filter
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_ID = "310647615"
COLLECTIONS = ["Document", "ChatGPTMemory"]


def check_user_id_in_collection(collection_name):
    logging.info(f"Проверка коллекции: {collection_name}")
    connection_params = ConnectionParams(
        http={"host": os.getenv("WEAVIATE_HTTP_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_HTTP_PORT", "8080")), "secure": False},
        grpc={"host": os.getenv("WEAVIATE_GRPC_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")), "secure": False},
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    collection = client.collections.get(collection_name)
    # Проверяем объекты без user_id
    filter_no_user = Filter.by_property("user_id").equal(None)
    no_user = collection.query.fetch_objects(filters=filter_no_user, limit=20).objects
    logging.info(f"Без user_id: {len(no_user)} (пример: {getattr(no_user[0], 'properties', no_user[0]) if no_user else 'нет'})")
    # Проверяем объекты с user_id != USER_ID
    filter_wrong_user = Filter.by_property("user_id").not_equal(USER_ID)
    wrong_user = collection.query.fetch_objects(filters=filter_wrong_user, limit=20).objects
    logging.info(f"user_id != {USER_ID}: {len(wrong_user)} (пример: {getattr(wrong_user[0], 'properties', wrong_user[0]) if wrong_user else 'нет'})")
    client.close()


def main():
    for col in COLLECTIONS:
        check_user_id_in_collection(col)
    logging.info("Проверка user_id завершена.")

if __name__ == "__main__":
    main()
    logging.shutdown() 