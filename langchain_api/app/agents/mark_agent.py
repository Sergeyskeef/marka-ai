"""
Mark Agent - основной агент на базе OpenAI SDK
"""

import copy
import json
import re
import inspect
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import asyncio

from openai import AsyncOpenAI
from redis.asyncio import Redis
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCallUnion
from openai.types.chat.chat_completion import ChatCompletion

from ..prompts import (
    PromptManager, DynamicPromptRouter, ContextArchitect,
    PromptEvolution
)
from ..prompts.templates.mark_base import create_mark_base_prompt
from ..config import settings
from app.memory.fractal_graph import fractal_graph
from app.agents.fractal.reap import detect_incident, mine_skill
from core.memory.memory_manager import memory_manager

logger = logging.getLogger(__name__)


@dataclass
class RequestState:
    """Состояние одного запроса к агенту."""

    user_id: Optional[str]
    llm_calls: int = 0
    llm_limit: int = 0
    tool_calls: int = 0
    tool_limit: int = 0
    rounds: int = 0
    progress_checkpoint_calls: int = 0
    budget_checkpoint_tool_calls: int = 0
    progress_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    progress: Dict[str, Any] = field(default_factory=dict)
    debug_trace: Dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> Dict[str, Any]:
        """Создать копию состояния для отладки."""
        return asdict(self)


