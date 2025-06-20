import os
from weaviate import WeaviateClient, ConnectionParams

if __name__ == "__main__":
    # Параметры подключения (можно изменить при необходимости)
    http_host = os.getenv("WEAVIATE_HTTP_HOST", "weaviate")
    http_port = int(os.getenv("WEAVIATE_HTTP_PORT", "8080"))
    grpc_host = os.getenv("WEAVIATE_GRPC_HOST", "weaviate")
    grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))

    client = WeaviateClient(ConnectionParams.from_params(
        http_host=http_host,
        http_port=http_port,
        http_secure=False,
        grpc_host=grpc_host,
        grpc_port=grpc_port,
        grpc_secure=False
    ))
    client.connect()
    if client.collections.exists("Experience"):
        client.collections.delete("Experience")
        print("Класс Experience успешно удалён.")
    else:
        print("Класс Experience не найден.") 