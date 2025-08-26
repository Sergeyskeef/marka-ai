"""
Mark Agent - основной агент на базе OpenAI SDK
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import asyncio

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCallUnion
from openai.types.chat.chat_completion import ChatCompletion

from ..prompts import (
    PromptManager, DynamicPromptRouter, ContextArchitect,
    PromptEvolution
)
from ..prompts.templates.mark_base import create_mark_base_prompt

logger = logging.getLogger(__name__)


class MarkAgent:
    """
    Агент Марк на базе OpenAI SDK
    
    Особенности:
    - Прямое использование OpenAI API без абстракций
    - Встроенная поддержка инструментов (tools)
    - Интеграция с Graphiti памятью
    - Модель gpt-5-mini по умолчанию
    - Продвинутая система управления промптами
    """
    
    def __init__(
        self, 
        client: AsyncOpenAI,
        model: str = "gpt-5-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        prompt_manager: Optional[PromptManager] = None,
        use_dynamic_prompts: bool = True
    ):
        """
        Инициализация агента
        
        Args:
            client: Клиент OpenAI
            model: Модель для использования
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов
            system_prompt: Системный промпт (если не используется динамический)
            prompt_manager: Менеджер промптов
            use_dynamic_prompts: Использовать ли динамическую систему промптов
        """
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        
        # Система промптов
        self.prompt_manager = prompt_manager
        self.use_dynamic_prompts = use_dynamic_prompts and prompt_manager is not None
        
        if self.use_dynamic_prompts:
            # Инициализируем компоненты системы промптов
            self.prompt_router = DynamicPromptRouter(prompt_manager)
            self.context_architect = ContextArchitect()
            self.prompt_evolution = PromptEvolution(prompt_manager)
            
            # Создаем и сохраняем базовый промпт если его нет
            asyncio.create_task(self._ensure_base_prompt())
        
        # Инструменты
        self.tools: List[Dict[str, Any]] = []
        self.tool_functions: Dict[str, Any] = {}
        
        # История
        self.conversation_history: List[Dict[str, str]] = []
        self.total_tokens_used = 0
        
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
            }
            # Некоторые модели (например, семейство mini) не поддерживают произвольную температуру
            # В таких случаях используем значение по умолчанию, просто не передавая параметр
            if self.temperature is not None and float(self.temperature) != 1.0:
                api_params["temperature"] = self.temperature
            
            if self.max_tokens:
                api_params["max_tokens"] = self.max_tokens
            
            # Добавляем инструменты если нужно
            if use_tools and self.tools:
                api_params["tools"] = self.tools
                api_params["tool_choice"] = "auto"
            
            # Вызываем OpenAI API
            logger.info(f"🤖 Отправка запроса к {self.model}")
            try:
                response = await self.client.chat.completions.create(**api_params)
            except Exception as e:
                err_text = str(e).lower()
                # Авто-ретрай без temperature, если модель не поддерживает переопределение
                if "temperature" in err_text and ("unsupported" in err_text or "unsupported_value" in err_text):
                    logger.warning("🔁 Повтор запроса без temperature из-за ограничений модели")
                    api_params.pop("temperature", None)
                    response = await self.client.chat.completions.create(**api_params)
                else:
                    raise
            
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
            
            # Обновляем историю
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": result["content"]})
            
            # Обновляем награду в роутере если используем динамические промпты
            if self.use_dynamic_prompts and hasattr(self, '_last_prompt_name'):
                quality = self._evaluate_response_quality(result)
                await self.prompt_router.update_reward(
                    self._last_prompt_name,
                    self._last_router_context,
                    quality
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка в chat: {str(e)}")
            return {
                "content": f"Произошла ошибка: {str(e)}",
                "error": True,
                "metadata": {"error": str(e)}
            }
    
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
        tool_calls: List[ChatCompletionMessageToolCallUnion]
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
        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ],
        }
        req_temperature = kwargs.get("temperature", self.temperature)
        if req_temperature is not None and float(req_temperature) != 1.0:
            params["temperature"] = req_temperature
        if kwargs.get("max_tokens", self.max_tokens):
            params["max_tokens"] = kwargs.get("max_tokens", self.max_tokens)

        try:
            response = await self.client.chat.completions.create(**params)
        except Exception as e:
            err_text = str(e).lower()
            if "temperature" in err_text and ("unsupported" in err_text or "unsupported_value" in err_text):
                logger.warning("🔁 Повтор get_completion без temperature из-за ограничений модели")
                params.pop("temperature", None)
                response = await self.client.chat.completions.create(**params)
            else:
                raise
        
        return response.choices[0].message.content

    async def _ensure_base_prompt(self):
        """Убедиться что базовый промпт существует"""
        try:
            base_prompt = await self.prompt_manager.get_prompt("mark_base")
            if not base_prompt:
                logger.info("Создаю базовый промпт Mark")
                base_prompt = create_mark_base_prompt()
                await self.prompt_manager.save_prompt(base_prompt)
                
                # Запускаем мониторинг эволюции
                if hasattr(self, 'prompt_evolution'):
                    await self.prompt_evolution.start_monitoring("mark_base")
        except Exception as e:
            logger.error(f"Ошибка создания базового промпта: {e}")
    
    async def _prepare_messages_dynamic(
        self,
        message: str,
        context: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Подготовка сообщений с динамическим промптом"""
        # Подготавливаем контекст для роутера
        router_context = {
            "query": message,
            "user_id": user_id or "unknown",
            "complexity": self._estimate_complexity(message),
            "domain": self._classify_domain(message),
            "requires_memory": "помни" in message.lower() or "запомни" in message.lower(),
            "requires_tools": any(kw in message.lower() for kw in ["файл", "код", "тест", "анализ"]),
            "conversation_length": len(self.conversation_history)
        }
        
        # Выбираем оптимальный промпт
        prompt_template, confidence = await self.prompt_router.select_prompt(router_context)
        logger.info(f"Выбран промпт: {prompt_template.name} (уверенность: {confidence:.2f})")
        
        # Подготавливаем данные для контекста
        context_data = {
            "model_name": self.model,
            "user_id": user_id or "",
            "user_query": message,
            "interaction_count": len(self.conversation_history),
            "working_memory": self._get_working_memory()
        }
        
        # Строим оптимизированный контекст
        optimized_context, metrics = self.context_architect.architect_context(
            template=prompt_template,
            context_data=context_data,
            optimization_mode="balanced"
        )
        
        logger.debug(f"Метрики контекста: {metrics}")
        
        # Формируем сообщения
        messages = [{"role": "system", "content": optimized_context}]
        
        # Добавляем историю
        if context:
            messages.extend(context)
        
        messages.append({"role": "user", "content": message})
        
        # Сохраняем информацию для оценки качества
        self._last_prompt_name = prompt_template.name
        self._last_router_context = router_context
        
        return messages
    
    def _estimate_complexity(self, message: str) -> float:
        """Оценка сложности запроса"""
        # Простая эвристика
        complexity = 0.3  # базовая сложность
        
        # Увеличиваем за длину
        if len(message) > 200:
            complexity += 0.2
        if len(message) > 500:
            complexity += 0.2
            
        # Увеличиваем за технические термины
        tech_terms = ["код", "функция", "класс", "тест", "анализ", "рефакторинг"]
        for term in tech_terms:
            if term in message.lower():
                complexity += 0.1
                
        return min(complexity, 1.0)
    
    def _classify_domain(self, message: str) -> str:
        """Классификация домена запроса"""
        message_lower = message.lower()
        
        if any(kw in message_lower for kw in ["код", "программ", "функц", "класс", "тест"]):
            return "technical"
        elif any(kw in message_lower for kw in ["расскаж", "объясни", "помоги понять"]):
            return "educational"
        elif any(kw in message_lower for kw in ["напиши", "создай", "придумай"]):
            return "creative"
        else:
            return "general"
    
    def _get_working_memory(self) -> str:
        """Получение текущей рабочей памяти"""
        # Берем последние 3 обмена из истории
        recent = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        
        memory_parts = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")[:200]  # Ограничиваем длину
            memory_parts.append(f"{role}: {content}")
        
        return "\n".join(memory_parts)
    
    def _prepare_messages(
        self, 
        message: str, 
        context: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Подготовка сообщений для API"""
        # Если используем динамические промпты, делегируем
        if self.use_dynamic_prompts:
            # Возвращаем синхронную обертку для обратной совместимости
            import asyncio
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self._prepare_messages_dynamic(message, context, user_id)
            )
        
        # Иначе используем статический промпт
        messages = []
        
        # Системное сообщение
        messages.append({
            "role": "system",
            "content": self.system_prompt
        })
        
        # Добавляем контекст если есть
        if context:
            messages.extend(context)
        
        # Добавляем сообщение пользователя
        messages.append({
            "role": "user", 
            "content": message
        })
        
        return messages

    def _evaluate_response_quality(self, result: Dict[str, Any]) -> float:
        """Оценка качества ответа для обновления награды"""
        # Базовая оценка
        quality = 0.7
        
        # Проверяем длину ответа
        content = result.get("content", "")
        if len(content) < 10:
            quality -= 0.3  # Слишком короткий
        elif len(content) > 2000:
            quality -= 0.1  # Возможно слишком многословный
        
        # Проверяем наличие ошибок
        if result.get("error"):
            quality = 0.1  # Минимальная оценка при ошибке
        
        # Проверяем использование инструментов
        if result.get("tool_calls"):
            quality += 0.1  # Бонус за использование инструментов
        
        # Ограничиваем диапазон
        return max(0.0, min(1.0, quality))