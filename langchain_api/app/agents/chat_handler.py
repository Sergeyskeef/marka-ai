"""
Chat handler - замена simple_chat на базе OpenAI Agents SDK
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from openai import AsyncOpenAI
from .mark_agent import MarkAgent
from .tools import tool_registry
from .memory_tools import MEMORY_TOOLS
from .advanced_memory_tools import ADVANCED_MEMORY_TOOLS
from .learning_tools import LEARNING_TOOLS
from .vector_search_tools import VECTOR_SEARCH_TOOLS
from .introspection_tools import INTROSPECTION_TOOLS
from .file_tools import FILE_TOOLS
from .sandbox_tools import SANDBOX_TOOLS
from .test_tools import TEST_TOOLS
from .code_analysis_tools import CODE_ANALYSIS_TOOLS
from .dependency_tools import DEPENDENCY_TOOLS
from .change_tracker_tools import CHANGE_TRACKER_TOOLS
from core.memory.memory_manager import memory_manager
from core.memory.graphiti_adapter import graphiti_adapter
from ..prompts import PromptSystemFactory
from redis.asyncio import Redis
import asyncio

logger = logging.getLogger(__name__)

# Глобальный экземпляр агента (будет инициализирован позже)
_agent_instance: Optional[MarkAgent] = None
_prompt_system: Optional[dict] = None
_agent_lock = asyncio.Lock()


async def get_agent() -> MarkAgent:
    """Получить или создать экземпляр агента"""
    global _agent_instance, _prompt_system
    
    if _agent_instance is None:
        async with _agent_lock:
            # Двойная проверка после получения блокировки
            if _agent_instance is None:
                # Создаем OpenAI клиент
                client = AsyncOpenAI()
                
                # Создаем систему промптов
                try:
                    from app.config import settings
                    redis_client = None
                    
                    # Пытаемся подключиться к Redis если настроен
                    if settings.REDIS_URL:
                        try:
                            redis_client = Redis.from_url(settings.redis_url_with_auth)
                            await redis_client.ping()
                            logger.info("✅ Подключен к Redis для системы промптов")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось подключиться к Redis: {e}")
                            redis_client = None
                    
                    # Создаем систему промптов
                    _prompt_system = await PromptSystemFactory.create_system(
                        redis_client=redis_client
                    )
                    
                    # Создаем агента с системой промптов
                    _agent_instance = MarkAgent(
                        client=client,
                        model=settings.OPENAI_MODEL,
                        temperature=settings.OPENAI_TEMPERATURE,
                        max_tokens=settings.OPENAI_MAX_TOKENS,
                        prompt_manager=_prompt_system["manager"],
                        use_dynamic_prompts=True
                    )
                    
                    logger.info("✅ Агент создан с динамической системой промптов")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка создания системы промптов: {e}")
                    logger.info("⚠️ Создаю агента без динамических промптов")
                    
                    # Fallback - создаем агента без системы промптов
                    _agent_instance = MarkAgent(
                        client=client,
                        model=settings.OPENAI_MODEL,
                        temperature=settings.OPENAI_TEMPERATURE,
                        max_tokens=settings.OPENAI_MAX_TOKENS,
                        use_dynamic_prompts=False
                    )
                
                # Регистрируем все инструменты
                all_tools = (MEMORY_TOOLS + ADVANCED_MEMORY_TOOLS + 
                            LEARNING_TOOLS + VECTOR_SEARCH_TOOLS + 
                            INTROSPECTION_TOOLS + FILE_TOOLS + TEST_TOOLS +
                            CODE_ANALYSIS_TOOLS + DEPENDENCY_TOOLS + SANDBOX_TOOLS +
                            CHANGE_TRACKER_TOOLS)
                
                for tool in all_tools:
                    definition = tool._openai_tool_definition
                    _agent_instance.register_tool(definition, tool)
                    
                logger.info(f"✅ Агент Марк инициализирован с {len(all_tools)} инструментами")
                
    return _agent_instance


async def enhanced_chat(
    question: str,
    chat_id: Optional[int] = None,
    mode: str = "chat",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Улучшенная функция чата на базе OpenAI Agents SDK
    
    Полная замена simple_chat с дополнительными возможностями:
    - Автоматический поиск контекста в памяти
    - Использование инструментов
    - Сохранение важной информации
    - Персонализация на основе user_id
    
    Args:
        question: Вопрос пользователя
        chat_id: ID чата
        mode: Режим работы (chat, task, analysis)
        user_id: ID пользователя
        session_id: Идентификатор сессии (если уже создан)
        
    Returns:
        Словарь с ответом и метаданными
    """
    try:
        import time
        t0 = time.time()
        logger.info(f"💬 Новый запрос: '{question[:50]}...' (user={user_id}, mode={mode})")
        
        # Получаем агента
        t_get_agent_s = time.time()
        agent = await get_agent()
        t_get_agent_e = time.time()
        get_agent_ms = int((t_get_agent_e - t_get_agent_s) * 1000)
        # Определяем session_id (используем chat_id как session_id, если задан)
        session_key: str
        if session_id:
            session_key = session_id
        elif chat_id is not None:
            session_key = str(chat_id)
        else:
            import uuid
            # Fallback: уникальная сессия на запрос, если не передана
            session_key = str(uuid.uuid4())
        
        # Подготавливаем контекст из памяти (4 компактных блока)
        context = []
        lowered = (question or "").strip().lower()
        is_smalltalk = False  # полностью отключаем smalltalk-фаст‑путь
        # Поддержка коротких подтверждений/уточнений: избегаем инструментов
        def _is_confirmation(text: str) -> bool:
            t = text.lower()
            return any(p in t for p in ["правильно?", "верно?", "так?", "помнишь", "согласен?", "верно", "ок?", "так верно" ])
        if _is_confirmation(lowered):
            is_smalltalk = True

        # Эвристика: использовать инструменты только по явной просьбе или при явной необходимости
        def _should_use_tools(text: str, mode: str) -> bool:
            t = text.lower()
            explicit = any(k in t for k in [
                "вызови", "запусти", "прочитай файл", "открой файл", "найди файл", "grep", "pytest", "тесты",
                "собери", "построй", "скачай", "список файлов", "прочитай код", "проанализируй код",
                "создай файл", "измени файл", "перепиши файл", "docker", "compose", "миграци", "endpoint",
                "curl", "запрос к api", "neo4j", "redis", "лог"
            ])
            if explicit:
                return True
            # В аналитических режимах разрешаем инструменты только если речь о коде/файлах/инфре
            if mode in ("task", "analysis"):
                return any(k in t for k in ["файл", "код", "директори", "папк", "тест", "лог", "база", "neo4j", "redis"])  # pragma: no cover
            # В обычном чате по умолчанию — без инструментов
            return False
        prep_breakdown: dict[str, int] = {}
        if not is_smalltalk:
            # 1) Краткий профиль пользователя
            try:
                user_summary = None
                t_prof_s = time.time()
                from core.memory.memory_manager import memory_manager
                user_items = await memory_manager.hybrid_search(query=f"user:{user_id}", user_id=user_id or "", k=3, use_hybrid=True)
                if user_items:
                    prefs = []
                    for it in user_items[:2]:
                        txt = it.get("text") or ""
                        if txt:
                            prefs.append(txt[:100])
                    if prefs:
                        user_summary = "; ".join(prefs)
                if user_summary:
                    context.append({"role": "system", "content": f"User Profile: {user_summary}"})
                prep_breakdown["user_profile_ms"] = int((time.time() - t_prof_s) * 1000)
            except Exception:
                pass

            # 2) Snapshot проекта
            from app.config import settings
            context.append({"role": "system", "content": f"Project: {settings.PROJECT_ID} env={settings.ENVIRONMENT}"})

            # 3) Граф-снимок (узлы/рёбра) с жёстким лимитом
            try:
                t_graph_s = time.time()
                graph_ctx = await _prepare_graph_context(session_key, user_id)
                if graph_ctx:
                    context.append({"role": "system", "content": graph_ctx})
                prep_breakdown["graph_ctx_ms"] = int((time.time() - t_graph_s) * 1000)
            except Exception:
                pass

            # 4) Рецепты и факты
            t_extra_s = time.time()
            extra_ctx = await _prepare_context(question, user_id, mode)
            context.extend(extra_ctx)
            prep_breakdown["extra_ctx_ms"] = int((time.time() - t_extra_s) * 1000)
        
        # Режим: smalltalk fast-path (короткие приветствия/простые фразы)
        use_tools_flag = (not is_smalltalk) and _should_use_tools(lowered, mode)
        # Для smalltalk добавляем лёгкую системную подсказку стилю ответа (через LLM)
        if is_smalltalk:
            context.append({
                "role": "system",
                "content": (
                    "Smalltalk-режим: Ответь дружелюбно и кратко (1–2 предложения). "
                    "Сделай ответ осмысленным: коротко отзеркаль отражение готовности помочь/текущего фокуса, "
                    "но не перечисляй внутренние шаги, метрики или статусы. "
                    "Избегай сухих отчётов. В конце можешь мягко уточнить следующий шаг пользователя."
                )
            })
        # Форс-флаги и прочие обходные пути — отключены, всё идёт через обычную ветку
        # Пер-режимные лимиты max_tokens и бюджетов LLM/tools
        from app.config import settings
        mode_to_limit = {
            "chat": settings.MAX_TOKENS_CHAT,
            "task": settings.MAX_TOKENS_TASK,
            "analysis": settings.MAX_TOKENS_ANALYSIS,
        }
        override_max = mode_to_limit.get(mode, settings.MAX_TOKENS_CHAT)
        # Бюджеты вызовов: для многошаговых режимов увеличиваем до 35
        llm_limit = settings.LLM_CALLS_PER_REQUEST_LIMIT
        tool_limit = settings.TOOL_CALLS_PER_REQUEST_LIMIT
        if mode in ("task", "analysis"):
            llm_limit = max(llm_limit, 35)
            tool_limit = max(tool_limit, 35)
        # Если инструменты не используем, сжимаем лимит LLM, чтобы не устраивать лишние раунды
        if not use_tools_flag:
            llm_limit = min(llm_limit, 2)
        
        # Вызываем агента
        t1 = time.time()
        result = await agent.chat(
            message=question,
            user_id=user_id,
            chat_id=session_key,
            context=context,
            use_tools=use_tools_flag,
            override_max_tokens=override_max,
            override_llm_calls_limit=llm_limit,
            override_tool_calls_limit=tool_limit
        )
        t2 = time.time()

        # Обрабатываем результат
        response = await _process_result(result, question, user_id, session_key)
        # Жёсткий fallback при пустом контенте: построить краткий ответ без LLM
        if not (response.get("content") or "").strip():
            try:
                fallback_text = await _build_fallback_answer(question, user_id, session_key)
            except Exception:
                fallback_text = None
            response["content"] = fallback_text or (
                "Извини, финальный ответ не сформировался. Я повторю поиск и покажу найденные факты/связи. "
                "Если нужно — могу сразу создать или обновить графовые узлы/рёбра."
            )
            response.setdefault("metadata", {})
            response["metadata"]["fallback_used"] = True

        # Персист сессии и сообщений в Graphiti
        try:
            await graphiti_adapter.create_session(session_id=session_key, user_id=user_id)
            await graphiti_adapter.create_message(
                session_id=session_key,
                role="user",
                text=question,
                metadata={"user_id": user_id, "mode": mode, "session_id": session_key}
            )
            await graphiti_adapter.create_message(
                session_id=session_key,
                role="assistant",
                text=response.get("content", ""),
                metadata={
                    "user_id": user_id,
                    "mode": mode,
                    "has_tools": bool(response.get("tool_calls")),
                    "session_id": session_key,
                }
            )
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить чат-сообщения в Graphiti: {e}")
        t3 = time.time()

        # Добавляем дополнительные метаданные
        response.setdefault("metadata", {})
        response["metadata"].update({
            "mode": mode,
            "context_used": len(context) > 0,
            "memory_searched": True,
            "tools_available": len(agent.tools),
            "timings_app": {
                "prepare_ms": int((t1 - t0) * 1000),
                "agent_ms": int((t2 - t1) * 1000),
                "persist_ms": int((t3 - t2) * 1000),
                "total_ms": int((t3 - t0) * 1000),
                "get_agent_ms": get_agent_ms,
                "breakdown": prep_breakdown,
            },
            "session_id": session_key,
        })

        return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка в enhanced_chat: {str(e)}")
        return {
            "content": f"Произошла ошибка при обработке запроса: {str(e)}",
            "error": True,
            "metadata": {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        }


async def _prepare_context(question: str, user_id: Optional[str], mode: str = "chat") -> List[Dict[str, str]]:
    """Подготовка контекста из памяти"""
    context = []
    
    try:
        # Поиск релевантной информации
        if question.strip():
            # Сначала ищем по вопросу
            limit = 2 if mode == "chat" else 3
            search_results = await memory_manager.search_episodes(question, limit=limit)
            
            if search_results.get("items"):
                # Добавляем найденную информацию в контекст
                memory_info = "Информация из памяти:\n"
                for item in search_results["items"]:
                    memory_info += f"- {item.get('text', '')}\n"
                
                context.append({
                    "role": "system",
                    "content": f"Используй эту информацию из памяти для персонализации ответа:\n{memory_info}"
                })
                logger.info(f"📚 Добавлено {len(search_results['items'])} элементов из памяти")
        
        # Получаем контекст пользователя если есть user_id
        if user_id:
            k = 3 if mode == "chat" else 5
            user_results = await memory_manager.hybrid_search(
                query=f"user:{user_id}",
                user_id=user_id,
                k=k,
                use_hybrid=True
            )
            
            if user_results:
                user_info = "Информация о пользователе:\n"
                top = 2 if mode == "chat" else 3
                for item in user_results[:top]:  # Берем топ-N
                    user_info += f"- {item.get('text', '')}\n"
                    
                context.append({
                    "role": "system", 
                    "content": f"Контекст пользователя:\n{user_info}"
                })
                logger.info(f"👤 Добавлен контекст пользователя")
                
    except Exception as e:
        logger.error(f"⚠️ Ошибка при подготовке контекста: {str(e)}")
        
    return context


async def _process_result(
    result: Dict[str, Any],
    question: str,
    user_id: Optional[str],
    session_id: Optional[str],
) -> Dict[str, Any]:
    """Обработка результата от агента"""
    
    # Если были вызваны инструменты памяти, логируем
    if result.get("tool_calls"):
        for tool_call in result["tool_calls"]:
            logger.info(f"🔧 Использован инструмент: {tool_call['name']}")
    
    # Автоматически сохраняем диалог в память
    try:
        dialog_text = f"Вопрос: {question}\nОтвет: {result.get('content', '')}"
        metadata = {
            "type": "dialog",
            "user_id": user_id,
            # Храним timestamp как целое число для совместимости с моделью
            "timestamp": int(datetime.now().timestamp()),
            "has_tools": bool(result.get("tool_calls")),
            "session_id": session_id,
        }
        
        save_result = await memory_manager.save(dialog_text, metadata)
        if save_result.get("success"):
            logger.info(f"💾 Диалог сохранен в память: {save_result.get('id')}")
    except Exception as e:
        logger.error(f"⚠️ Не удалось сохранить диалог: {str(e)}")
    
    return result

async def _build_fallback_answer(question: str, user_id: Optional[str], session_id: str) -> Optional[str]:
    """Собрать минимальный осмысленный ответ без LLM: последние диалоги и несколько связей графа."""
    try:
        parts: list[str] = []
        # Последние диалоги пользователя из Graphiti
        try:
            lst = await graphiti_adapter.list_episodes(limit=20)
            items = []
            for n in lst.get("nodes", []):
                md = n.get("properties", {})
                if isinstance(md, dict) and md.get("type") == "dialog" and (md.get("user_id") == user_id):
                    items.append(md)
            items = sorted(items, key=lambda x: x.get("timestamp", 0))[-3:]
            if items:
                parts.append("Последние диалоги:")
                for it in items:
                    txt = (it.get("msg") or "")
                    if not txt:
                        # у нас диалог сохранялся в create_episode(text=...)
                        txt = (it.get("text") or "")
                    preview = (txt or "").splitlines()[0][:140]
                    parts.append(f"- {preview}")
        except Exception:
            pass
        # Короткий граф‑снимок
        try:
            edge_lines: list[str] = []
            if user_id:
                pid = f"person:{user_id}"
                e = await graphiti_adapter.list_edges(source_id=pid, limit=5)
                for ed in e.get("edges", [])[:5]:
                    edge_lines.append(f"Person→{ed.get('type')}→{ed.get('target_id')}")
            se = await graphiti_adapter.list_edges(source_id=session_id, limit=5)
            for ed in se.get("edges", [])[:5]:
                edge_lines.append(f"Session→{ed.get('type')}→{ed.get('target_id')}")
            if edge_lines:
                parts.append("Граф (кратко):")
                parts.extend([f"- {ln}" for ln in edge_lines[:6]])
        except Exception:
            pass
        if parts:
            head = "Короткий ответ без LLM (fallback)\n"
            return head + "\n".join(parts)
        return None
    except Exception:
        return None
async def _prepare_graph_context(session_id: str, user_id: Optional[str]) -> Optional[str]:
    """Собирает компактный граф-снимок по активной сессии и пользователю.
    Формат: список кратких связей с лимитами, чтобы не раздувать промпт.
    """
    try:
        lines = []
        max_edges = 6
        # Связи сессии
        try:
            se = await graphiti_adapter.list_edges(source_id=session_id, limit=max_edges)
            for e in se.get("edges", [])[:max_edges]:
                lines.append(f"Session→{e.get('type')}→{e.get('target_id')}")
        except Exception:
            pass
        # Связи пользователя (Person)
        if user_id:
            try:
                pid = f"person:{user_id}"
                pe = await graphiti_adapter.list_edges(source_id=pid, limit=max_edges)
                for e in pe.get("edges", [])[:max_edges]:
                    lines.append(f"Person→{e.get('type')}→{e.get('target_id')}")
            except Exception:
                pass
        if not lines:
            return None
        # Компактный блок
        head = "Graph snapshot (trimmed):\n"
        body = "\n".join(f"- {ln}" for ln in lines[:max_edges])
        return head + body
    except Exception:
        return None


async def shutdown_agent():
    """Корректное завершение работы агента и системы промптов"""
    global _agent_instance, _prompt_system
    
    if _prompt_system:
        try:
            await PromptSystemFactory.shutdown_system(_prompt_system)
            logger.info("✅ Система промптов остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки системы промптов: {e}")
        _prompt_system = None
    
    _agent_instance = None
    logger.info("✅ Агент остановлен")


# Функция обратной совместимости с simple_chat
async def simple_chat(
    question: str,
    chat_id: Optional[int] = None,
    mode: str = "chat",
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Обратная совместимость с simple_chat
    
    Эта функция сохранена для совместимости с существующим кодом.
    Внутри использует новый enhanced_chat.
    """
    logger.info("🔄 Вызов simple_chat перенаправлен на enhanced_chat")
    
    result = await enhanced_chat(question, chat_id, mode, user_id)
    
    # Преобразуем результат в старый формат если нужно
    if "content" in result:
        return {
            "answer": result["content"],  # Изменено с "result" на "answer" для совместимости
            "result": result["content"],  # Оставляем и result для обратной совместимости
            "metadata": result.get("metadata", {}),
            "context_used": result.get("metadata", {}).get("context_used", False)
        }
    
    return result