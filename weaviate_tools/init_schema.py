#!/usr/bin/env python3
import os
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.collections.classes.config import Property, DataType, Vectorizers, VectorizerConfigCreate

def main():
    connection_params = ConnectionParams.from_params(
        http_host=os.getenv("WEAVIATE_HTTP_HOST", "weaviate"),
        http_port=int(os.getenv("WEAVIATE_HTTP_PORT", "8080")),
        http_secure=False,
        grpc_host=os.getenv("WEAVIATE_GRPC_HOST", "weaviate"),
        grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
        grpc_secure=False,
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()

    # Удаляем старые классы, если они есть
    for cls in ("Memory", "Experience", "Reflection", "Insight", "Core"):
        try:
            if cls in client.collections.list_all():
                client.collections.delete(cls)
        except Exception:
            pass

    # Создаем новые классы
    collections = {
        "Memory": [
            Property(name="speaker", data_type=DataType.TEXT),
            Property(name="text", data_type=DataType.TEXT),
            Property(name="timestamp", data_type=DataType.DATE),
            Property(name="importance", data_type=DataType.NUMBER),
            Property(name="tags", data_type=DataType.STRING_ARRAY),
        ],
        "Experience": [
            Property(name="summary", data_type=DataType.TEXT),
            Property(name="sourceIds", data_type=DataType.STRING_ARRAY),
            Property(name="createdAt", data_type=DataType.DATE),
        ],
        "Reflection": [
            Property(name="thought", data_type=DataType.TEXT),
            Property(name="createdAt", data_type=DataType.DATE),
        ],
        "Insight": [
            Property(name="insight", data_type=DataType.TEXT),
            Property(name="relatedExperiences", data_type=DataType.STRING_ARRAY),
            Property(name="createdAt", data_type=DataType.DATE),
        ],
        "Core": [
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="createdAt", data_type=DataType.DATE),
            Property(name="tags", data_type=DataType.STRING_ARRAY),
        ],
    }

    for name, props in collections.items():
        client.collections.create(
            name=name,
            properties=props,
            vectorizer_config=VectorizerConfigCreate(vectorizer=Vectorizers.TEXT2VEC_OPENAI)
        )

    print("✔️ Weaviate schema for Memory, Experience, Reflection, Insight, Core is up-to-date.")

if __name__ == "__main__":
    main()
