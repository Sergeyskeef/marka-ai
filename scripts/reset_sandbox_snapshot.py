import weaviate
from weaviate import WeaviateClient
from weaviate.collections import Collection

def reset_sandbox_snapshot():
    # Подключение к Weaviate через WeaviateClient с указанием grpc_port
    client = WeaviateClient(
        connection_params=weaviate.connect.ConnectionParams.from_url(
            url="http://weaviate:8080",
            grpc_port=50051
        )
    )

    try:
        try:
            client.collections.delete("SandboxSnapshot")
            print("SandboxSnapshot удалён.")
        except Exception:
            print("SandboxSnapshot не найден, можно создавать заново.")

        # Создаем коллекцию с новым синтаксисом v4
        collection = client.collections.create(
            name="SandboxSnapshot",
            vectorizer_config={
                "text2vec-openai": {
                    "model": "ada",
                    "modelVersion": "002",
                    "type": "text"
                }
            }
        )

        # Добавляем свойства
        collection.config.add_property(
            name="snapshot_id",
            data_type="string",
            vectorizer_config={"text2vec-openai": {"skip": False}}
        )
        collection.config.add_property(
            name="session_id",
            data_type="string",
            vectorizer_config={"text2vec-openai": {"skip": False}}
        )
        collection.config.add_property(
            name="object_types",
            data_type="string[]",
            vectorizer_config={"text2vec-openai": {"skip": False}}
        )
        collection.config.add_property(
            name="object_states",
            data_type="text",
            vectorizer_config={"text2vec-openai": {"skip": True}}
        )
        collection.config.add_property(
            name="meta",
            data_type="text",
            vectorizer_config={"text2vec-openai": {"skip": False}}
        )
        collection.config.add_property(
            name="created_at",
            data_type="date",
            vectorizer_config={"text2vec-openai": {"skip": True}}
        )

        print("SandboxSnapshot создан с нужной схемой.")

    except Exception as e:
        print(f"Ошибка при пересоздании SandboxSnapshot: {str(e)}")

if __name__ == "__main__":
    reset_sandbox_snapshot() 