import weaviate

client = weaviate.Client("http://localhost:8080")  # Замените на свой адрес, если нужно

# 1. Удаляем только SandboxSnapshot (остальные коллекции не трогаем!)
if client.schema.exists("SandboxSnapshot"):
    client.schema.delete_class("SandboxSnapshot")
    print("SandboxSnapshot удалён.")
else:
    print("SandboxSnapshot не найден, можно создавать заново.")

# 2. Создаём новую коллекцию SandboxSnapshot с нужной схемой
sandbox_snapshot_schema = {
    "class": "SandboxSnapshot",
    "description": "Снапшоты памяти для отката/восстановления (можно очищать)",
    "vectorizer": "text2vec-openai",
    "properties": [
        {
            "name": "snapshot_id",
            "dataType": ["text"],
            "indexFilterable": True,
            "indexSearchable": True,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        },
        {
            "name": "timestamp",
            "dataType": ["date"],
            "indexFilterable": True,
            "indexSearchable": False,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        },
        {
            "name": "session_id",
            "dataType": ["text"],
            "indexFilterable": True,
            "indexSearchable": True,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        },
        {
            "name": "object_refs",
            "dataType": ["text[]"],
            "indexFilterable": False,
            "indexSearchable": False,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        },
        {
            "name": "object_states",
            "dataType": ["text"],
            "indexFilterable": False,
            "indexSearchable": False,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        },
        {
            "name": "snapshot_type",
            "dataType": ["text"],
            "indexFilterable": True,
            "indexSearchable": False,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        },
        {
            "name": "meta",
            "dataType": ["text"],
            "indexFilterable": False,
            "indexSearchable": False,
            "moduleConfig": {"text2vec-openai": {"skip": True, "vectorizePropertyName": False}}
        }
    ]
}

client.schema.create_class(sandbox_snapshot_schema)
print("SandboxSnapshot создан с нужной схемой.") 