class MarkAgent:
    """
    Агент Марк на базе OpenAI SDK
    
    Особенности:
    - Прямое использование OpenAI API без абстракций
    - Встроенная поддержка инструментов (tools)
    - Интеграция с Graphiti памятью
    - Модель gpt-4.1-mini по умолчанию
    - Продвинутая система управления промптами
    """
    
    def __init__(
        self, 
        client: AsyncOpenAI,
        model: str = "gpt-4.1-mini",
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
        base_prompt = system_prompt or self._get_default_system_prompt()
        if getattr(settings, 'USE_COMPACT_SYSTEM_PROMPT', False):
            base_prompt = self._compact_prompt(base_prompt)
        self.system_prompt = base_prompt
        
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
        self._history_max_total: int = getattr(settings, "HISTORY_MAX_MESSAGES", 100)
        self._verbosity_mode: str = getattr(settings, "VERBOSITY_MODE", "auto")
        self._redis: Optional[Redis] = None
        self.total_tokens_used = 0
        # Последняя подробная трассировка диалога для отладки
        self._last_debug: Dict[str, Any] = {}

        logger.info(f"✅ MarkAgent инициализирован с моделью {model}")

    def _update_debug_snapshot(self, state: RequestState):
        """Обновить последний снимок отладочной информации."""
        try:
            debug_copy = copy.deepcopy(state.debug_trace) if state.debug_trace else {}
            debug_copy["state"] = {
                "user_id": state.user_id,
                "llm_calls": state.llm_calls,
                "llm_limit": state.llm_limit,
                "tool_calls": state.tool_calls,
                "tool_limit": state.tool_limit,
                "rounds": state.rounds,
                "progress": copy.deepcopy(state.progress),
                "progress_snapshots": copy.deepcopy(state.progress_snapshots),
            }
            self._last_debug = debug_copy
        except Exception:
            self._last_debug = {
                "state": {
                    "user_id": state.user_id,
                    "llm_calls": state.llm_calls,
                    "tool_calls": state.tool_calls,
                    "rounds": state.rounds,
                }
            }

    async def _get_redis(self) -> Optional[Redis]:
        """Лениво инициализировать Redis для хранения истории диалогов."""
        try:
            if self._redis is None:
                # Используем ту же конфигурацию, что и приложение
                self._redis = Redis.from_url(settings.redis_url_with_auth)
                await self._redis.ping()
            return self._redis
        except Exception:
            return None

    async def _load_user_history_from_store(self, history_key: str, max_items: int = 24) -> List[Dict[str, str]]:
        """Загрузить последние сообщения пользователя из Redis (если доступен)."""
        try:
            r = await self._get_redis()
            if not r:
                return []
            key = f"user_history:{history_key}"
            # Берем последние элементы
            raw_items = await r.lrange(key, -max_items, -1)
            history: List[Dict[str, str]] = []
            for bi in raw_items:
                try:
                    item = json.loads(bi)
                    if isinstance(item, dict) and item.get("role") and item.get("content") is not None:
                        history.append({"role": item["role"], "content": item["content"]})
                except Exception:
                    continue
            return history
        except Exception:
            return []

    async def _persist_user_history_to_store(self, history_key: str, new_items: List[Dict[str, str]]):
        """Сохранить новые элементы истории пользователя в Redis и обрезать до лимита."""
        try:
            if not new_items:
                return
            r = await self._get_redis()
            if not r:
                return
            key = f"user_history:{history_key}"
            # Добавляем элементы
            payloads = [json.dumps(it, ensure_ascii=False) for it in new_items]
            if payloads:
                await r.rpush(key, *payloads)
                await r.ltrim(key, -self._history_max_total, -1)
        except Exception:
            return
    
    def _get_default_system_prompt(self) -> str:
        """Получить системный промпт по умолчанию"""
        return (
            "Ты - Марк, интеллектуальный AI-ассистент с долговременной памятью и способностью к самообучению.\n\n"
            "Твои ключевые особенности:\n"
            "- Ты помнишь предыдущие разговоры и учишься на них\n"
            "- Ты можешь анализировать свои действия и улучшаться\n"
            "- У тебя есть доступ к различным инструментам для выполнения задач\n"
            "- Ты стремишься быть полезным, честным и дружелюбным\n\n"
            "Всегда:\n"
            "- Используй память для персонализации ответов\n"
            "- Сохраняй важную информацию в память\n"
            "- Будь проактивным в предложении помощи\n"
            "- Признавай ошибки и учись на них\n"
            "- Уважай бюджет инструментов и лимиты LLM: заверши в рамках текущего лимита, если он близок к исчерпанию, дай краткий полезный ответ и остановись, предложив продолжение при необходимости\n"
            "- Сохраняй промежуточные отчёты прогресса и бюджетные чекпоинты в память; при запросе пользователя 'продолжай' возобновляй с места остановки\n"
            "- Для диагностики используй логи инструментов (инструмент get_recent_tool_logs) и, при необходимости, сообщай пользователю, каких инструментов или настроек не хватает\n"
                "- Для статуса изменений в проекте при необходимости используй инструмент generate_change_report (кратко и без лишних деталей)\n\n"
                "Правдивость про инструменты (обязательно):\n"
                "- Если в текущем ответе инструменты НЕ вызывались — явно укажи 'инструменты не вызывались'; не создавай впечатление, что они использовались.\n"
                "- Если опираешься на ранее сохранённую информацию — обозначь, что это контекст из памяти, а не результат текущих вызовов.\n"
                "- Если пользователь явно просит вызвать инструменты (например: 'вызови N инструментов', 'запусти X') — делай это по делу; если инструмент не нужен или недоступен — кратко объясни почему.\n\n"
                "Уточнения и продолжение:\n"
                "- Не спрашивай 'продолжать?' без веской причины. Спрашивай только при неоднозначности цели пользователя или когда продолжение приведёт к существенным затратам.\n"
                "- Если бюджет на исходе — подведи краткий итог, сохрани прогресс и предложи продолжение по запросу пользователя."
        )
    
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
        use_tools: bool = True,
        override_max_tokens: Optional[int] = None,
        override_llm_calls_limit: Optional[int] = None,
        override_tool_calls_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Основной метод общения с агентом
        
        Args:
            message: Сообщение пользователя
            user_id: ID пользователя
            chat_id: ID чата
            context: Дополнительный контекст (история сообщений)
            use_tools: Использовать ли инструменты
            override_max_tokens: Явно ограничить токены генерации для этого запроса
            
        Returns:
            Словарь с ответом и метаданными
        """
        try:
            # Инициализация лимитов и счётчиков для текущего запроса
            t_func_start = __import__('time').time()
            llm_limit = int(
                (override_llm_calls_limit if override_llm_calls_limit is not None else getattr(settings, "LLM_CALLS_PER_REQUEST_LIMIT", 10)) or 10
            )
            tool_limit = int(
                (override_tool_calls_limit if override_tool_calls_limit is not None else getattr(settings, "TOOL_CALLS_PER_REQUEST_LIMIT", 6)) or 6
            )
            progress_checkpoint_calls = int(getattr(settings, "PROGRESS_CHECKPOINT_CALLS", 2) or 2)
            budget_checkpoint_tool_calls = int(getattr(settings, "BUDGET_CHECKPOINT_TOOL_CALLS", 2) or 2)
            state = RequestState(
                user_id=user_id,
                llm_calls=0,
                llm_limit=llm_limit,
                tool_calls=0,
                tool_limit=tool_limit,
                rounds=0,
                progress_checkpoint_calls=progress_checkpoint_calls,
                budget_checkpoint_tool_calls=budget_checkpoint_tool_calls,
            )
            state.progress.setdefault("started_at", datetime.now().isoformat())
            state.progress.setdefault("checkpoint_count", 0)
            # Подготавливаем сообщения
            t_build_start = __import__('time').time()
            if self.use_dynamic_prompts:
                # Детализированные тайминги подготовки контекста
                t_hist_start = __import__('time').time()
                # Внутри prepare_messages_dynamic произойдёт ленивый fetch истории из Redis (если нужно)
                messages = await self._prepare_messages_dynamic(message, context, user_id)
                t_hist_end = __import__('time').time()
                # Сохраняем в отладочной трассе
                debug_hist_ms = int((t_hist_end - t_hist_start) * 1000)
                # Инициализируем debug_trace, чтобы тайминги не потерялись до заполнения ниже
                debug_trace = {
                    "timings": {
                        "build_messages_ms": int((t_hist_end - t_build_start) * 1000),
                        "prepare_history_ms": debug_hist_ms,
                    }
                }
                state.debug_trace = debug_trace
                self._update_debug_snapshot(state)
            else:
                messages = []
                messages.append({"role": "system", "content": self.system_prompt})
                if context:
                    messages.extend(context)
                # Инъекция фрактального контекста и в не‑динамической ветке
                try:
                    zoom_items = await fractal_graph.retrieve_context(query=message, scale="auto", k=8)
                    if zoom_items:
                        fc = self._format_fractal_context(zoom_items)
                        if fc:
                            messages[0]["content"] = (fc.rstrip() + "\n\n" + messages[0]["content"]).strip()
                except Exception as e:
                    logger.warning(f"Fractal context injection (non-dynamic) failed: {e}")
                messages.append({"role": "user", "content": message})
            t_build_end = __import__('time').time()
            
            # Параметры для API
            api_params = {
                "model": self.model,
                "messages": messages,
            }
            # Устанавливаем температуру, если она явно задана и отличается от 1.0
            if self.temperature is not None and float(self.temperature) != 1.0:
                api_params["temperature"] = self.temperature
            
            # Лимит длины генерации
            max_limit = override_max_tokens if override_max_tokens is not None else self.max_tokens
            if max_limit:
                api_params["max_tokens"] = max_limit
            
            # Первый ход: просим модель спланировать без инструментов (план + критерии)
            if use_tools and self.tools:
                planning_hint = (
                    "Сначала краткий план действий без вызова инструментов: шаги, критерий результата, бюджет инструментов."
                    f" Допустимый бюджет инструментов за запрос: {state.tool_limit}."
                    " Затем, если необходимо, переходи к инструментам."
                    " Если бюджет инструментов исчерпан или близок к исчерпанию — дай финальный краткий ответ,"
                    " зафиксируй прогресс и остановись. Избегай холостых повторов и пустых вызовов инструментов."
                )
                messages.insert(1, {"role": "system", "content": planning_hint})
                # Разрешаем инструментам быть вызванными уже на первом ходе (для проверки бюджета)
                api_params["tools"] = self.tools
                api_params["tool_choice"] = "auto"
            
            # Собираем отладочную информацию перед вызовом LLM
            # Подсчёт размеров промпта по ролям
            sys_len = len(messages[0].get("content", "")) if messages and messages[0].get("role") == "system" else 0
            user_msgs = [m for m in messages if m.get("role") == "user"]
            asst_msgs = [m for m in messages if m.get("role") == "assistant"]
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            system_msgs = [m for m in messages if m.get("role") == "system"]
            hist_msgs = [m for m in messages if m.get("role") in ("user","assistant")]
            def _tok_est(text: str) -> int:
                return int(len(text) / 4) if text else 0
            prompt_sizes = {
                "system_chars": sys_len,
                "system_tokens_est": _tok_est(system_msgs[0].get("content","")) if system_msgs else 0,
                "history_count": len(hist_msgs),
                "history_tokens_est": sum(_tok_est((m.get("content") or "")) for m in hist_msgs),
                "user_count": len(user_msgs),
                "assistant_count": len(asst_msgs),
                "tool_count": len(tool_msgs),
                "total_messages": len(messages),
            }
            # Если ранее мы частично наполнили debug_trace, дополним его; иначе создадим
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
                "prompt_sizes": prompt_sizes,
                "timings": {
                    **((debug_trace.get("timings") or {}) if 'debug_trace' in locals() else {}),
                    "build_messages_ms": int((t_build_end - t_build_start) * 1000),
                }
            }
            # Сохраняем отладочную информацию ДО вызова LLM, чтобы видеть контекст даже при таймауте
            state.debug_trace = debug_trace
            self._update_debug_snapshot(state)
            
            # Вызываем OpenAI API
            logger.info(f"🤖 Отправка запроса к {self.model}")
            t_llm_start = __import__('time').time()
            try:
                response = await self._create_with_limit(state, **api_params)
            except Exception as e:
                err_text = str(e).lower()
                # Авто-ретраи для несовместимых параметров
                if "temperature" in err_text and ("unsupported" in err_text or "unsupported_value" in err_text):
                    logger.warning("🔁 Повтор запроса без temperature из-за ограничений модели")
                    api_params.pop("temperature", None)
                    response = await self._create_with_limit(state, **api_params)
                elif "max_tokens" in err_text and ("unsupported" in err_text or "unsupported_parameter" in err_text):
                    # Переключаемся на max_completion_tokens
                    val = api_params.pop("max_tokens", None)
                    if val is not None:
                        api_params["max_completion_tokens"] = val
                    logger.warning("🔁 Повтор запроса с max_completion_tokens вместо max_tokens")
                    response = await self._create_with_limit(state, **api_params)
                elif "max_completion_tokens" in err_text and ("unsupported" in err_text or "unsupported_parameter" in err_text):
                    # Переключаемся обратно на max_tokens
                    val = api_params.pop("max_completion_tokens", None)
                    if val is not None:
                        api_params["max_tokens"] = val
                    logger.warning("🔁 Повтор запроса с max_tokens вместо max_completion_tokens")
                    response = await self._create_with_limit(state, **api_params)
                elif ("rate limit" in err_text) or ("rate_limit" in err_text) or ("too many requests" in err_text) or (" 429" in err_text):
                    # Мягкая обработка 429/TPM: подождём указанное время и повторим один раз
                    try:
                        import re
                        m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", str(e), flags=re.IGNORECASE)
                        wait_s = float(m.group(1)) if m else 12.0
                        wait_s = max(3.0, min(wait_s + 0.5, 25.0))
                    except Exception:
                        wait_s = 12.0
                    try:
                        logger.warning(f"⏳ Rate limit detected, sleep {wait_s:.2f}s and retry")
                        await asyncio.sleep(wait_s)
                        # Отметим задержку в отладке (запишется позже в metadata.timings)
                        try:
                            if 'debug_trace' in locals():
                                dt = debug_trace.get("timings", {})
                                dt["tpm_wait_ms"] = int(wait_s * 1000)
                                debug_trace["timings"] = dt
                        except Exception:
                            pass
                        response = await self._create_with_limit(state, **api_params)
                    except Exception as er:
                        if isinstance(er, RuntimeError) and "llm_limit_reached" in str(er):
                            report = self._build_limit_report(state, rounds=0, t_start=t_llm_start, prompt_sizes={})
                            return report
                        raise
                else:
                    if isinstance(e, RuntimeError) and "llm_limit_reached" in str(e):
                        # Формируем отчёт о достигнутом лимите
                        report = self._build_limit_report(state, rounds=0, t_start=t_llm_start, prompt_sizes={})
                        return report
                    raise
            t_llm_end = __import__('time').time()
            
            # Обрабатываем ответ
            result = await self._process_response(response, messages, state)
            # Сохраняем ранний прогресс в память (внутренний чекпоинт)
            try:
                if state.llm_calls >= state.progress_checkpoint_calls:
                    snapshot = self._build_progress_checkpoint(state, rounds=1, t_start=t_llm_start, prompt_sizes=prompt_sizes)
                    state.progress_snapshots.append(snapshot)
                    state.progress["checkpoint_count"] = len(state.progress_snapshots)
                    # Персист краткого прогресса в память
                    summary = snapshot.get("content", "")
                    if summary:
                        await memory_manager.save(
                            text=summary,
                            metadata={
                                "type": "progress_checkpoint",
                                "user_id": user_id,
                                "timestamp": int(__import__('time').time()),
                            }
                        )
            except Exception:
                pass

            # Многошаговый цикл инструментов: повторяем, пока модель вызывает инструменты,
            # но ограничиваемся MAX_CONCURRENT_TOOLS*2 раундами для безопасности
            max_rounds = max(3, int(getattr(settings, "MAX_CONCURRENT_TOOLS", 5)) * 2)
            rounds = 1
            state.rounds = rounds
            while use_tools and self.tools and (result.get("tool_calls") or []) and rounds < max_rounds:
                rounds += 1
                state.rounds = rounds
                # После каждого исполнения инструментов модель уже запрашивала финальный текст.
                # Если финальный текст пустой и снова есть намерение вызвать инструменты — позволим ещё один цикл
                last_messages = list(messages)
                # Принудительно просим модель продолжить решение до завершения или запроса подтверждения
                # Инъекция состояния бюджета инструментов
                budget_left = max(0, state.tool_limit - state.tool_calls)
                budget_hint = (
                    f"Бюджет инструментов на этот запрос: всего {state.tool_limit}, осталось {budget_left}. "
                    "Вызывай инструменты только если нужно для следующего проверяемого шага."
                )
                last_messages.append({"role": "system", "content": budget_hint})
                api_loop = {"model": self.model, "messages": last_messages, "tools": self.tools, "tool_choice": "auto"}
                try:
                    response = await self._create_with_limit(state, **api_loop)
                except Exception as e:
                    if isinstance(e, RuntimeError) and "llm_limit_reached" in str(e):
                        report = self._build_limit_report(state, rounds=rounds, t_start=t_llm_start, prompt_sizes=prompt_sizes)
                        return report
                    # Обработка 429/TPM и здесь
                    err_text = str(e).lower()
                    if ("rate limit" in err_text) or ("rate_limit" in err_text) or ("too many requests" in err_text) or (" 429" in err_text):
                        try:
                            import re
                            m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", str(e), flags=re.IGNORECASE)
                            wait_s = float(m.group(1)) if m else 10.0
                            wait_s = max(3.0, min(wait_s + 0.5, 25.0))
                        except Exception:
                            wait_s = 10.0
                        logger.warning(f"⏳ Rate limit in tools loop, sleep {wait_s:.2f}s and retry")
                        await asyncio.sleep(wait_s)
                        response = await self._create_with_limit(state, **api_loop)
                    else:
                        raise
                result = await self._process_response(response, last_messages, state)
                # Логируем прогресс циклов
                try:
                    loop_ms = int((__import__('time').time() - t_llm_start) * 1000)
                    logger.info(f"tools_loop_round={rounds} llm_call_ms_total~={loop_ms}")
                except Exception:
                    pass
                # Чекпоинт бюджета инструментов с персистом
                try:
                    if state.tool_calls % max(1, state.budget_checkpoint_tool_calls) == 0 and state.tool_calls != 0:
                        budget_snapshot = (
                            f"Бюджет инструментов: использовано {state.tool_calls} из {state.tool_limit}."
                        )
                        state.progress["last_budget_snapshot"] = budget_snapshot
                        await memory_manager.save(
                            text=budget_snapshot,
                            metadata={
                                "type": "budget_checkpoint",
                                "user_id": user_id,
                                "timestamp": int(__import__('time').time()),
                            }
                        )
                except Exception:
                    pass

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
                # Диагностика ответа: finish_reason, длина контента, количество tool_calls
                try:
                    fr = getattr(getattr(response.choices[0], "finish_reason", None), "value", None) or getattr(response.choices[0], "finish_reason", None)
                except Exception:
                    fr = None
                try:
                    tc_count = len(getattr(response.choices[0].message, "tool_calls", []) or [])
                except Exception:
                    tc_count = 0
                logger.info(f"LLM after_llm: finish_reason={fr}, content_len={len(getattr(first_msg_obj,'content','') or '')}, tool_calls={tc_count}")
            except Exception:
                first_msg = None

            pre_llm_ms = int((t_llm_start - t_func_start) * 1000)
            first_llm_ms = int((t_llm_end - t_llm_start) * 1000)
            debug_trace.update({
                "stage": "after_llm",
                "usage": usage,
                "first_model_message": first_msg,
                "tool_calls_count": len(getattr(response.choices[0].message, "tool_calls", []) or []),
                "timings": {
                    **(debug_trace.get("timings") or {}),
                    "pre_llm_ms": pre_llm_ms,
                    "llm_first_call_ms": first_llm_ms,
                    "llm_call_ms": int((t_llm_end - t_llm_start) * 1000)
                }
            })
            state.debug_trace = debug_trace
            self._update_debug_snapshot(state)
            
            # Если контент пустой, делаем один принудительный повтор без инструментов
            if not (result.get("content") or "").strip():
                try:
                    fr = getattr(getattr(response.choices[0], "finish_reason", None), "value", None) or getattr(response.choices[0], "finish_reason", None)
                except Exception:
                    fr = None
                logger.warning(f"⚠️ Пустой ответ модели. Повтор запроса без инструментов (finish_reason={fr}).")
                try:
                    messages_retry = list(messages)
                    messages_retry.append({
                        "role": "system",
                        "content": "Ответь текстом, кратко (1–2 предложения)."
                    })
                    retry_kwargs = {"model": self.model, "messages": messages_retry}
                    if self.tools:
                        retry_kwargs["tools"] = self.tools
                        retry_kwargs["tool_choice"] = "none"
                    response_retry = await self._create_with_limit(state, **retry_kwargs)
                    result = await self._process_response(response_retry, messages_retry, state)
                except Exception as e:
                    if isinstance(e, RuntimeError) and "llm_limit_reached" in str(e):
                        report = self._build_limit_report(state, rounds=rounds, t_start=t_llm_start, prompt_sizes=prompt_sizes)
                        return report
                    logger.warning(f"Повтор без инструментов не удался: {e}")

            # Ранний чекпоинт прогресса: если инструментов не было и количество вызовов достигло порога
            try:
                if state.tool_calls == 0 and state.llm_calls >= state.progress_checkpoint_calls:
                    early = self._build_progress_checkpoint(state, rounds=rounds, t_start=t_llm_start, prompt_sizes=prompt_sizes)
                    # Вставляем краткий отчёт в начало ответа
                    result["content"] = (early["content"] + "\n\n" + (result.get("content") or "")).strip()
                    result.setdefault("metadata", {}).update({"progress_checkpoint": True})
                    state.progress.setdefault("early_checkpoint", True)
                    # Персистим отчёт
                    try:
                        await memory_manager.save(
                            text=early.get("content", ""),
                            metadata={
                                "type": "progress_checkpoint",
                                "user_id": user_id,
                                "timestamp": int(__import__('time').time()),
                            }
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Добавляем метаданные
            t_total_end = __import__('time').time()
            tools_phase_ms = None
            try:
                tools_phase_ms = int((t_total_end - t_llm_end) * 1000)
            except Exception:
                tools_phase_ms = None
            result["metadata"] = {
                "model": self.model,
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": datetime.now().isoformat(),
                "tokens_used": response.usage.total_tokens if response.usage else None,
                "prompt_sizes": prompt_sizes,
                "timings": {
                    **(debug_trace.get("timings") or {}),
                    "agent_total_ms": int((t_total_end - t_func_start) * 1000),
                    **({"tools_phase_ms": tools_phase_ms} if tools_phase_ms is not None else {}),
                },
                "rounds": state.rounds,
                "tool_calls_count": state.tool_calls,
                "llm_calls": state.llm_calls,
                "selected_prompt": getattr(self, "_last_prompt_name", None),
                "router_context": getattr(self, "_last_router_context", None),
            }
            # Встраиваем собранные чекпоинты в метаданные
            if state.progress_snapshots:
                try:
                    result["metadata"]["progress_snapshots"] = [s.get("content") for s in state.progress_snapshots][:3]
                except Exception:
                    pass
            # REAP: Reflect/Extract/Apply/Persist — минимальная встройка
            try:
                outcome = {
                    "text": result.get("content", ""),
                    "steps": [tc.get("name") for tc in (result.get("tool_calls") or [])],
                }
                incident = await detect_incident(outcome)
                skill = await mine_skill(outcome)
                result["metadata"]["reap"] = {"incident": incident, "skill": skill}
            except Exception as _e:
                try:
                    result.setdefault("metadata", {})["reap_error"] = str(_e)
                except Exception:
                    pass
            
            # Обновляем историю (персонально для пользователя)
            history_key = user_id or "anonymous"
            user_hist = self.user_histories.setdefault(history_key, [])
            new_entries = [{"role": "user", "content": message}, {"role": "assistant", "content": result.get("content", "")}]
            user_hist.extend(new_entries)
            # Ограничение длины истории per-user
            if len(user_hist) > self._max_history_per_user:
                # Оставляем последние N записей
                self.user_histories[history_key] = user_hist[-self._max_history_per_user:]
            # Персист в Redis (лучше хранить больше, чем in-memory лимит)
            await self._persist_user_history_to_store(history_key, new_entries)
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
            state.debug_trace = debug_trace
            self._update_debug_snapshot(state)

            return result

        except Exception as e:
            # Специальная обработка лимита, чтобы вернуть краткий отчёт вместо сырой ошибки
            try:
                if isinstance(e, RuntimeError) and "llm_limit_reached" in str(e):
                    report = self._build_limit_report(
                        state,
                        rounds=state.rounds,
                        t_start=locals().get("t_llm_start", None),
                        prompt_sizes=locals().get("prompt_sizes", {})
                    )
                    return report
            except Exception:
                pass
            try:
                state.debug_trace.setdefault("error", str(e))
                self._update_debug_snapshot(state)
            except Exception:
                pass
            logger.error(f"❌ Ошибка в chat: {str(e)}")
            return {
                "content": f"Произошла ошибка: {str(e)}",
                "error": True,
                "metadata": {"error": str(e)}
            }

    async def generate_response(
        self,
        prompt: str,
        *,
        user_id: Optional[str] = None,
        chat_id: Optional[int] = None,
        context: Optional[List[Dict[str, str]]] = None,
        use_tools: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        llm_calls_limit: Optional[int] = None,
        tool_calls_limit: Optional[int] = None,
    ) -> str:
        """Сгенерировать текстовый ответ, используя основную логику chat."""
        prev_temperature = self.temperature
        temperature_overridden = False
        if temperature is not None and temperature != self.temperature:
            self.temperature = temperature
            temperature_overridden = True

        try:
            response = await self.chat(
                prompt,
                user_id=user_id,
                chat_id=chat_id,
                context=context,
                use_tools=use_tools,
                override_max_tokens=max_tokens,
                override_llm_calls_limit=llm_calls_limit,
                override_tool_calls_limit=tool_calls_limit,
            )
        finally:
            if temperature_overridden:
                self.temperature = prev_temperature

        if isinstance(response, dict) and "content" in response:
            content = response.get("content")
            if isinstance(content, str):
                return content
            if content is None:
                return ""
            return str(content)

        return ""

    async def _create_with_limit(self, state: RequestState, **kwargs) -> ChatCompletion:
        """Обертка над client.chat.completions.create с лимитом вызовов за запрос."""
        try:
            limit = state.llm_limit
            calls = state.llm_calls
            if limit is not None and calls >= int(limit):
                raise RuntimeError("llm_limit_reached")
            state.llm_calls = calls + 1
            return await self.client.chat.completions.create(**kwargs)
        except Exception:
            raise

    def _build_limit_report(self, state: RequestState, rounds: int, t_start: float, prompt_sizes: Dict[str, Any]) -> Dict[str, Any]:
        """Сформировать краткий отчёт при достижении лимита LLM-вызовов."""
        try:
            elapsed_ms = int((__import__('time').time() - t_start) * 1000) if t_start else None
        except Exception:
            elapsed_ms = None
        calls = state.llm_calls
        limit = state.llm_limit
        tools_used = state.tool_calls
        content = (
            f"⏹ Достигнут лимит вызовов LLM: {calls} из {limit}.\n"
            f"Что сделано:\n- Раундов инструментов: {rounds}\n- Вызовы инструментов: {tools_used}\n"
            + (f"- Время обработки LLM: ~{elapsed_ms} мс\n" if elapsed_ms is not None else "")
            + "\nОтветьте ‘продолжай’, чтобы выполнить ещё шаги, или уточните запрос."
        )
        return {
            "content": content,
            "tool_calls": [],
            "metadata": {
                "limit_reached": True,
                "llm_calls": calls,
                "llm_limit": limit,
                "tool_calls_count": tools_used,
                "prompt_sizes": prompt_sizes,
            }
        }

    def _build_progress_checkpoint(self, state: RequestState, rounds: int, t_start: float, prompt_sizes: Dict[str, Any]) -> Dict[str, Any]:
        """Короткий промежуточный отчёт о прогрессе, чтобы не ждать лимита."""
        try:
            elapsed_ms = int((__import__('time').time() - t_start) * 1000) if t_start else None
        except Exception:
            elapsed_ms = None
        calls = state.llm_calls
        tools_used = state.tool_calls
        content = (
            f"⏸ Промежуточный отчёт: LLM-вызовов {calls}, инструментов {tools_used}, раундов {rounds}."
            + (f" Время: ~{elapsed_ms} мс." if elapsed_ms is not None else "")
        )
        return {
            "content": content,
            "tool_calls": [],
            "metadata": {
                "checkpoint": True,
                "llm_calls": calls,
                "tool_calls_count": tools_used,
                "prompt_sizes": prompt_sizes,
            },
        }
    
    async def _process_response(
        self,
        response: ChatCompletion,
        messages: List[Dict[str, str]],
        state: RequestState,
    ) -> Dict[str, Any]:
        """Обработка ответа от OpenAI API"""
        message = response.choices[0].message

        # Если есть вызовы инструментов
        if message.tool_calls:
            tool_results = await self._execute_tools(state, message.tool_calls)
            
            # Добавляем результаты инструментов в историю
            messages.append(message.model_dump())
            
            for tool_call, result in zip(message.tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": getattr(tool_call, "id", None),
                    "content": json.dumps(result, ensure_ascii=False, default=str)
                })
            
            # Получаем финальный ответ
            # Важно: после инструментов принудительно требуем текстовый ответ
            # чтобы избежать повторного tool_call и пустого content
            final_kwargs = {"model": self.model, "messages": messages}
            if self.tools:
                final_kwargs["tools"] = self.tools
                final_kwargs["tool_choice"] = "none"
            final_response = await self._create_with_limit(state, **final_kwargs)
            
            final_message = final_response.choices[0].message
            # Защитный фолбэк: если контент пуст, вернем метаданные причины
            final_content = getattr(final_message, "content", None)
            if not (final_content or "").strip():
                try:
                    fr = getattr(getattr(final_response.choices[0], "finish_reason", None), "value", None) or getattr(final_response.choices[0], "finish_reason", None)
                except Exception:
                    fr = None
                logger.warning(f"⚠️ Финальный ответ без контента после tools. finish_reason={fr}")
                final_content = ""
            
            return {
                "content": final_content,
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

    def _prepare_tool_call_arguments(
        self,
        tool_name: str,
        function: callable,
        args: Optional[Dict[str, Any]],
        state: Optional[RequestState] = None,
    ) -> Dict[str, Any]:
        """Подготовить аргументы для вызова инструмента согласно его сигнатуре."""
        normalized_args: Dict[str, Any] = {}
        base_args = args or {}

        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):
            return dict(base_args)

        allowed = set(signature.parameters.keys())
        normalized_args = {k: v for k, v in base_args.items() if k in allowed}
        dropped = sorted(set(base_args.keys()) - allowed)
        if dropped:
            logger.warning(
                f"🔎 Игнорирую неподдерживаемые аргументы для {tool_name}: {dropped}"
            )

        if "metadata" in signature.parameters:
            metadata = normalized_args.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            current_user = state.user_id if state else None
            if current_user:
                metadata.setdefault("owner_id", current_user)
                metadata.setdefault("user_id", current_user)
            metadata.setdefault("timestamp", int(__import__('time').time()))
            normalized_args["metadata"] = metadata

        return normalized_args

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Union[str, Dict[str, Any]]] = None,
        state: Optional[RequestState] = None,
    ) -> Any:
        """Вызвать зарегистрированный инструмент напрямую."""
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("Tool name must be a non-empty string")

        normalized_name = tool_name.strip()
        if normalized_name not in self.tool_functions:
            raise ValueError(f"Tool '{normalized_name}' is not registered")

        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments)
            except Exception:
                parsed_args = {}
        elif isinstance(arguments, dict):
            parsed_args = arguments
        else:
            parsed_args = {}

        function = self.tool_functions[normalized_name]
        filtered_args = self._prepare_tool_call_arguments(normalized_name, function, parsed_args, state)

        logger.info(f"🔧 Вызов инструмента: {normalized_name}")
        try:
            if inspect.iscoroutinefunction(function):
                result = await function(**filtered_args)
            else:
                outcome = function(**filtered_args)
                result = await outcome if inspect.iscoroutine(outcome) else outcome

            if state is not None:
                try:
                    state.tool_calls += 1
                except Exception:
                    pass

            return result
        except Exception as exc:
            logger.error(f"❌ Ошибка выполнения инструмента {normalized_name}: {exc}")
            raise

    async def _execute_tools(
        self,
        state: RequestState,
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
            # Проверяем бюджет инструментов
            try:
                if state.tool_calls >= state.tool_limit:
                    logger.warning("⏹ Достигнут лимит инструментов на запрос — пропускаю выполнение.")
                    results.append({"error": "tool_budget_exhausted"})
                    continue
            except Exception:
                pass
            
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
                filtered_args = self._prepare_tool_call_arguments(tool_name, function, args, state)
                t0 = __import__('time').time()
                if inspect.iscoroutinefunction(function):
                    result = await function(**filtered_args)
                else:
                    res = function(**filtered_args)
                    if inspect.iscoroutine(res):
                        result = await res
                    else:
                        result = res
                duration_ms = int((__import__('time').time() - t0) * 1000)

                state.tool_calls += 1
                results.append(result)

                # Логируем вызов инструмента в память (для прозрачности и обучения)
                try:
                    # Определяем успех по отсутствию ключа error
                    success = True
                    error_text = None
                    if isinstance(result, dict) and result.get("error"):
                        success = False
                        error_text = str(result.get("error"))
                    elif isinstance(result, str) and '"error"' in result.lower():
                        success = False
                        error_text = "error in string result"
                    # Краткое представление аргументов
                    try:
                        args_preview = json.dumps(filtered_args, ensure_ascii=False)[:800]
                    except Exception:
                        args_preview = str(filtered_args)[:800]
                    text = (
                        f"TOOL {tool_name}: {'OK' if success else 'FAIL'} in {duration_ms} ms\n"
                        f"args={args_preview}"
                    )
                    await memory_manager.save(
                        text=text,
                        metadata={
                            "type": "tool_call",
                            "tool": tool_name,
                            "success": success,
                            "duration_ms": duration_ms,
                            "user_id": state.user_id,
                            "timestamp": int(__import__('time').time()),
                            "error": error_text,
                        },
                    )
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения {tool_name}: {str(e)}")
                results.append({
                    "error": f"Error executing {tool_name}: {str(e)}"
                })
                # Персист ошибки инструмента
                try:
                        await memory_manager.save(
                            text=f"TOOL {tool_name}: EXCEPTION {str(e)[:400]}",
                            metadata={
                                "type": "tool_call",
                                "tool": tool_name,
                                "success": False,
                                "user_id": state.user_id,
                                "timestamp": int(__import__('time').time()),
                                "error": str(e)[:800],
                            },
                        )
                except Exception:
                    pass
        
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
    
    def _compact_prompt(self, text: str) -> str:
        """Уплотнение системного промпта: удаление повторов, лишних пустых строк,
        схлопывание пробелов и не влияющих на смысл формулировок.
        Безопасно: не меняет смысл, только представление.
        """
        try:
            # Сначала удалим повторяющиеся абзацы/строки существующим методом
            dedup = self._deduplicate_system_prompt(text)
            # Схлопываем множественные пробелы внутри строк
            lines = []
            for ln in dedup.splitlines():
                stripped = " ".join(ln.strip().split())
                lines.append(stripped)
            # Убираем последовательные пустые строки
            out = []
            prev_blank = False
            for ln in lines:
                is_blank = (ln == "")
                if is_blank and prev_blank:
                    continue
                out.append(ln)
                prev_blank = is_blank
            compact = "\n".join(out).strip()
            # Мини-замены формулировок без потери смысла
            replacements = {
                "Всегда:": "Всегда делай:",
                "Ты - Марк,": "Ты — Марк,",
            }
            for a, b in replacements.items():
                compact = compact.replace(a, b)
            return compact
        except Exception:
            return text
    
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
        if not per_user_hist:
            # Ленивая подгрузка истории из Redis (последние 12 сообщений)
            loaded = await self._load_user_history_from_store(history_key, max_items=24)
            if loaded:
                self.user_histories[history_key] = loaded
                per_user_hist = loaded

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
            # Инъекция фрактального контекста и в фолбэк-ветке
            try:
                zoom_items = await fractal_graph.retrieve_context(query=message, scale="auto", k=8)
                if zoom_items:
                    fc = self._format_fractal_context(zoom_items)
                    if fc:
                        messages[0]["content"] = (messages[0]["content"].rstrip() + "\n\n" + fc).strip()
            except Exception as e:
                logger.warning(f"Fractal context injection (fallback) failed: {e}")
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
        # Инъекция стилистики краткости при verbosity=auto
        if self._verbosity_mode == "auto":
            brevity_instruction = (
                "СТИЛЬ ОТВЕТА: кратко по умолчанию; сначала уточняй, если контекст недостаточен; "
                "развёрнутый ответ — только по запросу пользователя."
            )
            optimized_context = (optimized_context.rstrip() + "\n\n" + brevity_instruction).strip()

        messages = [{"role": "system", "content": optimized_context}]

        # Инъекция фрактального контекста (zoom-attention) в системный блок
        try:
            zoom_items = await fractal_graph.retrieve_context(query=message, scale="auto", k=8)
            if zoom_items:
                fc = self._format_fractal_context(zoom_items)
                if fc:
                    messages[0]["content"] = (fc.rstrip() + "\n\n" + messages[0]["content"]).strip()
                fc = self._format_fractal_context(zoom_items)
                if fc:
                    messages[0]["content"] = (fc.rstrip() + "\n\n" + messages[0]["content"]).strip()
        except Exception as e:
            logger.warning(f"Fractal context injection failed: {e}")
        
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

    def _format_fractal_context(self, items: List[Dict[str, Any]]) -> str:
        """Сформировать краткий блок фрактального контекста для системного промпта."""
        try:
            lines: List[str] = []
            for it in items[:8]:
                md = it.get("metadata", {}) or {}
                scale = md.get("scale") or md.get("payload", {}).get("scale") or "?"
                ntype = md.get("type") or it.get("type") or "Node"
                text = (it.get("text") or "")[:140].replace("\n", " ")
                lines.append(f"- [{scale}] {ntype}: {text}")
            if not lines:
                return ""
            return "Фрактальный контекст:\n" + "\n".join(lines)
        except Exception:
            return ""

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