"""
Сервис для интеграции с системой чата
"""

import logging
from typing import Dict, Any, Optional, AsyncGenerator, Tuple
import asyncio
import time
import httpx

from ..config import bot_config
from core.memory.graphiti_adapter import graphiti_adapter

logger = logging.getLogger(__name__)


class ChatService:
    """
    Сервис для взаимодействия с enhanced_chat API
    """
    
    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = base_url or bot_config.APP_HOST
        self.timeout = timeout or bot_config.REQUEST_TIMEOUT
        
        # Создаем HTTP клиент с настройками
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers={"Content-Type": "application/json"},
            http2=True,
            limits=limits
        )
        # TPM limiter (простая скользящая минутная сумма)
        self._tpm_tokens: int = 0
        self._tpm_window_start: float = time.time()
        self._tpm_lock = asyncio.Lock()
        self._last_wait_ms: float = 0.0
    
    async def close(self):
        """Закрыть HTTP клиент"""
        await self.client.aclose()
    
    async def ask_question(
        self,
        question: str,
        user_id: str,
        chat_id: Optional[int] = None,
        mode: str = "chat"
    ) -> Dict[str, Any]:
        """
        Отправить вопрос в enhanced_chat
        
        Args:
            question: Текст вопроса
            user_id: ID пользователя
            chat_id: ID чата (опционально)
            mode: Режим работы (chat, task, analysis)
            
        Returns:
            Ответ от API
        """
        try:
            # Подготавливаем данные в зависимости от endpoint
            if bot_config.USE_ENHANCED_CHAT:
                # Формат для /api/chat
                payload = {
                    "message": question,  # используем message, не question
                    "user_id": str(user_id),
                    "session_id": f"telegram_{user_id}_{chat_id}" if chat_id else f"telegram_{user_id}",
                    "context": {"mode": mode}
                }
                endpoint = "/api/chat"
            else:
                # Формат для legacy /chat/ask
                payload = {
                    "question": question,
                    "user_id": str(user_id),
                    "mode": mode
                }
                if chat_id is not None:
                    payload["chat_id"] = chat_id
                endpoint = "/chat/ask"
            
            # Персонализация: компактный профиль пользователя
            try:
                profile = await self._build_user_profile(str(user_id))
                if profile:
                    payload["context"]["user_profile"] = profile
            except Exception:
                pass
            
            logger.info(f"Sending request to {endpoint}: user={user_id}, mode={mode}")
            
            # Урезаем контекст, если надо
            t_start = time.time()
            payload, trimmed, est_before, est_after = await self._trim_context(payload)
            
            # Отправляем запрос с retry на 429
            response, waited_ms = await self._post_with_retry(endpoint, payload)
            
            data = response.json()
            # Обновляем TPM по возвращаемым метрикам, если есть
            self._account_tokens_used(data)
            t_end = time.time()
            timings = {
                "prepare_ms": 0,  # подготовка в этой функции в основном тримминг
                "http_ms": int((t_end - t_start) * 1000),
                "total_ms": int((t_end - t_start) * 1000),
                "tpm_wait_ms": int(waited_ms),
            }
            sizes = {
                "message_chars": len(payload.get("message", "")),
                "est_tokens_before": est_before,
                "est_tokens_after": est_after,
                "profile_chars": len((payload.get("context", {}) or {}).get("user_profile", "")),
                "trimmed": bool(trimmed),
            }
            meta = data.get("metadata") or {}
            meta["timings"] = timings
            meta["sizes"] = sizes
            # Переименуем некоторые ключи для удобства чтения в боте
            if "rounds" in meta or "tool_calls_count" in meta or "llm_calls" in meta:
                meta["progress"] = {
                    "rounds": meta.get("rounds"),
                    "tool_calls": meta.get("tool_calls_count"),
                    "llm_calls": meta.get("llm_calls"),
                }
            data["metadata"] = meta
            logger.info(f"LLM timings: {timings} sizes: {sizes}")
            
            # Логируем использование инструментов
            if data.get("tool_calls"):
                tools_used = [tc.get("name") for tc in data["tool_calls"]]
                logger.info(f"Tools used: {tools_used}")
            
            return data
            
        except httpx.TimeoutException:
            logger.error(f"Timeout while calling {endpoint}")
            return {
                "error": True,
                "content": "⏱️ Превышено время ожидания ответа. Попробуйте еще раз.",
                "metadata": {"error": "timeout"}
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            return {
                "error": True,
                "content": f"❌ Ошибка сервера: {e.response.status_code}",
                "metadata": {"error": f"http_{e.response.status_code}"}
            }
            
        except Exception as e:
            logger.error(f"Unexpected error in ask_question: {str(e)}")
            return {
                "error": True,
                "content": "😔 Произошла неожиданная ошибка. Попробуйте позже.",
                "metadata": {"error": str(e)}
            }

    async def _post_with_retry(self, endpoint: str, payload: Dict[str, Any]) -> Tuple[httpx.Response, float]:
        """POST с экспоненциальным backoff на 429 и учётом TPM.
        """
        retries = bot_config.RATE_LIMIT_MAX_RETRIES
        backoff = bot_config.RATE_LIMIT_BACKOFF_BASE
        last_exc = None
        wait_acc_ms = 0.0
        for attempt in range(retries + 1):
            # Простой TPM‑гейт
            waited = await self._wait_for_tpm_budget(payload)
            wait_acc_ms += (waited * 1000.0)
            try:
                r = await self.client.post(endpoint, json=payload)
                if r.status_code == 429:
                    # Логируем инцидент 429 как эпизод в память
                    try:
                        asyncio.create_task(self._log_rate_limit_episode(payload, endpoint, attempt))
                    except Exception:
                        pass
                    raise httpx.HTTPStatusError("rate limited", request=None, response=r)
                r.raise_for_status()
                return r, wait_acc_ms
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code == 429:
                    # backoff + джиттер
                    sleep_s = (backoff ** attempt) + (0.1 * attempt)
                    logger.warning(f"429 received. Retry in {sleep_s:.2f}s (attempt {attempt+1}/{retries})")
                    await asyncio.sleep(sleep_s)
                    last_exc = e
                    continue
                raise
        # если не удалось
        raise last_exc if last_exc else Exception("POST failed without response")

    async def _wait_for_tpm_budget(self, payload: Dict[str, Any]) -> float:
        """Ждём, если рискуем превысить TPM."""
        async with self._tpm_lock:
            now = time.time()
            if now - self._tpm_window_start >= 60:
                self._tpm_window_start = now
                self._tpm_tokens = 0
            # прогноз: пользовательские токены + максимальный ген
            est_in = self._estimate_tokens_in(payload.get("message", ""))
            projected = self._tpm_tokens + est_in + bot_config.MAX_GEN_TOKENS
            if projected > bot_config.OPENAI_TPM_LIMIT:
                wait_s = 60 - (now - self._tpm_window_start)
                wait_s = max(0.5, wait_s)
                logger.warning(f"TPM projected {projected} > limit {bot_config.OPENAI_TPM_LIMIT}. Sleep {wait_s:.2f}s")
                await asyncio.sleep(wait_s)
                self._last_wait_ms = wait_s * 1000.0
                return wait_s
            self._last_wait_ms = 0.0
            return 0.0

    async def _trim_context(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, int, int]:
        """Урезаем сообщение/контекст, если слишком длинно.
        Простейшая эвристика: ограничить message по символам/словам.
        """
        msg = payload.get("message", "")
        # Быстрая оценка токенов ~ 4 chars/token
        est_tokens = self._estimate_tokens_in(msg)
        if est_tokens > bot_config.MAX_USER_TOKENS:
            ratio = bot_config.MAX_USER_TOKENS / max(1, est_tokens)
            new_len = max(200, int(len(msg) * ratio))
            trimmed = msg[:new_len]
            payload = dict(payload)
            payload["message"] = trimmed + "\n\n[context trimmed]"
            logger.info(f"Message trimmed from {est_tokens}tks to <= {bot_config.MAX_USER_TOKENS}tks")
            return payload, True, est_tokens, self._estimate_tokens_in(payload["message"]) 
        return payload, False, est_tokens, est_tokens

    def _estimate_tokens_in(self, text: str) -> int:
        # Грубая оценка: 1 токен ≈ 4 символа рус/латиницы
        return int(len(text) / 4) if text else 0

    def _account_tokens_used(self, data: Dict[str, Any]):
        """Учитываем токены по ответу API, если backend присылает метаданные.
        Иначе — увеличиваем на MAX_GEN_TOKENS.
        """
        tokens_used = None
        meta = data.get("metadata") or {}
        tokens_used = meta.get("tokens_used") or meta.get("total_tokens")
        async def _bump(n: int):
            async with self._tpm_lock:
                now = time.time()
                if now - self._tpm_window_start >= 60:
                    self._tpm_window_start = now
                    self._tpm_tokens = 0
                self._tpm_tokens += n
        if isinstance(tokens_used, int) and tokens_used > 0:
            asyncio.create_task(_bump(tokens_used))
        else:
            asyncio.create_task(_bump(bot_config.MAX_GEN_TOKENS))

    async def _log_rate_limit_episode(self, payload: Dict[str, Any], endpoint: str, attempt: int):
        """Записать 429 инцидент в память (Graphiti)."""
        try:
            user_id = payload.get("user_id")
            session_id = payload.get("session_id")
            msg_preview = (payload.get("message") or "")[:200]
            text = f"Rate limit 429 на {endpoint}. Попытка {attempt+1}."
            metadata = {
                "type": "rate_limit_incident",
                "http_status": 429,
                "endpoint": endpoint,
                "user_id": user_id,
                "session_id": session_id,
                "message_preview": msg_preview,
            }
            await graphiti_adapter.create_episode(text=text, metadata=metadata)
        except Exception:
            pass

    async def _build_user_profile(self, user_id: str) -> str:
        """Собирает краткий профиль пользователя из ближайших эпизодов памяти."""
        try:
            # Ищем эпизоды, содержащие user_id (простая эвристика)
            res = await graphiti_adapter.search_episodes(query=user_id, limit=5, user_id=user_id)
            items = res.get("items", [])
            if not items:
                return ""
            # Формируем компактный summary
            bullets = []
            for it in items[:5]:
                meta = it.get("metadata", {})
                hint = meta.get("lesson_learned") or meta.get("subject") or it.get("text")
                if hint:
                    bullets.append(str(hint)[:120])
            if not bullets:
                return ""
            profile = "; ".join(bullets[:4])
            return profile
        except Exception:
            return ""

    # stream_answer удалён: используем только синхронные ответы
    
    async def get_chat_modes(self) -> list[Dict[str, str]]:
        """Получить доступные режимы чата"""
        return [
            {"mode": "chat", "name": "💬 Обычный чат", "description": "Дружеская беседа"},
            {"mode": "task", "name": "📋 Режим задач", "description": "Помощь в выполнении задач"},
            {"mode": "analysis", "name": "🔍 Анализ", "description": "Глубокий анализ темы"},
        ]
    
    def format_response(self, response: Dict[str, Any]) -> str:
        """
        Форматировать ответ для отображения в Telegram
        
        Args:
            response: Ответ от API
            
        Returns:
            Отформатированный текст
        """
        if response.get("error"):
            return response.get("content", "Произошла ошибка")
        
        # Основной ответ - проверяем все возможные форматы
        content = response.get("content", response.get("answer", response.get("response", "")))
        
        # Добавляем информацию об использованных инструментах
        if response.get("tool_calls") and len(response["tool_calls"]) > 0:
            tools_info = "\n\n🔧 *Использованные инструменты:*\n"
            for tool in response["tool_calls"]:
                tool_name = tool.get("name", "unknown")
                tools_info += f"• {self._format_tool_name(tool_name)}\n"
            
            content += tools_info
        
        # Добавляем метаданные если есть
        metadata = response.get("metadata", {})
        # Токены показываем только в DEV_MODE
        if bot_config.DEV_MODE and metadata.get("tokens_used"):
            content += f"\n\n_Токенов использовано: {metadata['tokens_used']}_"

        # В DEV_MODE выводим краткую сводку таймингов и прогресса
        try:
            if bot_config.DEV_MODE and metadata:
                timings = metadata.get("timings") or {}
                progress = metadata.get("progress") or {
                    "rounds": metadata.get("rounds"),
                    "tool_calls": metadata.get("tool_calls_count"),
                    "llm_calls": metadata.get("llm_calls"),
                }
                # Ключевые замеры (если есть)
                pre_llm = timings.get("pre_llm_ms") or timings.get("build_messages_ms")
                llm_first = timings.get("llm_first_call_ms") or timings.get("llm_call_ms")
                tools_phase = timings.get("tools_phase_ms")
                total_ms = timings.get("agent_total_ms") or timings.get("total_ms")
                parts = []
                if pre_llm is not None:
                    parts.append(f"pre_llm={int(pre_llm)}ms")
                if llm_first is not None:
                    parts.append(f"llm={int(llm_first)}ms")
                if tools_phase is not None:
                    parts.append(f"tools={int(tools_phase)}ms")
                if total_ms is not None:
                    parts.append(f"total={int(total_ms)}ms")
                pr = []
                if progress.get("rounds") is not None:
                    pr.append(f"rounds={progress['rounds']}")
                if progress.get("tool_calls") is not None:
                    pr.append(f"tools={progress['tool_calls']}")
                if progress.get("llm_calls") is not None:
                    pr.append(f"llm_calls={progress['llm_calls']}")
                if parts or pr:
                    content += "\n\n⏱ " + ", ".join(parts)
                    if pr:
                        content += " | " + ", ".join(pr)
        except Exception:
            pass
        
        return content
    
    def _format_tool_name(self, tool_name: str) -> str:
        """Форматировать имя инструмента для отображения"""
        tool_names = {
            "search_memory": "🔍 Поиск в памяти",
            "save_to_memory": "💾 Сохранение в память",
            "remember_fact": "📝 Запоминание факта",
            "save_fact": "📌 Сохранение факта",
            "vector_search": "🔎 Векторный поиск",
            "start_learning_cycle": "🔄 Запуск цикла обучения",
            "analyze_skill_usage": "📊 Анализ навыков",
        }
        return tool_names.get(tool_name, tool_name)