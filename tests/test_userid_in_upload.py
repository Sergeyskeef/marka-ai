import os
import pytest
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

CHAT_ID = "310647615"

@pytest.fixture(scope="module")
def weaviate_client():
    http_host = os.getenv("WEAVIATE_HTTP_HOST", "localhost")
    http_port = int(os.getenv("WEAVIATE_HTTP_PORT", "8080"))
    grpc_host = os.getenv("WEAVIATE_GRPC_HOST", "localhost")
    grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
    connection_params = ConnectionParams(
        http={"host": http_host, "port": http_port, "secure": False},
        grpc={"host": grpc_host, "port": grpc_port, "secure": False},
    )
    client = WeaviateClient(connection_params=connection_params)
    client.connect()
    yield client
    client.close()

def test_user_id_in_document_collection(weaviate_client):
    collection = weaviate_client.collections.get("Document")
    # Получаем последние 5 объектов
    objs = collection.query.fetch_objects(limit=5).objects
    assert objs, "В коллекции Document нет объектов для проверки!"
    for obj in objs:
        props = getattr(obj, 'properties', obj)
        assert "user_id" in props, f"user_id отсутствует в объекте: {props}"
        assert props["user_id"] == CHAT_ID, f"user_id={props['user_id']} (ожидалось {CHAT_ID})"

def test_user_id_in_chatgptmemory_collection(weaviate_client):
    collection = weaviate_client.collections.get("ChatGPTMemory")
    objs = collection.query.fetch_objects(limit=5).objects
    assert objs, "В коллекции ChatGPTMemory нет объектов для проверки!"
    for obj in objs:
        props = getattr(obj, 'properties', obj)
        assert "user_id" in props, f"user_id отсутствует в объекте: {props}"
        assert props["user_id"] == CHAT_ID, f"user_id={props['user_id']} (ожидалось {CHAT_ID})" 