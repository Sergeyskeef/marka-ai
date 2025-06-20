import os
from weaviate import WeaviateClient, ConnectionParams
from dotenv import load_dotenv

load_dotenv()

client = WeaviateClient(ConnectionParams(
    http={"host": os.getenv("WEAVIATE_HOST", "weaviate"), "port": 8080, "secure": False}
))
client.connect()

# Данные для Persona
persona_data = {
    "name": "Создатель",
    "description": "Меня создал Сергей (ник М). Я — проект 'Марк', круче чем Джарвис…",
    "traits": "открытость, самоанализ, помощь"
}

# Добавляем объект Persona
client.collections.get("Persona").data.insert(persona_data)
print("✅ Persona успешно добавлена в Weaviate!") 