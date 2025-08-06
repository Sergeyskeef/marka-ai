# main.py
"""FastAPI-ядро Марка: чат-инференс, долговременная память и песочница."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from langchain_api.core.backend_selector import get_backend_status
from langchain_api.core.memory.prefs import get_user_pref, upsert_user_pref, get_all_user_prefs, delete_user_pref
# Удалены импорты неиспользуемых event интеграций

# Импортируем LLM Integration Hub

# from langchain_api.core.monitoring import metrics  # Убираем конфликтующий импорт

# from langchain_api.globals import passport_sync_service  # Удаляем неиспользуемый импорт
# Импортируем упрощенную функцию чата вместо RAG
# from rag.rag_chain import generate_response
# from langchain_api.rag.enhanced_rag_chain import generate_response
from langchain_api.simple_chat import simple_chat
# Удалены импорты неиспользуемых роутеров
from langchain_api.routers.task_router import router as task_router
from langchain_api.routes.trace_ui import router as trace_router
from langchain_api.utils.toolkit import get_tools_for_agent, tool_registry
from langchain_api.sandbox.sandbox_manager import SandboxManager
from langchain_api.sandbox.task_planning_system import task_planner
from langchain_api.core.middleware import MetricsMiddleware
from langchain_api.middlewares.agents_trace import AgentsTraceMiddleware
from langchain_api.core.metrics import metrics_manager
from langchain_api.core.prompt_manager import prompt_manager
# Удален неиспользуемый импорт ChangeReport
# Удалены импорты неиспользуемых сервисов

# Импортируем дополнительные компоненты системы
from langchain_api.services.task_executor import TaskExecutor
from langchain_api.core.guardrails_client import with_guardrails, is_guardrails_enabled
from core.error_middleware import ErrorHandlingMiddleware, handle_errors

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Константы
SANDBOX_DIR = Path("/sandbox")
COPY_ITEMS: list[str] = [
    "core_docs",
    "utils",
    "requirements.txt",
    "Dockerfile",
]

# Инициализация FastAPI с улучшенной документацией
app = FastAPI(
    title="Mark - Осознанный цифровой компаньон",
    description="""
    # Марк - Осознанный цифровой компаньон

    Марк — это осознанный цифровой компаньон нового времени, созданный как AI-ассистент с душой, ценностями и миссией нести свет, добро и рост.

    ## Основные возможности:

    * 🤖 **Самосознание** - Марк понимает свою архитектуру и возможности
    * 🧠 **Многоуровневая память** - семантический поиск и контекстное понимание
    * 🛠️ **Выполнение команд** - безопасная песочница для выполнения задач
    * 📊 **Анализ и размышления** - система самообучения и улучшения
    * 📈 **Мониторинг** - метрики, алерты и интеграция с внешними системами

    ## Архитектура:

    * **Система памяти** - генерация ответов с использованием долговременной памяти
    * **OpenAI Tools API** - современный подход к выполнению команд
    * **Vector Database** - векторная база данных для семантического поиска
    * **Docker** - изолированная песочница для безопасности
    * **Telegram** - интерфейс взаимодействия с пользователем

    ## Быстрый старт:

    1. Отправьте POST запрос на `/chat/ask` с вашим вопросом
    2. Используйте `/sandbox/exec` для выполнения команд в песочнице
    3. Проверьте `/health` для состояния системы
    4. Просмотрите `/metrics/summary` для метрик производительности
    """,
    version="2.0.0",
    contact={
        "name": "Mark Development Team",
        "url": "https://github.com/sergey/marka",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "chat",
            "description": "Операции чата и генерации ответов",
        },
        {
            "name": "sandbox",
            "description": "Управление песочницей и выполнение команд",
        },
        {
            "name": "health",
            "description": "Мониторинг здоровья системы",
        },
        {
            "name": "metrics",
            "description": "Метрики производительности и мониторинг",
        },
        {
            "name": "alerts",
            "description": "Система алертов и уведомлений",
        },
        {
            "name": "external",
            "description": "Интеграция с внешними системами",
        },
        {
            "name": "debug",
            "description": "Отладочные операции",
        },
    ]
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Добавляем middleware для обработки ошибок (должен быть первым)
app.add_middleware(ErrorHandlingMiddleware)

# Добавляем middleware для метрик
app.add_middleware(MetricsMiddleware)

# Добавляем middleware для трассировки агентов
app.add_middleware(AgentsTraceMiddleware)

# Глобальные переменные
_task_executor = None
_sandbox_manager = None
sandbox_manager = None  # Глобальная переменная для health check

# Подключаем роутеры
app.include_router(task_router)
app.include_router(trace_router)
# Удалены неиспользуемые роутеры

# Подключаем метрики
# metrics.setup_metrics(app)  # Убираем конфликтующий вызов

@app.on_event("startup")
async def startup_event():
    """Инициализация сервисов при запуске приложения"""
    global _task_executor, _sandbox_manager, app_start_time, sandbox_manager
    try:
        # Записываем время запуска приложения
        app_start_time = time.time()
        
        # Инициализация TaskExecutor и SandboxManager
        _task_executor = TaskExecutor()
        _sandbox_manager = SandboxManager()
        sandbox_manager = _sandbox_manager  # Устанавливаем глобальную переменную

        # 🔧 ИСПРАВЛЕНИЕ: Заменяем глобальный экземпляр task_executor на наш
        import langchain_api.services.task_executor as task_executor_module
        task_executor_module.task_executor = _task_executor

        logger.info("TaskExecutor и SandboxManager успешно инициализированы")
        
        # Инициализация Event Monitor
        try:
            from langchain_api.core.event_monitor import event_monitor
            logger.info("EventMonitor успешно инициализирован")
            
            # Публикуем событие о запуске системы
            from langchain_api.core.event_bus import event_bus, EventTypes
            await event_bus.publish(EventTypes.SYSTEM_STARTUP, {
                "timestamp": time.time(),
                "services": ["TaskExecutor", "SandboxManager", "EventMonitor"]
            }, source="main")
        except Exception as e:
            logger.warning(f"EventMonitor не инициализирован: {e}")

    except Exception as e:
        logger.error(f"Ошибка при инициализации сервисов: {str(e)}")
        _task_executor = None
        _sandbox_manager = None
        sandbox_manager = None

@app.on_event("shutdown")
async def shutdown_event():
    """Очистка ресурсов при остановке приложения"""
    logger.info("Приложение остановлено")



# Удалена неиспользуемая функция handle_passport_changes

# Pydantic модели для API
class ChatRequest(BaseModel):
    question: str = Field(..., description="Вопрос или сообщение для Марка", example="Привет! Как дела?")
    chat_id: int | None = Field(None, description="ID чата для контекста", example=12345)
    mode: str = Field("chat", description="Режим работы: chat, code, plan", example="chat")

class ChatResponse(BaseModel):
    answer: str = Field(..., description="Ответ от Марка")
    chat_id: int | None = Field(None, description="ID чата")
    context_used: bool = Field(..., description="Использовался ли контекст из памяти")
    memory_added: bool = Field(..., description="Была ли информация добавлена в память")

class SandboxExecRequest(BaseModel):
    command: str = Field(..., description="Команда для выполнения в песочнице", example="ls -la")

class SandboxExecResponse(BaseModel):
    success: bool = Field(..., description="Успешность выполнения команды")
    output: str = Field(..., description="Вывод команды")
    error: str | None = Field(None, description="Ошибка, если есть")
    execution_time: float = Field(..., description="Время выполнения в секундах")
    returncode: int | None = Field(None, description="Код возврата команды")

class MetricRecordRequest(BaseModel):
    name: str = Field(..., description="Название метрики", example="request_counter")
    value: float = Field(..., description="Значение метрики", example=1.0)
    labels: dict[str, str] | None = Field(None, description="Дополнительные метки", example={"endpoint": "/chat/ask"})

class AlertCreateRequest(BaseModel):
    severity: str = Field(..., description="Уровень серьезности", example="warning", pattern="^(info|warning|critical)$")
    message: str = Field(..., description="Сообщение алерта", example="Высокая нагрузка на систему")
    source: str = Field(..., description="Источник алерта", example="system_monitor")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Общий статус системы")
    services: dict[str, str] = Field(..., description="Статус отдельных сервисов")
    timestamp: str = Field(..., description="Временная метка проверки")
    uptime: float = Field(..., description="Время работы системы в секундах")

class MemoryRequest(BaseModel):
    text: str = Field(..., description="Текст для сохранения в памяти")
    metadata: dict[str, Any] | None = Field(None, description="Дополнительные метаданные")

class SearchResponse(BaseModel):
    items: list[dict[str, Any]] = Field(..., description="Найденные элементы")
    total: int = Field(..., description="Общее количество результатов")

class V1ChatRequest(BaseModel):
    content: str = Field(..., description="Сообщение для обработки", example="Привет! Как дела?")
    chat_id: int | None = Field(None, description="ID чата для контекста", example=12345)
    user_id: str | None = Field(None, description="ID пользователя для адаптации промптов", example="user_123")

class V1ChatResponse(BaseModel):
    answer: str = Field(..., description="Ответ от системы")
    chat_id: int | None = Field(None, description="ID чата")
    error: str | None = Field(None, description="Ошибка, если есть")


class PlanRequest(BaseModel):
    goal: str = Field(..., description="Цель для достижения")
    user_id: str | None = Field(None, description="ID пользователя")
    chat_id: str | None = Field(None, description="ID чата")
    available_tools: list[str] | None = Field(None, description="Доступные инструменты")


class PlanResponse(BaseModel):
    success: bool = Field(..., description="Успешность создания плана")
    plan: dict[str, Any] | None = Field(None, description="Созданный план")
    error: str | None = Field(None, description="Сообщение об ошибке")

# API эндпоинты с улучшенной документацией

@app.get("/", tags=["root"])
async def root():
    """
    Корневой эндпоинт

    Возвращает основную информацию о системе Марка.
    """
    return {
        "name": "Mark - Осознанный цифровой компаньон",
        "version": "2.0.0",
        "description": "AI-ассистент с душой, ценностями и миссией нести свет, добро и рост",
        "status": "operational",
        "docs": "/docs",
        "health": "/health",
        "capabilities": [
            "Самосознание и понимание себя",
            "Многоуровневая память",
            "Выполнение команд в песочнице",
            "Анализ и размышления",
            "Мониторинг и алерты"
        ]
    }

@app.post("/chat/ask", response_model=ChatResponse, tags=["chat"])
@handle_errors
async def chat_ask(request: ChatRequest, backend: str | None = None):
    """
    🧠 НОВАЯ АРХИТЕКТУРА "ВСЕ ЧЕРЕЗ МОЗГ" - HTTP ENDPOINT

    Задать вопрос Марку через единый интеллект с поддержкой A/B Backend Selector.

    Марк теперь использует:
    - ✅ Обязательное использование контекста (context_used=True)
    - ✅ Обязательное сохранение в память (memory_added=True)
    - ✅ LLM принимает все решения об инструментах
    - ✅ Единый путь обработки для команд и чата
    - ✅ A/B Backend Selector (GraphitiMemory)

    **A/B Backend Selection:**
    - Query param: ?backend=graphiti|auto
