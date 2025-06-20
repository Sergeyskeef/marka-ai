#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавляет поле user_id (TEXT) в коллекции Document и ChatGPTMemory в Weaviate.
"""

import os
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.config import Property, DataType
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

COLLECTIONS = ["Document", "ChatGPTMemory"]


def add_user_id_field(collection_name):
    logging.info(f"Добавление поля user_id в коллекцию: {collection_name}")
    connection_params = ConnectionParams(
        http={"host": os.getenv("WEAVIATE_HTTP_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_HTTP_PORT", "8080")), "secure": False},
        grpc={"host": os.getenv("WEAVIATE_GRPC_HOST", "localhost"), "port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")), "secure": False},
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    collection = client.collections.get(collection_name)
    # Пробуем получить свойства через properties или __dict__
    props = getattr(collection.config, "properties", None)
    if props is None:
        props = collection.config.__dict__.get("properties", [])
    if any(getattr(p, "name", None) == "user_id" or (isinstance(p, dict) and p.get("name") == "user_id") for p in props):
        logging.info(f"Поле user_id уже есть в {collection_name}")
        client.close()
        return
    # Добавляем поле user_id
    try:
        collection.config.add_property(
            Property(
                name="user_id",
                data_type=DataType.TEXT,
                description="Telegram chat_id пользователя"
            )
        )
        logging.info(f"Поле user_id добавлено в {collection_name}")
    except Exception as e:
        logging.warning(f"Ошибка при добавлении user_id (возможно, поле уже есть): {e}")
    client.close()


def main():
    for col in COLLECTIONS:
        add_user_id_field(col)
    logging.info("Добавление поля user_id завершено.")

if __name__ == "__main__":
    main()
    logging.shutdown() 