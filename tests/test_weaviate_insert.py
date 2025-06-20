import time
from weaviate import WeaviateClient, ConnectionParams
import requests

# Подключение к Weaviate
client = WeaviateClient(ConnectionParams(
    http={"host": "weaviate", "port": 8080, "secure": False},
    grpc={"host": "weaviate", "port": 50051, "secure": False}
))
client.connect()

# Вставка тестового объекта в Memory
obj = {
    "sender": "user",
    "message": "Тестовое сообщение для проверки vectorizer",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "importance": 0.0,
    "session_id": "test_session"
}
obj_id = client.collections.get("Memory").data.insert(properties=obj)
print("Inserted object id:", obj_id)

# Ждём пару секунд для генерации vector
time.sleep(3)

# GraphQL-запрос для получения vector
url = "http://weaviate:8080/v1/graphql"
query = '{ Get { Memory(where: {operator: Equal, path: ["id"], valueString: "%s"}) { _additional { id vector } } } }' % obj_id
resp = requests.post(url, json={"query": query})
print("[DEBUG][Memory] GraphQL vector check:", resp.json()) 