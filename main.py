# main.py
"""FastAPI-ядро Марка: чат-инференс, долговременная память и песочница."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
import os
from pathlib import Path
from typing import Dict, Optional, Any
import logging
import json

from fastapi import Body, FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.config import Configure, Property, DataType
import uvicorn
from langchain_api.core.monitoring import metrics

# Импортируем улучшенную RAG-цепочку вместо стандартной
# from rag.rag_chain import generate_response
from langchain_api.rag.enhanced_rag_chain import generate_response
from langchain_api.routers import passport_sync
from langchain_api.globals import passport_sync_service
from langchain_api.routers.task_router import router as task_router
from langchain_api.routers.log_router import router as log_router
from langchain_api.services.passport_sync_service import PassportSyncService
from langchain_api.scripts.auto_sync_passport import ChangeReport
from langchain_api.services.health_service import HealthService

# Импортируем LLM Integration Hub
from langchain_api.core.llm_integration_hub import LLMIntegrationHub, LLMRequest

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
    "rag",
    "utils",
    "requirements.txt",
    "Dockerfile",
]

# Инициализация FastAPI
app = FastAPI(title="LangChain API")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные переменные
weaviate_client = None
passport_sync_service = None
health_service = None
llm_hub = None  # Добавляем глобальный экземпляр LLMIntegrationHub

# Подключаем роутеры
app.include_router(passport_sync.router)
app.include_router(task_router)
app.include_router(log_router)

# Подключаем метрики
metrics.setup_metrics(app)

@app.on_event("startup")
async def startup_event():
    """Инициализация сервисов при запуске приложения"""
    global passport_sync_service, health_service, llm_hub
    try:
        # Инициализация PassportSyncService
        passport_sync_service = PassportSyncService()
        logger.info("PassportSyncService успешно инициализирован")
        
        # Инициализация HealthService
        health_service = HealthService(get_weaviate_client())
        logger.info("HealthService успешно инициализирован")
        
        # Инициализация LLMIntegrationHub
        llm_hub = LLMIntegrationHub()
        await llm_hub.initialize()
        logger.info("LLMIntegrationHub успешно инициализирован")
        
    except Exception as e:
        logger.error(f"Ошибка при инициализации сервисов: {str(e)}")
        passport_sync_service = None
        health_service = None
        llm_hub = None

@app.on_event("shutdown")
async def shutdown_event():
    """Очистка ресурсов при остановке приложения"""
    global passport_sync_service, llm_hub
    if passport_sync_service:
        try:
            await passport_sync_service.cleanup()
            logger.info("PassportSyncService успешно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке PassportSyncService: {str(e)}")
    passport_sync_service = None
    
    if llm_hub:
        try:
            await llm_hub.shutdown()
            logger.info("LLMIntegrationHub успешно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке LLMIntegrationHub: {str(e)}")
    llm_hub = None

async def handle_passport_changes(changes: ChangeReport):
    """Обработчик изменений в паспорте"""
    # Здесь можно добавить логику обработки изменений
    # Например, отправку уведомлений в Telegram или другие системы
    print(f"Обнаружены изменения в паспорте:\n{changes.to_markdown()}")

@app.get("/passport/sync/status")
async def get_sync_status():
    """Получить статус автосинхронизации"""
    if not passport_sync_service:
        return {"error": "Сервис автосинхронизации не инициализирован"}
    return passport_sync_service.status

@app.post("/passport/sync/apply")
async def apply_changes(background_tasks: BackgroundTasks):
    """Применить накопленные изменения"""
    if not passport_sync_service:
        return {"error": "Сервис автосинхронизации не инициализирован"}
    
    # Применяем изменения в фоновом режиме
    background_tasks.add_task(passport_sync_service.apply_changes)
    return {"message": "Изменения будут применены в фоновом режиме"}

@app.get("/passport/sync/changes")
async def get_pending_changes():
    """Получить список накопленных изменений"""
    if not passport_sync_service:
        return {"error": "Сервис автосинхронизации не инициализирован"}
    
    changes = passport_sync_service.get_pending_changes()
    return {
        "changes": changes.to_dict(),
        "markdown": changes.to_markdown()
    }

@app.post("/passport/sync/clear")
async def clear_pending_changes():
    """Очистить накопленные изменения"""
    if not passport_sync_service:
        return {"error": "Сервис автосинхронизации не инициализирован"}
    
    passport_sync_service.clear_pending_changes()
    return {"message": "Накопленные изменения очищены"}

def get_weaviate_client():
    """Получает глобальный клиент Weaviate, инициализирует при необходимости."""
    global weaviate_client
    
    if weaviate_client is None:
        connection_params = ConnectionParams.from_params(
            http_host=os.getenv("WEAVIATE_HTTP_HOST", "weaviate"),
            http_port=int(os.getenv("WEAVIATE_HTTP_PORT", "8080")),
            http_secure=False,
            grpc_host=os.getenv("WEAVIATE_GRPC_HOST", "weaviate"),
            grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
            grpc_secure=False,
        )
        weaviate_client = WeaviateClient(connection_params=connection_params)
        weaviate_client.connect()
    
    return weaviate_client

# Функция: Убедиться, что класс Memory есть
def _ensure_memory_class() -> None:
    client = get_weaviate_client()
    
    try:
        if not client.collections.exists("Memory"):
            client.collections.create(
                name="Memory",
                vectorizer_config=Configure.Vectorizer.text2vec_openai(),
                properties=[
                    Property(name="sender", data_type=DataType.TEXT),
                    Property(name="message", data_type=DataType.TEXT),
                    Property(name="timestamp", data_type=DataType.DATE),
                    Property(name="importance", data_type=DataType.NUMBER),
                    Property(name="session_id", data_type=DataType.TEXT),
                    Property(name="tags", data_type=DataType.TEXT_ARRAY)
                ]
            )
    except Exception as e:
        print(f"Error ensuring Memory class: {e}")
        raise

_ensure_memory_class()

# Модель запроса к чату
class ChatRequest(BaseModel):
    question: str
    chat_id: Optional[int] = None

def _sync_to_sandbox() -> Dict:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    for item in COPY_ITEMS:
        src = Path(__file__).parent / item
        dst = SANDBOX_DIR / item
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        if src.exists():
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return {"synced": COPY_ITEMS, "sandbox_path": str(SANDBOX_DIR), "status": "ok"}


def _exec_in_sandbox(cmd: str, timeout: int = 15) -> Dict:
    if not cmd.strip():
        raise HTTPException(400, "empty command")
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "command timeout")

    return {
        "cmd": cmd,
        "returncode": res.returncode,
        "stdout": res.stdout[-4000:],
        "stderr": res.stderr[-4000:],
    }

# REST-эндпоинты

@app.post("/chat/ask")
async def chat_ask(request: ChatRequest):
    """Обработка запроса к чату через LLM Integration Hub."""
    try:
        question = request.question.strip()
        chat_id = request.chat_id
        
        if not question:
            return JSONResponse(content={"error": "Пустой запрос"}, status_code=400)
        
        if not llm_hub:
            # Fallback на старую систему, если LLMIntegrationHub не инициализирован
            logger.warning("LLMIntegrationHub не инициализирован, используем fallback")
            answer = generate_response(question, chat_id)
            return {"answer": answer, "meta": {"chat_id": chat_id, "fallback": True}}
        
        # Формируем запрос для LLMIntegrationHub
        llm_request = LLMRequest(
            prompt=question,
            context={"chat_id": chat_id, "source": "telegram"},
            priority=0.7,  # Средний приоритет для обычных вопросов
            temperature=0.3
        )
        
        # Обрабатываем запрос через LLMIntegrationHub
        llm_response = await llm_hub.process_request(llm_request)
        
        # Извлекаем ответ
        answer = llm_response.content
        
        # Формируем метаданные ответа
        meta = {
            "chat_id": chat_id,
            "llm_integration_hub": True,
            "confidence": llm_response.confidence,
            "reasoning": llm_response.reasoning,
            "suggestions": llm_response.suggestions,
            "metadata": llm_response.metadata
        }
        
        return {"answer": answer, "meta": meta}
        
    except Exception as e:
        logging.error(f"Ошибка при обработке запроса: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sandbox/sync")
def sandbox_sync() -> Dict:
    return _sync_to_sandbox()


@app.post("/sandbox/exec")
def sandbox_exec(command: str = Body(..., embed=True)) -> Dict:
    return _exec_in_sandbox(command)


@app.get("/ping")
def ping():
    """Проверка состояния сервиса."""
    return {"status": "ok", "version": "1.0", "memory_type": "multi-layer"}

@app.get("/debug/userfacts")
def debug_userfacts(chat_id: int = None):
    """Диагностика: получить все UserFacts (фильтрация по chat_id отключена, возвращаются все факты)."""
    from langchain_api.memory.memory_manager import MemoryManager
    mm = MemoryManager()
    wrapper = mm.memory_registry.get("UserFacts")
    facts = wrapper.snapshot()["snapshot"]
    return {"userfacts": facts}

@app.post("/debug/echo_chat_id")
def echo_chat_id(request: ChatRequest):
    """Возвращает chat_id из запроса (для Telegram-бота)."""
    return {"chat_id": request.chat_id}

@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    if not health_service:
        raise HTTPException(
            status_code=503,
            detail="Сервис мониторинга здоровья не инициализирован"
        )
    
    health_status = await health_service.get_health()
    
    if health_status["status"] == "unhealthy":
        raise HTTPException(
            status_code=503,
            detail="Один или несколько сервисов недоступны",
            headers={"X-Health-Status": json.dumps(health_status)}
        )
    
    return health_status

@app.get("/")
async def root():
    return {"message": "Welcome to LangChain API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
