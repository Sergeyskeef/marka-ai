#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

fail(){ echo "❌ $1"; exit 1; }

echo "🔎 Проверка HTTP API…"
curl -s http://localhost:8000/ping | grep -q '"status":"ok"' \
  || fail "API недоступно (http://localhost:8000/ping)"

echo "🔎 Проверка Weaviate…"
docker compose exec -T weaviate wget -q --spider http://localhost:8080/v1/.well-known/ready \
  || fail "Weaviate не готов (HTTP-код != 200)"

echo "🔎 Тест RAG…"
docker compose exec -T app python << 'PY' || fail "RAG-тест не прошёл"
import weaviate
from langchain_community.vectorstores import Weaviate
from langchain_openai import OpenAIEmbeddings

# Legacy v3-style client (still available in v4)
client = weaviate.Client(url="http://weaviate:8080")

vectorstore = Weaviate(
    client=client,
    index_name="Document",
    text_key="text",
    embedding=OpenAIEmbeddings()
)

res = vectorstore.similarity_search("Кто такой Марк?", k=1)
print("✅ RAG OK:", res[0].page_content[:80])

client.close()
PY

echo "✅ Все тесты пройдены."

