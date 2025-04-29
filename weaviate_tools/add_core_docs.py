import os
from langchain_community.document_loaders import TextLoader
from langchain_weaviate.vectorstores import WeaviateVectorStore
from langchain_openai import OpenAIEmbeddings
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams, ProtocolParams

# Загрузка документов с Windows-кодировкой
docs = []
for file in os.listdir("core_docs"):
    if file.endswith(".txt"):
        path = os.path.join("core_docs", file)
        loader = TextLoader(path, encoding="cp1251")
        docs.extend(loader.load())

# Подключение клиента Weaviate v4
client = WeaviateClient(
    connection_params=ConnectionParams(
        http=ProtocolParams(host="weaviate", port=8080, secure=False),
        grpc=ProtocolParams(host="weaviate", port=50051, secure=False),
    )
)
client.connect()

# Загрузка векторов через WeaviateVectorStore (v4)
vectorstore = WeaviateVectorStore(
    client=client,
    index_name="Document",
    text_key="text",
    embedding=OpenAIEmbeddings()
)

vectorstore.add_documents(docs)
print("✅ Документы успешно добавлены в Weaviate.")
client.close()
