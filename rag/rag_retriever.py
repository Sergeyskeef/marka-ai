# rag/rag_retriever.py

from typing import Any, Dict, List
from memory.memory_manager import MemoryManager

class MemoryRetriever:
    """
    Callable-класс для семантического извлечения истории из Weaviate.
    Принимает на вход словарь с полем 'question' и возвращает словарь {'history': [...]}
    """
    def __init__(self, memory_manager: MemoryManager, k: int = 5):
        self.memory_manager = memory_manager
        self.k = k

    def __call__(self, inputs: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        :param inputs: {"question": str}
        :return: {"history": [...]}, где список — результаты mm.query_relevant
        """
        question = inputs.get("question")
        # Если по какой-то причине вопрос не передан
        if question is None:
            return {"history": []}
        history = self.memory_manager.query_relevant(question, top_k=self.k)
        return {"history": history}

