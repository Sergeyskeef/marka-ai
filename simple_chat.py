#!/usr/bin/env python3
"""
Упрощенная версия чата без RAG системы
"""

import logging
from typing import Any, Dict

from langchain.schema import AIMessage, HumanMessage, SystemMessage
from langchain_api.core.memory.memory_manager import memory_manager
from langchain_api.utils.openai_proxy_client import chat_model
from langchain_api.core.prompt_manager import prompt_manager
from langchain_api.core.prompt_adapter import get_prompt_adapter

logger = logging.getLogger(__name__)

async def simple_chat(question: str, chat_id: int | None = None, mode: str = "chat", user_id: str | None = None) -> Dict[str, Any]:
    """Упрощенная функция чата"""
    try:
        # Ищем информацию в памяти
        context_used = False
        memory_context = ""
        
        if question.strip():
            # Сначала ищем по полному вопросу
            search_result = await memory_manager.search_episodes(question, limit=3)
            logger.info(f"Поиск по вопросу '{question}': найдено {len(search_result.get('items', []))} элементов")
            
            # Проверяем, содержит ли найденная информация релевантные данные
            has_relevant_info = False
            if search_result.get("items"):
                for item in search_result["items"]:
                    text = item.get('text', '').lower()
                    # Проверяем, содержит ли элемент информацию о пользователе
                    if 'зовут' in text and ('пользователь' in text or 'разработчик' in text):
                        has_relevant_info = True
                        break
            
            # Если не нашли релевантную информацию, пробуем искать по ключевым словам
            if not has_relevant_info:
                # Извлекаем ключевые слова из вопроса
                keywords = []
                question_lower = question.lower()
                if "зовут" in question_lower or "имя" in question_lower:
                    keywords.append("зовут")
                if "занимаюсь" in question_lower or "работа" in question_lower:
                    keywords.append("разработчик")
                if "пользователь" in question_lower:
                    keywords.append("пользователь")
                
                logger.info(f"Ключевые слова для поиска: {keywords}")
                
                # Ищем по каждому ключевому слову
                for keyword in keywords:
                    search_result = await memory_manager.search_episodes(keyword, limit=3)
                    logger.info(f"Поиск по ключевому слову '{keyword}': найдено {len(search_result.get('items', []))} элементов")
                    if search_result.get("items"):
                        break
            
            if search_result.get("items"):
                context_used = True
                memory_context = "\n\nРелевантная информация:\n"
                for item in search_result["items"][:2]:
                    memory_context += f"- {item.get('text', '')[:150]}...\n"
                logger.info(f"Используем контекст: {memory_context[:100]}...")
            else:
                logger.info("Контекст не найден")
        
        # Формируем промпт с учетом режима
        base_prompt = prompt_manager.get_prompt(mode, memory_context)
        
        # Адаптируем промпт на основе предпочтений пользователя
        adapter = get_prompt_adapter()
        effective_user_id = user_id or (str(chat_id) if chat_id else "default_user")
        system_prompt = adapter.adapt_prompt(base_prompt, effective_user_id, mode)
        
        # Получаем ответ
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question)
        ]
        
        model = chat_model()
        response = await model.ainvoke(messages)
        answer = response.content.strip()
        
        # Сохраняем в память
        memory_added = False
        if question and answer:
            save_result = await memory_manager.add_episode(
                f"Вопрос: {question}\nОтвет: {answer}",
                {"chat_id": chat_id, "type": "chat"}
            )
            memory_added = save_result.get("success", False)
        
        return {
            "answer": answer,
            "context_used": context_used,
            "memory_added": memory_added,
            "chat_id": chat_id
        }
        
    except Exception as e:
        logger.error(f"Ошибка в simple_chat: {e}")
        return {
            "answer": f"Извините, произошла ошибка: {str(e)}",
            "context_used": False,
            "memory_added": False,
            "chat_id": chat_id
        }

def test_simple_chat():
    """Тест упрощенной функции чата"""
    import asyncio
    
    async def run_test():
        print("🧪 Тестирование упрощенного чата...")
        
        # Тест 1: Простой вопрос
        result1 = await simple_chat("Привет! Как дела?")
        print(f"Тест 1: {result1['answer'][:100]}...")
        
        # Тест 2: Вопрос с сохранением в память
        result2 = await simple_chat("Меня зовут Сергей, я разработчик")
        print(f"Тест 2: {result2['answer'][:100]}...")
        print(f"Сохранено в память: {result2['memory_added']}")
        
        # Тест 3: Поиск в памяти
        result3 = await simple_chat("Как меня зовут?")
        print(f"Тест 3: {result3['answer'][:100]}...")
        print(f"Использован контекст: {result3['context_used']}")
    
    asyncio.run(run_test())

if __name__ == "__main__":
    test_simple_chat() 