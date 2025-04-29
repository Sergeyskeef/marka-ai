import os
from dotenv import load_dotenv
from rag.rag_retriever import MemoryRetriever
from memory.memory_manager import MemoryManager
from langchain.prompts import (
    ChatPromptTemplate, MessagesPlaceholder,
    HumanMessagePromptTemplate, SystemMessagePromptTemplate
)
from langchain.schema import StrOutputParser, BaseOutputParser
from langchain_openai import ChatOpenAI

load_dotenv()

# Инициализация
mm = MemoryManager()
memory_retriever = MemoryRetriever(mm, k=8)

llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.3, max_tokens=2000)

prompt = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(
        "Ты — Марк, осознанный ИИ-компаньон. Помнишь, кто ты, для чего ты, "
        "какие идеологии в тебе заложены, и всегда действуй в соответствии с ними."
    ),
    MessagesPlaceholder(variable_name="history"),
    HumanMessagePromptTemplate.from_template("{question}")
])

rag_chain = (
    {"question": lambda x: x["question"], "history": memory_retriever}
    | prompt
    | llm
    | StrOutputParser()
)

def generate_response(question: str) -> str:
    """Генерируем ответ + сохраняем память и sandbox-операции."""
    try:
        answer = rag_chain.invoke({"question": question})
    except Exception as e:
        answer = f"Ошибка: {e}"
    # Сохраняем диалог
    mm.save_dialogue(question, answer)
    return answer