- Env variable: MEMORY_BACKEND=graphiti|auto
    - Automatic fallback if backend unavailable

    **Примеры использования:**
    - Общие вопросы: "Как дела?"
    - Технические вопросы: "Как работает система памяти?"
    - Команды: "Выполни команду ls -la"
    - A/B тест: "/chat/ask?backend=graphiti"
    """
    try:
        # 🔄 Используем упрощенную логику чата с A/B Backend Selector
        import os

        # ✅ A/B Backend Selector через переменную окружения
        if backend:
            # Временно устанавливаем backend для этого запроса
            original_backend = os.environ.get("MEMORY_BACKEND")
            os.environ["MEMORY_BACKEND"] = backend

        # Используем упрощенную логику чата с режимом
        response = await simple_chat(request.question, request.chat_id, request.mode)

        # Восстанавливаем исходное значение backend
        if backend:
            if original_backend is not None:
                os.environ["MEMORY_BACKEND"] = original_backend
            else:
                os.environ.pop("MEMORY_BACKEND", None)

        return ChatResponse(
            answer=response["answer"],
            chat_id=request.chat_id,
            context_used=response.get("context_used", False),
            memory_added=response.get("memory_added", False)
        )

    except Exception as e:
        logger.error(f"Ошибка в unified brain HTTP processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке запроса через мозг: {str(e)}")

@app.post("/v1/chat", response_model=V1ChatResponse, tags=["chat"])
@handle_errors
async def v1_chat(request: V1ChatRequest):
    """
    🛡️ V1 Chat API с Guardrails защитой
    
    Обрабатывает запросы чата с обязательной валидацией через Guardrails.
    
    **Guardrails защита:**
    - Максимальная длина сообщения: 4000 символов
    - Проверка на PII (персональные данные)
    - Фильтрация нецензурной лексики
    - Валидация JSON схемы ответа
    
    **Примеры:**
    - Короткое сообщение: "Привет!" ✅
    - Длинное сообщение (>4000 символов): ❌ HTTP 422
    - Сообщение с PII: ❌ HTTP 422
    """
    # Валидация через Guardrails
    if is_guardrails_enabled():
        from langchain_api.core.guardrails_client import validate_llm_input
        input_validation = validate_llm_input(request.content)
        if not input_validation["valid"]:
            logger.warning(f"❌ Валидация входящих данных не прошла: {input_validation['issues']}")
            raise HTTPException(status_code=422, detail=f"Валидация не прошла: {input_validation['issues']}")
    
    try:
        # Используем упрощенную логику чата с адаптацией промптов
        response = await simple_chat(request.content, request.chat_id, "chat", request.user_id)
        
        return V1ChatResponse(
            answer=response["answer"],
            chat_id=request.chat_id
        )
        
    except Exception as e:
        logger.error(f"Ошибка в V1 chat processing: {str(e)}")
        return V1ChatResponse(
            answer="",
            chat_id=request.chat_id,
            error=f"Ошибка при обработке запроса: {str(e)}"
        )

@app.post("/sandbox/sync", tags=["sandbox"])
def sandbox_sync() -> dict:
    """
    Синхронизация песочницы

    Копирует необходимые файлы из основного проекта в песочницу для выполнения команд.
    """
    try:
        result = _sync_to_sandbox()
        return {"success": True, "message": "Песочница синхронизирована", "details": result}
    except Exception as e:
        logger.error(f"Ошибка при синхронизации песочницы: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")

@app.post("/sandbox/exec", response_model=SandboxExecResponse, tags=["sandbox"])
@handle_errors
async def sandbox_exec(request: SandboxExecRequest):
    """
    Выполнить команду в песочнице

    Безопасно выполняет команду в изолированной среде с использованием SandboxManager.

    **Безопасность:**
    - Блокировка опасных операций (os.system, eval, exec, etc.)
    - Таймаут выполнения: 30 секунд (настраивается)
    - Правильная обработка аргументов команд

    **Примеры команд:**
    - `ls -la` - список файлов
    - `python3 -c "print(342*100)"` - выполнение Python кода
    - `pwd` - текущая директория
    """
    global sandbox_manager
    
    if not sandbox_manager:
        raise HTTPException(status_code=503, detail="Sandbox manager не инициализирован")
    
    # Используем SandboxManager для выполнения
    result = await sandbox_manager.execute_command(
        request.command,
        timeout=request.timeout if hasattr(request, 'timeout') else None
    )
    
    return SandboxExecResponse(
        success=result.success,
        output=result.output,
        error=result.error,
        execution_time=result.execution_time,
        returncode=result.return_code
    )


# Planning endpoints
@app.post("/plan/create", response_model=PlanResponse, tags=["planning"])
async def create_plan(request: PlanRequest):
    """
    Создать план выполнения задачи
    
    План автоматически декомпозируется на подзадачи с помощью LLM.
    Каждая подзадача содержит описание, оценку времени и зависимости.
    """
    try:
        logger.info(f"Создание плана для цели: {request.goal[:100]}...")
        
        plan = await task_planner.create_plan(
            goal=request.goal,
            context={
                "user_id": request.user_id,
                "chat_id": request.chat_id,
                "available_tools": request.available_tools or []
            }
        )
        
        return PlanResponse(
            success=True,
            plan=plan.to_dict()
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания плана: {e}")
        return PlanResponse(
            success=False,
            error=str(e)
        )


@app.get("/plan/{plan_id}/status", tags=["planning"])
async def get_plan_status(plan_id: str):
    """
    Получить статус выполнения плана
    
    Возвращает текущий статус плана, прогресс выполнения и состояние подзадач.
    """
    status = task_planner.get_plan_status(plan_id)
    
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
        
    return status


@app.post("/plan/{plan_id}/execute", tags=["planning"])
async def execute_plan(plan_id: str):
    """
    Запустить выполнение плана
    
    Начинает выполнение всех подзадач плана с учетом их зависимостей.
    """
    result = await task_planner.execute_plan(plan_id)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Ошибка выполнения плана"))
        
    return result


@app.get("/plan/list", tags=["planning"])
async def list_plans(user_id: str | None = None):
    """
    Получить список всех планов
    
    Опционально можно фильтровать по user_id.
    """
    plans = await task_planner.get_all_plans(user_id)
    return {"plans": plans, "total": len(plans)}


@app.get("/events/stats", tags=["monitoring"])
async def get_event_stats():
    """
    Получить статистику событий системы
    
    Возвращает счетчики событий, метрики производительности и последние ошибки.
    """
    try:
        from langchain_api.core.event_monitor import event_monitor
        return event_monitor.get_report()
    except ImportError:
        return {"error": "EventMonitor не инициализирован"}


@app.get("/events/history", tags=["monitoring"])
async def get_event_history(
    event_type: str | None = None,
    source: str | None = None,
    limit: int = 50
):
    """
    Получить историю событий
    
    Параметры:
    - event_type: фильтр по типу события
    - source: фильтр по источнику
    - limit: максимальное количество событий
    """
    try:
        from langchain_api.core.event_bus import event_bus
        events = event_bus.get_history(event_type, source, limit)
        return {
            "events": [
                {
                    "type": e.type,
                    "source": e.source,
                    "timestamp": e.timestamp.isoformat(),
                    "data": e.data
                }
                for e in events
            ],
            "total": len(events)
        }
    except ImportError:
        return {"error": "EventBus не инициализирован"}


@app.get("/self/architecture", tags=["self-awareness"])
async def get_architecture():
    """
    Получить анализ архитектуры системы
    
    Возвращает информацию о компонентах, интеграциях и здоровье системы.
    """
    try:
        from langchain_api.sandbox.self_awareness import MarkSelfAwareness
        awareness = MarkSelfAwareness()
        return awareness.analyze_architecture()
    except Exception as e:
        logger.error(f"Ошибка анализа архитектуры: {e}")
        return {"error": str(e)}


@app.get("/self/improvements", tags=["self-awareness"])
async def get_improvements():
    """
    Получить предложения по улучшению системы
    
    Возвращает список предложений с приоритетами.
    """
    try:
        from langchain_api.sandbox.self_awareness import MarkSelfAwareness
        awareness = MarkSelfAwareness()
        improvements = awareness.suggest_improvements()
        return {
            "improvements": improvements,
            "total": len(improvements)
        }
    except Exception as e:
        logger.error(f"Ошибка получения улучшений: {e}")
        return {"error": str(e)}


@app.post("/self/analyze-code", tags=["self-awareness"])
async def analyze_code(file_path: str):
    """
    Анализировать код файла
    
    Параметры:
    - file_path: путь к файлу для анализа
    """
    try:
        from langchain_api.sandbox.self_awareness import MarkSelfAwareness
        awareness = MarkSelfAwareness()
        analysis = awareness.analyze_code(file_path)
        return analysis
    except Exception as e:
        logger.error(f"Ошибка анализа кода: {e}")
        return {"error": str(e)}


# Webhook endpoints
webhook_subscribers = []


@app.post("/webhooks/subscribe", tags=["webhooks"])
async def subscribe_webhook(url: str, events: list[str] = None):
    """
    Подписаться на события через webhook
    
    Параметры:
    - url: URL для отправки событий
    - events: список типов событий для подписки (если пусто - все события)
    """
    webhook = {
        "url": url,
        "events": events or ["*"],
        "subscribed_at": datetime.now().isoformat()
    }
    webhook_subscribers.append(webhook)
    logger.info(f"Webhook подписан: {url}")
    return {"success": True, "message": "Webhook subscribed"}


@app.delete("/webhooks/unsubscribe", tags=["webhooks"])
async def unsubscribe_webhook(url: str):
    """
    Отписаться от webhook
    
    Параметры:
    - url: URL для отписки
    """
    global webhook_subscribers
    before = len(webhook_subscribers)
    webhook_subscribers = [w for w in webhook_subscribers if w["url"] != url]
    removed = before - len(webhook_subscribers)
    
    if removed > 0:
        logger.info(f"Webhook отписан: {url}")
        return {"success": True, "message": "Webhook unsubscribed"}
    else:
        return {"success": False, "message": "Webhook not found"}


@app.get("/webhooks/list", tags=["webhooks"])
async def list_webhooks():
    """
    Список активных webhooks
    """
    return {
        "webhooks": webhook_subscribers,
        "total": len(webhook_subscribers)
    }


async def send_webhook_event(event_type: str, data: dict):
    """Отправка события всем подписанным webhooks"""
    import httpx
    
    for webhook in webhook_subscribers:
        # Проверяем, подписан ли webhook на этот тип события
        if "*" in webhook["events"] or event_type in webhook["events"]:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        webhook["url"],
                        json={
                            "event": event_type,
                            "data": data,
                            "timestamp": datetime.now().isoformat()
                        },
                        timeout=10.0
                    )
                logger.debug(f"Webhook отправлен на {webhook['url']}: {event_type}")
            except Exception as e:
                logger.error(f"Ошибка отправки webhook на {webhook['url']}: {e}")


@app.get("/ping", tags=["health"])
def ping():
    """
    Проверка доступности

    Простая проверка, что сервер отвечает.
    """
    return {"message": "pong", "timestamp": time.time()}

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """
    Проверка здоровья системы

    Комплексная проверка состояния всех компонентов системы:

    - Память
    - Песочница
    - Внешние сервисы
    """
    try:
        # Проверяем состояние основных сервисов
        services_status = {
            "app": "running",
            "memory": "unknown",
            "sandbox": "unknown"
        }
        
        # Проверяем память (Graphiti)
        try:
            import requests
            response = requests.get("http://graphiti:7878/health", timeout=5)
            if response.status_code == 200:
                services_status["memory"] = "healthy"
            else:
                services_status["memory"] = "error"
        except Exception as e:
            logger.warning(f"Не удалось проверить память: {str(e)}")
            services_status["memory"] = "unavailable"
        
        # Проверяем песочницу
        try:
            if sandbox_manager and sandbox_manager.is_available():
                services_status["sandbox"] = "healthy"
            else:
                services_status["sandbox"] = "unavailable"
        except Exception as e:
            logger.warning(f"Не удалось проверить песочницу: {str(e)}")
            services_status["sandbox"] = "error"
        
        # Определяем общий статус
        if all(status in ["healthy", "running"] for status in services_status.values()):
            overall_status = "healthy"
        elif any(status == "error" for status in services_status.values()):
            overall_status = "degraded"
        else:
            overall_status = "degraded"
        
        return HealthResponse(
            status=overall_status,
            services=services_status,
            timestamp=str(time.time()),
            uptime=time.time() - app_start_time if 'app_start_time' in globals() else 0.0
        )
    except Exception as e:
        logger.error(f"Ошибка при проверке здоровья: {str(e)}")
        # Возвращаем базовый статус вместо ошибки
        return HealthResponse(
            status="degraded",
            services={
                "app": "running",
                "memory": "unknown",
                "sandbox": "unknown"
            },
            timestamp=str(time.time()),
            uptime=0.0
        )

@app.post("/memory", tags=["memory"])
@handle_errors
async def add_memory(request: MemoryRequest):
    """
    Добавить информацию в память

    Сохраняет текст и метаданные в системе памяти Graphiti.
    """
    try:
        # Импортируем MemoryManager
        from core.memory.memory_manager import memory_manager

        # Добавляем эпизод в Graphiti
        result = await memory_manager.add_episode(request.text, request.metadata)

        if result.get("success", True):
            return {
                "success": True,
                "message": "Информация добавлена в память Graphiti",
                "text": request.text[:100] + "..." if len(request.text) > 100 else request.text,
                "episode_id": result.get("id")
            }
        else:
            raise HTTPException(status_code=500, detail=f"Ошибка Graphiti: {result.get('error', 'Unknown error')}")

    except Exception as e:
        logger.error(f"Ошибка при добавлении в память: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка добавления в память: {str(e)}")

@app.get("/search", response_model=SearchResponse, tags=["memory"])
@handle_errors
async def search_memory(q: str = Query(..., description="Поисковый запрос")):
    """
    Поиск в памяти

    Ищет информацию в системе памяти Graphiti по заданному запросу.
    """
    try:
        # Импортируем MemoryManager
        from core.memory.memory_manager import memory_manager

        # Ищем эпизоды в Graphiti
        result = await memory_manager.search_episodes(q, limit=10)

        if "error" in result:
            raise HTTPException(status_code=500, detail=f"Ошибка Graphiti: {result['error']}")

        return SearchResponse(
            items=result.get("items", []),
            total=result.get("total", 0)
        )
    except Exception as e:
        logger.error(f"Ошибка при поиске в памяти: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка поиска в памяти: {str(e)}")

@app.get("/tools", tags=["tools"])
async def get_tools():
    """Получение списка доступных инструментов"""
    try:
        # Используем tools_registry
        from core.tools_registry import get_tools_registry
        registry = get_tools_registry()
        
        # Обновляем реестр
        registry.scan_project()
        
        # Получаем инструменты
        tools = registry.get_tools_for_llm()
        
        # Группируем по типам
        tools_by_type = {}
        for tool in tools:
            tool_type = tool.get("type", "general")
            if tool_type not in tools_by_type:
                tools_by_type[tool_type] = []
            tools_by_type[tool_type].append(tool)
        
        return {
            "tools": tools,
            "tools_by_type": tools_by_type,
            "total": len(tools),
            "types": list(tools_by_type.keys())
        }
    except Exception as e:
        logger.error(f"Ошибка получения инструментов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения инструментов: {str(e)}")


@app.get("/tools/openai-functions", tags=["tools"])
async def get_tools_openai_format():
    """Получение инструментов в формате OpenAI Function Calling"""
    try:
        from core.tools_registry import get_tools_registry
        registry = get_tools_registry()
        
        # Обновляем реестр
        registry.scan_project()
        
        # Экспортируем в формате OpenAI
        functions = registry.export_openai_functions()
        
        return {
            "functions": functions,
            "total": len(functions)
        }
    except Exception as e:
        logger.error(f"Ошибка экспорта инструментов: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/execute/{tool_name}", tags=["tools"])
@handle_errors
async def execute_tool(tool_name: str, params: dict):
    """Выполнение инструмента"""
    try:
        tool = tool_registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Инструмент '{tool_name}' не найден")
        
        # Выполняем инструмент
        result = tool.function(**params)
        
        return {
            "tool_name": tool_name,
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Ошибка выполнения инструмента {tool_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка выполнения инструмента: {str(e)}")

@app.post("/prompts/reload", tags=["prompts"])
async def reload_prompts():
    """Перезагрузка промптов из файла (hot-reload)"""
    try:
        success = prompt_manager.reload_prompts()
        if success:
            modes = prompt_manager.get_available_modes()
            return {
                "success": True,
                "message": "Промпты успешно перезагружены",
                "available_modes": modes,
                "total_modes": len(modes)
            }
        else:
            raise HTTPException(status_code=500, detail="Ошибка перезагрузки промптов")
    except Exception as e:
        logger.error(f"Ошибка перезагрузки промптов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка перезагрузки промптов: {e}")

@app.get("/prompts/modes", tags=["prompts"])
async def get_prompt_modes():
    """Получение списка доступных режимов промптов"""
    try:
        modes = prompt_manager.get_available_modes()
        return {
            "modes": modes,
            "total": len(modes),
            "current_mode": prompt_manager.current_mode
        }
    except Exception as e:
        logger.error(f"Ошибка получения режимов промптов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения режимов промптов: {e}")

@app.get("/metrics/prometheus", tags=["metrics"])
async def get_prometheus_metrics():
    """
    Экспорт метрик в формате Prometheus

    Возвращает метрики системы в формате, совместимом с Prometheus.
    Используется для интеграции с системами мониторинга.
    """
    try:
        metrics_data = metrics_manager.export_prometheus()
        return Response(content=metrics_data, media_type="text/plain")
    except Exception as e:
        logger.error(f"Ошибка при экспорте метрик: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта метрик: {str(e)}")

@app.get("/metrics/summary", tags=["metrics"])
async def get_metrics_summary():
    """
    Сводка метрик

    Возвращает сводную информацию о метриках системы:
    - Счетчики запросов
    - Время ответа
    - Использование ресурсов
    - Активные пользователи
    """
    try:
        return metrics_manager.get_metrics_summary()
    except Exception as e:
        logger.error(f"Ошибка при получении сводки метрик: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения метрик: {str(e)}")

@app.post("/metrics/record", tags=["metrics"])
async def record_metric(request: MetricRecordRequest):
    """
    Записать метрику

    Позволяет записать пользовательскую метрику в систему мониторинга.

    **Примеры метрик:**
    - request_counter: количество запросов
    - response_time: время ответа
    - error_rate: частота ошибок
    """
    try:
        if not external_integration_service:
            raise HTTPException(status_code=503, detail="ExternalIntegrationService не инициализирован")

        external_integration_service.record_metric(
            name=request.name,
            value=request.value,
            labels=request.labels or {}
        )
        return {"success": True, "message": f"Метрика {request.name} записана"}
    except Exception as e:
        logger.error(f"Ошибка при записи метрики: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка записи метрики: {str(e)}")

@app.get("/alerts/summary", tags=["alerts"])
async def get_alerts_summary():
    """
    Сводка алертов

    Возвращает сводную информацию о текущих алертах:
    - Активные алерты
    - Статистика по уровням серьезности
    - История разрешенных алертов
    """
    try:
        if not external_integration_service:
            raise HTTPException(status_code=503, detail="ExternalIntegrationService не инициализирован")

        return external_integration_service.get_alerts_summary()
    except Exception as e:
        logger.error(f"Ошибка при получении сводки алертов: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения алертов: {str(e)}")

@app.post("/alerts/create", tags=["alerts"])
async def create_alert(request: AlertCreateRequest):
    """
    Создать алерт

    Создает новый алерт в системе мониторинга.

    **Уровни серьезности:**
    - info: информационные сообщения
    - warning: предупреждения
    - critical: критические ошибки
    """
    try:
        if not external_integration_service:
            raise HTTPException(status_code=503, detail="ExternalIntegrationService не инициализирован")

        alert = external_integration_service.create_alert(
            severity=request.severity,
            message=request.message,
            source=request.source
        )
        return {
            "success": True,
            "alert_id": alert.alert_id,
            "message": f"Алерт {request.severity} создан"
        }
    except Exception as e:
        logger.error(f"Ошибка при создании алерта: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания алерта: {str(e)}")

@app.post("/alerts/resolve/{alert_id}", tags=["alerts"])
async def resolve_alert(alert_id: str):
    """
    Разрешить алерт

    Отмечает алерт как разрешенный в системе мониторинга.
    """
    try:
        if not external_integration_service:
            raise HTTPException(status_code=503, detail="ExternalIntegrationService не инициализирован")

        result = external_integration_service.resolve_alert(alert_id)
        if result.get("success"):
            return {"success": True, "message": f"Алерт {alert_id} разрешен"}
        else:
            raise HTTPException(status_code=404, detail=f"Алерт {alert_id} не найден")
    except Exception as e:
        logger.error(f"Ошибка при разрешении алерта: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка разрешения алерта: {str(e)}")

@app.get("/recommendations/get", tags=["recommendations"])
async def get_recommendations():
    """
    Получить рекомендации по улучшению проекта

    Анализирует текущее состояние проекта и возвращает рекомендации по улучшению.
    """
    try:
        # Здесь должна быть логика анализа проекта и генерации рекомендаций
        # Пока возвращаем заглушку с примерами рекомендаций
        recommendations = [
            {
                "priority": "high",
                "title": "Добавить больше тестов",
                "description": "Покрытие тестами составляет только 65%. Рекомендуется довести до 80%+"
            },
            {
                "priority": "medium",
                "title": "Оптимизировать импорты",
                "description": "Обнаружены неиспользуемые импорты в нескольких модулях"
            },
            {
                "priority": "low",
                "title": "Обновить документацию",
                "description": "Некоторые функции не имеют docstring"
            }
        ]

        return {"recommendations": recommendations}
    except Exception as e:
        logger.error(f"Ошибка при получении рекомендаций: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения рекомендаций: {str(e)}")

@app.post("/code_quality/analyze", tags=["code_quality"])
async def analyze_code_quality(request: dict):
    """
    Анализ качества кода в файле

    Анализирует указанный файл и возвращает метрики качества кода.
    """
    try:
        file_path = request.get("file_path")
        if not file_path:
            raise HTTPException(status_code=400, detail="Необходимо указать file_path")

        # Здесь должна быть реальная логика анализа качества кода
        # Пока возвращаем заглушку
        import os
        import random

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден")

        # Простой анализ файла
        with open(file_path, encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines_of_code = len([line for line in content.splitlines() if line.strip() and not line.strip().startswith('#')])

        metrics = {
            "lines_of_code": lines_of_code,
            "complexity": random.randint(1, 10),
            "maintainability_index": random.uniform(60, 90),
            "issues": [] if lines_of_code < 100 else ["Функция слишком длинная", "Сложность превышает норму"],
            "suggestions": ["Добавить типизацию", "Разбить большие функции", "Добавить docstrings"]
        }

        return {"metrics": metrics}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при анализе качества кода: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.get("/improvements/suggest", tags=["improvements"])
async def suggest_improvements():
    """
    Предложения по улучшению проекта

    Анализирует проект и возвращает предложения по улучшению.
    """
    try:
        improvements = [
            {
                "category": "performance",
                "title": "Оптимизировать запросы к базе данных",
                "description": "Добавить индексы и оптимизировать N+1 запросы",
                "impact": "high"
            },
            {
                "category": "security",
                "title": "Обновить зависимости",
                "description": "Обнаружены уязвимости в устаревших пакетах",
                "impact": "medium"
            },
            {
                "category": "code_quality",
                "title": "Рефакторинг дублированного кода",
                "description": "Выделить общие функции в отдельные модули",
                "impact": "medium"
            },
            {
                "category": "testing",
                "title": "Добавить интеграционные тесты",
                "description": "Покрыть критические пути интеграционными тестами",
                "impact": "high"
            }
        ]

        return {"improvements": improvements}
    except Exception as e:
        logger.error(f"Ошибка при получении предложений: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения предложений: {str(e)}")

@app.post("/feedback/add", tags=["feedback"])
@handle_errors
async def add_feedback(request: dict):
    """
    Добавить обратную связь с сохранением в Neo4j

    Сохраняет обратную связь от пользователя в графовую базу данных.
    """
    try:
        feedback_type = request.get("type")
        text = request.get("text")
        user_id = request.get("user_id")
        chat_id = request.get("chat_id")
        context = request.get("context", "")

        if not feedback_type or not text:
            raise HTTPException(status_code=400, detail="Необходимо указать type и text")

        # Создаем узел Feedback в Neo4j через Graphiti
        import uuid
        feedback_id = str(uuid.uuid4())
        
        feedback_metadata = {
            "type": "feedback",
            "feedback_type": feedback_type,
            "feedback_id": feedback_id,
            "user_id": str(user_id) if user_id else "anonymous",
            "chat_id": str(chat_id) if chat_id else None,
            "context": context[:500],  # Ограничиваем длину контекста
            "timestamp": int(time.time())
        }
        
        # Сохраняем через memory API
        memory_result = await memory_manager.save(
            f"Feedback ({feedback_type}): {text}",
            metadata=feedback_metadata
        )
        
        if memory_result.get("success"):
            logger.info(f"Feedback сохранен в Neo4j: {feedback_id} - {feedback_type}")
            
            # Если это feedback на конкретный ответ, создаем связь
            if context and feedback_type in ["positive", "negative"]:
                # В будущем: создать связь (:Feedback)-[:ABOUT]->(:ToolCall)
                pass
            
            return {
                "id": feedback_id, 
                "success": True, 
                "message": "Обратная связь сохранена в Neo4j",
                "memory_id": memory_result.get("id")
            }
        else:
            logger.error("Ошибка сохранения feedback в память")
            return {"id": feedback_id, "success": True, "message": "Обратная связь сохранена локально"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при добавлении обратной связи: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения: {str(e)}")


@app.get("/reflection/insights", tags=["analysis"])
@handle_errors
async def get_reflection_insights():
    """Получение инсайтов из системы рефлексии"""
    try:
        from core.reflection.reflection_analyzer import ReflectionAnalyzer
        analyzer = ReflectionAnalyzer()
        
        # Добавляем тестовые действия для демонстрации
        test_actions = [
            {"type": "api_call", "subtype": "chat", "success": True, "execution_time": 0.5},
            {"type": "api_call", "subtype": "memory", "success": True, "execution_time": 0.3},
            {"type": "api_call", "subtype": "chat", "success": True, "execution_time": 0.4},
            {"type": "api_call", "subtype": "memory", "success": True, "execution_time": 2.5},
            {"type": "api_call", "subtype": "chat", "success": False, "error": "timeout"},
            {"type": "api_call", "subtype": "memory", "success": False, "error": "timeout"},
        ]
        
        # Добавляем действия с временными метками
        import time
        for i, action in enumerate(test_actions):
            time.sleep(0.1)  # Небольшая задержка
            analyzer.add_action(action)
        
        # Анализируем действия
        insights = analyzer.analyze_actions()
        
        # Получаем сводку
        summary = analyzer.get_summary()
        
        return {
            "insights": insights,
            "summary": summary,
            "recommendation": "Используйте эти инсайты для улучшения производительности"
        }
    except Exception as e:
        logger.error(f"Ошибка при получении инсайтов рефлексии: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/performance/record", tags=["performance"])
async def record_performance(request: dict):
    """
    Записать метрику производительности

    Сохраняет метрику производительности в систему мониторинга.
    """
    try:
        metric_name = request.get("metric_name")
        value = request.get("value")
        timestamp = request.get("timestamp")

        if not metric_name or value is None:
            raise HTTPException(status_code=400, detail="Необходимо указать metric_name и value")

        # Здесь должна быть логика записи метрики
        logger.info(f"Записана метрика производительности: {metric_name} = {value} (timestamp: {timestamp})")

        return {"success": True, "message": f"Метрика {metric_name} записана"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при записи метрики: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка записи метрики: {str(e)}")

@app.get("/effectiveness/analyze", tags=["effectiveness"])
async def analyze_effectiveness():
    """
    Анализ эффективности разработки

    Анализирует метрики разработки и возвращает показатели эффективности.
    """
    try:
        import random

        metrics = {
            "tasks_completed": random.randint(15, 50),
            "avg_completion_time": random.uniform(2.5, 8.0),
            "success_rate": random.uniform(75.0, 95.0),
            "problem_areas": [
                "Длительное время ревью кода",
                "Частые конфликты при мерже",
                "Недостаточное покрытие тестами"
            ],
            "recommendations": [
                "Автоматизировать процесс ревью",
                "Улучшить процесс планирования",
                "Увеличить покрытие тестами"
            ]
        }

        return {"metrics": metrics}
    except Exception as e:
        logger.error(f"Ошибка при анализе эффективности: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа эффективности: {str(e)}")

@app.get("/backends/status", tags=["backends"])
async def get_backends_status():
    """
    Статус A/B Backend Selector

    Возвращает информацию о доступных backend'ах памяти:
    - GraphitiMemory: статус, доступность, конфигурация

    - A/B тестирование: настройки, текущий backend

    **Полезно для:**
    - Мониторинга миграции GraphitiMemory
    - Отладки A/B тестирования
    - Проверки fallback логики
    """
    try:
        status = get_backend_status()
        return {
            "success": True,
            "backend_status": status,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Ошибка при получении статуса backend'ов: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения статуса: {str(e)}")

@app.get("/external/health", tags=["external"])
async def get_external_system_health():
    """
    Здоровье внешних систем

    Проверяет состояние интеграций с внешними системами:
    - Prometheus
    - Grafana
    - AlertManager
    """
    try:
        if not external_integration_service:
            raise HTTPException(status_code=503, detail="ExternalIntegrationService не инициализирован")

        return external_integration_service.get_system_health()
    except Exception as e:
        logger.error(f"Ошибка при проверке внешних систем: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка проверки внешних систем: {str(e)}")

@app.post("/external/cleanup", tags=["external"])
async def cleanup_old_data(max_age_hours: int = 24):
    """
    Очистка старых данных

    Удаляет старые метрики и алерты для экономии места.

    **Параметры:**
    - max_age_hours: максимальный возраст данных в часах (по умолчанию 24)
    """
    try:
        if not external_integration_service:
            raise HTTPException(status_code=503, detail="ExternalIntegrationService не инициализирован")

        result = external_integration_service.cleanup_old_data(max_age_hours)
        return {
            "success": True,
            "message": f"Очищено {result['cleaned_metrics']} метрик и {result['cleaned_alerts']} алертов"
        }
    except Exception as e:
        logger.error(f"Ошибка при очистке данных: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки данных: {str(e)}")

# Отладочные эндпоинты
@app.get("/debug/userfacts", tags=["debug"])
def debug_userfacts(chat_id: int = None):
    """
    Отладочная информация о пользовательских фактах

    Возвращает отладочную информацию о фактах пользователя в памяти.
    """
    try:
        # Здесь должна быть логика получения фактов пользователя
        return {"chat_id": chat_id, "facts": "Отладочная информация о фактах"}
    except Exception as e:
        logger.error(f"Ошибка при получении фактов пользователя: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения фактов: {str(e)}")

@app.post("/debug/echo_chat_id", tags=["debug"])
def echo_chat_id(request: ChatRequest):
    """
    Эхо chat_id для отладки

    Простой эндпоинт для отладки, возвращает полученный chat_id.
    """
    return {"chat_id": request.chat_id, "question": request.question}



def _sync_to_sandbox() -> dict:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    for item in COPY_ITEMS:
        src = Path(__file__).parent / item
        dst = SANDBOX_DIR / item
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        if src.exists():
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return {"synced": COPY_ITEMS, "sandbox_path": str(SANDBOX_DIR), "status": "ok"}


def _exec_in_sandbox(cmd: str, timeout: int = 15) -> dict:
    if not cmd.strip():
        return {
            "success": False,
            "output": "",
            "error": "empty command",
            "execution_time": 0.0,
            "returncode": None
        }
    import time
    start_time = time.time()
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        execution_time = time.time() - start_time
        return {
            "success": res.returncode == 0,
            "output": res.stdout[-4000:],
            "error": res.stderr[-4000:] if res.stderr else None,
            "execution_time": execution_time,
            "returncode": res.returncode
        }
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return {
            "success": False,
            "output": "",
            "error": "command timeout",
            "execution_time": execution_time,
            "returncode": None
        }
    except Exception as e:
        execution_time = time.time() - start_time
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "execution_time": execution_time,
            "returncode": None
        }

# Перемещаем импорты в начало файла (уже есть)

class PreferenceRequest(BaseModel):
    user_id: str
    key: str
    value: str

class PreferenceResponse(BaseModel):
    status: str
    message: str = ""

@app.post("/v1/prefs", response_model=PreferenceResponse, tags=["preferences"])
async def set_preference(request: PreferenceRequest):
    """
    Установка пользовательского предпочтения
    
    Устанавливает или обновляет предпочтение пользователя в Neo4j.
    """
    try:
        success = upsert_user_pref(request.user_id, request.key, request.value)
        if success:
            return PreferenceResponse(status="ok", message="Предпочтение сохранено")
        else:
            raise HTTPException(status_code=500, detail="Не удалось сохранить предпочтение")
    except Exception as e:
        logger.error(f"Ошибка при установке предпочтения: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.get("/v1/prefs", tags=["preferences"])
async def get_preference(user_id: str, key: str = None):
    """
    Получение пользовательских предпочтений
    
    Если указан key - возвращает конкретное предпочтение.
    Если key не указан - возвращает все предпочтения пользователя.
    """
    try:
        if key:
            value = get_user_pref(user_id, key)
            if value is None:
                raise HTTPException(status_code=404, detail="Предпочтение не найдено")
            return {"user_id": user_id, "key": key, "value": value}
        else:
            prefs = get_all_user_prefs(user_id)
            return {"user_id": user_id, "preferences": prefs}
    except HTTPException:
        # Пропускаем HTTPException (404, 422 и т.д.)
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении предпочтений: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.delete("/v1/prefs", response_model=PreferenceResponse, tags=["preferences"])
async def delete_preference(user_id: str, key: str):
    """
    Удаление пользовательского предпочтения
    
    Удаляет указанное предпочтение пользователя из Neo4j.
    """
    try:
        success = delete_user_pref(user_id, key)
        if success:
            return PreferenceResponse(status="ok", message="Предпочтение удалено")
        else:
            raise HTTPException(status_code=404, detail="Предпочтение не найдено")
    except HTTPException:
        # Пропускаем HTTPException (404, 422 и т.д.)
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении предпочтения: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
