"""
Mark Agent - основной агент на базе OpenAI SDK
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion import ChatCompletion

logger = logging.getLogger(__name__)


class MarkAgent:
    """
    Агент Марк на базе OpenAI SDK
    
    Особенности:
    - Прямое использование OpenAI API без абстракций
    - Встроенная поддержка инструментов (tools)
    - Интеграция с Graphiti памятью
    - Модель gpt-4.1-mini по умолчанию
    """
    
    def __init__(
        self, 
        client: AsyncOpenAI,
        model: str = "gpt-4.1-mini",
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = None
    ):
        """
        Инициализация агента
        
        Args:
            client: AsyncOpenAI клиент
            model: Модель для использования (по умолчанию gpt-4.1-mini)
            system_prompt: Системный промпт
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов
        """
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = []
        self.tool_functions = {}
        
        # Системный промпт по умолчанию
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        
        logger.info(f"✅ MarkAgent инициализирован с моделью {model}")
    
    def _get_default_system_prompt(self) -> str:
        """Получить системный промпт по умолчанию"""
        return """Ты - Марк, интеллектуальный AI-ассистент с долговременной памятью и способностью к самообучению.

Твои ключевые особенности:
- Ты помнишь предыдущие разговоры и учишься на них
- Ты можешь анализировать свои действия и улучшаться
- У тебя есть доступ к различным инструментам для выполнения задач
- Ты стремишься быть полезным, честным и дружелюбным

Всегда:
- Используй память для персонализации ответов
- Сохраняй важную информацию в память
- Будь проактивным в предложении помощи
- Признавай ошибки и учись на них"""
    
    def register_tool(self, tool_definition: Dict[str, Any], function: callable):
        """
        Регистрация инструмента
        
        Args:
            tool_definition: Определение инструмента в формате OpenAI
            function: Функция для выполнения
        """
        self.tools.append(tool_definition)
        tool_name = tool_definition["function"]["name"]
        self.tool_functions[tool_name] = function
        logger.info(f"🔧 Зарегистрирован инструмент: {tool_name}")
    
    async def chat(
        self,
        message: str,
        user_id: Optional[str] = None,
        chat_id: Optional[int] = None,
        context: Optional[List[Dict[str, str]]] = None,
        use_tools: bool = True
    ) -> Dict[str, Any]:
        """
        Основной метод общения с агентом
        
        Args:
            message: Сообщение пользователя
            user_id: ID пользователя
            chat_id: ID чата
            context: Дополнительный контекст (история сообщений)
            use_tools: Использовать ли инструменты
            
        Returns:
            Словарь с ответом и метаданными
        """
        try:
            # Подготавливаем сообщения
            messages = self._prepare_messages(message, context, user_id)
            
            # Параметры для API
            api_params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature
            }
            
            if self.max_tokens:
                api_params["max_tokens"] = self.max_tokens
            
            # Добавляем инструменты если нужно
            if use_tools and self.tools:
                api_params["tools"] = self.tools
                api_params["tool_choice"] = "auto"
            
            # Вызываем OpenAI API
            logger.info(f"🤖 Отправка запроса к {self.model}")
            response = await self.client.chat.completions.create(**api_params)
            
            # Обрабатываем ответ
            result = await self._process_response(response, messages)
            
            # Добавляем метаданные
            result["metadata"] = {
                "model": self.model,
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": datetime.now().isoformat(),
                "tokens_used": response.usage.total_tokens if response.usage else None
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка в chat: {str(e)}")
            return {
                "content": f"Произошла ошибка: {str(e)}",
                "error": True,
                "metadata": {"error": str(e)}
            }
    
    def _prepare_messages(
        self, 
        message: str, 
        context: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Подготовка сообщений для API"""
        messages = []
        
        # Системное сообщение
        messages.append({
            "role": "system",
            "content": self.system_prompt
        })
        
        # Добавляем контекст если есть
        if context:
            messages.extend(context)
        
        # Сообщение пользователя
        user_content = message
        if user_id:
            user_content = f"[User: {user_id}] {message}"
            
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        return messages
    
    async def _process_response(
        self, 
        response: ChatCompletion,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Обработка ответа от OpenAI API"""
        message = response.choices[0].message
        
        # Если есть вызовы инструментов
        if message.tool_calls:
            tool_results = await self._execute_tools(message.tool_calls)
            
            # Добавляем результаты инструментов в историю
            messages.append(message.model_dump())
            
            for tool_call, result in zip(message.tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
            
            # Получаем финальный ответ
            final_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            
            final_message = final_response.choices[0].message
            
            return {
                "content": final_message.content,
                "tool_calls": [
                    {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                        "result": result
                    }
                    for tc, result in zip(message.tool_calls, tool_results)
                ]
            }
        
        # Простой ответ без инструментов
        return {
            "content": message.content,
            "tool_calls": []
        }
    
    async def _execute_tools(
        self, 
        tool_calls: List[ChatCompletionMessageToolCall]
    ) -> List[Any]:
        """Выполнение вызовов инструментов"""
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            
            if tool_name not in self.tool_functions:
                logger.error(f"❌ Инструмент не найден: {tool_name}")
                results.append({
                    "error": f"Tool {tool_name} not found"
                })
                continue
            
            try:
                # Парсим аргументы
                args = json.loads(tool_call.function.arguments)
                
                # Выполняем функцию
                logger.info(f"🔧 Выполнение инструмента: {tool_name}")
                function = self.tool_functions[tool_name]
                
                # Проверяем, асинхронная ли функция
                if hasattr(function, '__call__'):
                    if hasattr(function, '__aiter__') or hasattr(function, '__await__'):
                        result = await function(**args)
                    else:
                        result = function(**args)
                else:
                    result = function(**args)
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения {tool_name}: {str(e)}")
                results.append({
                    "error": f"Error executing {tool_name}: {str(e)}"
                })
        
        return results
    
    def clear_tools(self):
        """Очистить все зарегистрированные инструменты"""
        self.tools = []
        self.tool_functions = {}
        logger.info("🧹 Все инструменты очищены")
    
    async def get_completion(
        self,
        prompt: str,
        **kwargs
    ) -> str:
        """
        Простой метод для получения завершения без контекста
        
        Args:
            prompt: Промпт для генерации
            **kwargs: Дополнительные параметры для API
            
        Returns:
            Сгенерированный текст
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens)
        )
        
        return response.choices[0].message.content