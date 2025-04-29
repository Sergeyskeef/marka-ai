import os
from langchain_openai import OpenAIEmbeddings

def embeddings():
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
