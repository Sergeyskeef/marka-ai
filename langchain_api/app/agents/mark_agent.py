"""
Mark Agent - основной агент на базе OpenAI SDK
"""

import json
import re
import inspect
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
        # История по пользователям, чтобы не смешивать диалоги
        self.user_histories: Dict[str, List[Dict[str, str]]] = {}
        self._max_history_per_user: int = 100  # ограничение роста in-memory истории
        self.total_tokens_used = 0
        # Последняя подробная трассировка диалога для отладки
        self._last_debug: Dict[str, Any] = {}
        
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
            # Запоминаем текущего пользователя для контекста инструментов
            self._current_user_id = user_id
            # Подготавливаем сообщения
            if self.use_dynamic_prompts:
                messages = await self._prepare_messages_dynamic(message, context, user_id)
            else:
                messages = []
                messages.append({"role": "system", "content": self.system_prompt})
                if context:
                    messages.extend(context)
                messages.append({"role": "user", "content": message})
            
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
            
            # Собираем отладочную информацию перед вызовом LLM
            debug_trace: Dict[str, Any] = {
                "stage": "before_llm",
                "selected_prompt": getattr(self, "_last_prompt_name", None),
                "router_context": getattr(self, "_last_router_context", None),
                "system_prompt_preview": (messages[0].get("content", "") if messages and messages[0].get("role") == "system" else "")[:1200],
                "messages_preview": [
                    {"role": m.get("role"), "content": (m.get("content") or "")[:400]} for m in messages[-10:]
                ],
                "api_params_preview": {
                    "model": self.model,
                    "messages_len": len(messages),
                    "has_tools": bool(self.tools),
                    "tool_count": len(self.tools) if self.tools else 0,
                    "tool_names": [
                        (td.get("function", {}) or {}).get("name")
                        for td in (self.tools or [])
                        if isinstance(td, dict)
                    ] or None,
                    "temperature": self.temperature if (self.temperature is not None and float(self.temperature) != 1.0) else None,
                    "max_tokens": self.max_tokens,
                },
            }
            # Сохраняем отладочную информацию ДО вызова LLM, чтобы видеть контекст даже при таймауте
            self._last_debug = debug_trace

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

            # Пополняем отладочную информацию
            try:
                usage = response.usage.model_dump() if response.usage else None
            except Exception:
                usage = None
            first_msg = None
            try:
                first_msg_obj = response.choices[0].message
                first_msg = first_msg_obj.model_dump() if hasattr(first_msg_obj, "model_dump") else {
                    "role": getattr(first_msg_obj, "role", None),
                    "content": getattr(first_msg_obj, "content", None),
                }
            except Exception:
                first_msg = None

            debug_trace.update({
                "stage": "after_llm",
                "usage": usage,
                "first_model_message": first_msg,
                "tool_calls_count": len(getattr(response.choices[0].message, "tool_calls", []) or []),
            })
            
            # Добавляем метаданные
            result["metadata"] = {
                "model": self.model,
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": datetime.now().isoformat(),
                "tokens_used": response.usage.total_tokens if response.usage else None
            }
            
            # Обновляем историю (персонально для пользователя)
            history_key = user_id or "anonymous"
            user_hist = self.user_histories.setdefault(history_key, [])
            user_hist.append({"role": "user", "content": message})
            user_hist.append({"role": "assistant", "content": result.get("content", "")})
            # Ограничение длины истории per-user
            if len(user_hist) > self._max_history_per_user:
                # Оставляем последние N записей
                self.user_histories[history_key] = user_hist[-self._max_history_per_user:]
            # Поддерживаем и общую историю для обратной совместимости
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": result.get("content", "")})
            
            # Обновляем награду в роутере если используем динамические промпты
            if self.use_dynamic_prompts and hasattr(self, '_last_prompt_name'):
                quality = self._evaluate_response_quality(result)
                await self.prompt_router.update_reward(
                    self._last_prompt_name,
                    self._last_router_context,
                    quality
                )

            # Финальный блок отладки
            debug_trace.update({
                "final_result": {
                    "content_preview": (result.get("content") or "")[:1200],
                    "tool_calls": result.get("tool_calls"),
                    "metadata": result.get("metadata"),
                },
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": datetime.now().isoformat(),
            })
            self._last_debug = debug_trace
            
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
                    "tool_call_id": getattr(tool_call, "id", None),
                    "content": json.dumps(result, ensure_ascii=False, default=str)
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
                        "name": getattr(getattr(tc, "function", None), "name", "unknown"),
                        "arguments": getattr(getattr(tc, "function", None), "arguments", "{}"),
                        "result": result
                    }
                    for tc, result in zip(message.tool_calls, tool_results)
                ]
            }
        
        # Простой ответ без инструментов
        return {
            "content": getattr(message, "content", ""),
            "tool_calls": []
        }
    
    async def _execute_tools(
        self, 
        tool_calls: List[ChatCompletionMessageToolCallUnion]
    ) -> List[Any]:
        """Выполнение вызовов инструментов"""
        results = []
        
        for tool_call in tool_calls:
            tool_fn = getattr(tool_call, "function", None)
            tool_name = getattr(tool_fn, "name", None)
            if not tool_fn or not tool_name:
                logger.error("❌ Некорректный вызов инструмента: отсутствует function/name")
                results.append({
                    "error": "Invalid tool call: missing function/name"
                })
                continue
            
            if tool_name not in self.tool_functions:
                logger.error(f"❌ Инструмент не найден: {tool_name}")
                results.append({
                    "error": f"Tool {tool_name} not found"
                })
                continue
            
            try:
                # Парсим аргументы
                raw_args = getattr(tool_fn, "arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}
                
                # Выполняем функцию
                logger.info(f"🔧 Выполнение инструмента: {tool_name}")
                function = self.tool_functions[tool_name]
                
                # Корректно обрабатываем async/sync
                # Фильтруем неожиданные аргументы по сигнатуре функции
                try:
                    signature = inspect.signature(function)
                    allowed = set(signature.parameters.keys())
                    filtered_args = {k: v for k, v in (args or {}).items() if k in allowed}
                    dropped = set((args or {}).keys()) - allowed
                    if dropped:
                        logger.warning(f"🔎 Игнорирую неподдерживаемые аргументы для {tool_name}: {sorted(dropped)}")
                    # Инъекция owner_id/user_id в метаданные, если поддерживается
                    if 'metadata' in signature.parameters:
                        md = filtered_args.get('metadata') or {}
                        if not isinstance(md, dict):
                            md = {}
                        if getattr(self, '_current_user_id', None):
                            md.setdefault('owner_id', self._current_user_id)
                            md.setdefault('user_id', self._current_user_id)
                        # Гарантируем целочисленный timestamp, если нет
                        md.setdefault('timestamp', int(__import__('time').time()))
                        filtered_args['metadata'] = md
                except Exception:
                    filtered_args = args or {}

                if inspect.iscoroutinefunction(function):
                    result = await function(**filtered_args)
                else:
                    res = function(**filtered_args)
                    if inspect.iscoroutine(res):
                        result = await res
                    else:
                        result = res
                
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
        # Персональная длина диалога
        history_key = user_id or "anonymous"
        per_user_hist = self.user_histories.get(history_key, [])

        router_context = {
            "query": message,
            "user_id": user_id or "unknown",
            "complexity": self._estimate_complexity(message),
            "domain": self._classify_domain(message),
            "requires_memory": "помни" in message.lower() or "запомни" in message.lower(),
            "requires_tools": any(kw in message.lower() for kw in ["файл", "код", "тест", "анализ"]),
            "conversation_length": len(per_user_hist)
        }
        
        # Выбираем оптимальный промпт
        prompt_template = None
        confidence = 0.0
        try:
            if hasattr(self, "prompt_router") and self.prompt_router is not None:
                prompt_template, confidence = await self.prompt_router.select_prompt(router_context)
        except Exception as e:
            logger.warning(f"Не удалось выбрать промпт динамической системой: {e}")

        # Фолбэк: если промпт не найден — используем системный
        if prompt_template is None:
            logger.warning("Промпт не найден, использую системный промпт по умолчанию")
            optimized_context = self.system_prompt
            # Удаляем незаполненные плейсхолдеры вида {var}
            optimized_context = self._remove_unfilled_placeholders(optimized_context)
            messages = [{"role": "system", "content": optimized_context}]
            if context:
                # Нормализуем: системные блоки объединяем в один system-промпт
                extra_system_parts = []
                non_system_messages = []
                for ctx_msg in context:
                    role = ctx_msg.get("role")
                    content = ctx_msg.get("content") or ""
                    if role == "system" and content:
                        extra_system_parts.append(content)
                    else:
                        non_system_messages.append(ctx_msg)
                if extra_system_parts:
                    merged = (messages[0]["content"].rstrip() + "\n\n" + "\n\n".join(extra_system_parts)).strip()
                    # Дедупликация повторяющихся абзацев/строк
                    messages[0]["content"] = self._deduplicate_system_prompt(merged)
                messages.extend(non_system_messages)
            messages.append({"role": "user", "content": message})
            self._last_prompt_name = "default_system"
            self._last_router_context = router_context
            return messages
        
        # Подготавливаем данные для контекста
        context_data = {
            "model_name": self.model,
            "user_id": user_id or "",
            "user_query": message,
            "interaction_count": len(per_user_hist),
            "working_memory": self._get_working_memory()
        }
        
        # Строим оптимизированный контекст
        optimized_context, metrics = self.context_architect.architect_context(
            template=prompt_template,
            context_data=context_data,
            optimization_mode="balanced"
        )
        # Удаляем незаполненные плейсхолдеры вида {var}
        optimized_context = self._remove_unfilled_placeholders(optimized_context)
        
        logger.debug(f"Метрики контекста: {metrics}")
        
        # Формируем сообщения
        messages = [{"role": "system", "content": optimized_context}]
        
        # Добавляем историю
        # 1) Внешний контекст (например, RAG). Системные блоки объединяем в один
        if context:
            extra_system_parts = []
            non_system_messages = []
            for ctx_msg in context:
                role = ctx_msg.get("role")
                content = ctx_msg.get("content") or ""
                if role == "system" and content:
                    extra_system_parts.append(content)
                else:
                    non_system_messages.append(ctx_msg)
            if extra_system_parts:
                merged = (messages[0]["content"].rstrip() + "\n\n" + "\n\n".join(extra_system_parts)).strip()
                messages[0]["content"] = self._deduplicate_system_prompt(merged)
            messages.extend(non_system_messages)
        # 2) Персональная история пользователя (последние 12 сообщений)
        user_hist = per_user_hist
        if user_hist:
            messages.extend(user_hist[-12:])
        
        messages.append({"role": "user", "content": message})
        
        # Сохраняем информацию для оценки качества
        self._last_prompt_name = getattr(prompt_template, "name", "unknown")
        self._last_router_context = router_context
        
        return messages

    def _remove_unfilled_placeholders(self, text: str) -> str:
        """Удалить строки с незаполненными плейсхолдерами вида {variable}.
        Полезно, когда в шаблоне остались переменные без значений.
        """
        try:
            lines = text.splitlines()
            cleaned = []
            placeholder_re = re.compile(r"\{[^\}]+\}")
            for line in lines:
                # Если есть явный плейсхолдер — пропускаем строку
                if placeholder_re.search(line):
                    continue
                cleaned.append(line)
            # Убираем лишние пустые строки по краям и последовательные пустые строки
            out = []
            previous_blank = False
            for line in cleaned:
                is_blank = not line.strip()
                if is_blank and previous_blank:
                    continue
                out.append(line)
                previous_blank = is_blank
            return "\n".join(out).strip()
        except Exception:
            return text

    def _deduplicate_system_prompt(self, text: str) -> str:
        """Удалить повторяющиеся абзацы и строки, сохраняя порядок.
        Нормализация: тримминг, схлопывание множественных пробелов, регистрозависимо.
        """
        try:
            # Разбиваем на абзацы по пустым строкам
            paragraphs = []
            current: list[str] = []
            for line in text.splitlines():
                if line.strip() == "":
                    if current:
                        paragraphs.append("\n".join(current))
                        current = []
                else:
                    current.append(line)
            if current:
                paragraphs.append("\n".join(current))
            
            seen = set()
            unique_paragraphs = []
            for p in paragraphs:
                norm_p = " ".join(p.strip().split())
                if norm_p in seen:
                    continue
                seen.add(norm_p)
                # Дополнительно удаляем дубли строк внутри абзаца
                lines_seen = set()
                dedup_lines = []
                for ln in p.splitlines():
                    norm_ln = " ".join(ln.strip().split())
                    if norm_ln in lines_seen:
                        continue
                    lines_seen.add(norm_ln)
                    dedup_lines.append(ln)
                unique_paragraphs.append("\n".join(dedup_lines))
            
            # Схлопываем последовательные пустые строки между абзацами
            result = "\n\n".join(up.strip() for up in unique_paragraphs if up.strip())
            return result.strip()
        except Exception:
            return text
    
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
        """Подготовка сообщений (устаревшая синхронная версия). Оставлена для совместимости."""
        # Используем статический промпт для синхронного пути
        messages: List[Dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": message})
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