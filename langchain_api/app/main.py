from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import sys
import asyncio
import warnings

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# включаем фасад памяти (можно отключить MARK_MEMORY_FACADE=0)
try:
    import core.memory.facade_shim  # noqa: F401
except Exception as _e:
    logging.getLogger(__name__).warning(f'facade_shim not loaded: {_e}')

from app.api.chat import router as chat_router
from app.api.prompts_api import register_prompts_api
from app.utils.fallback_queue import fallback_worker_loop
from core.monitoring import metrics, update_memory_usage
from core.memory.graphiti_adapter import graphiti_adapter

app = FastAPI(title="Mark AI API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat_router, prefix="/api", tags=["chat"])

# Память может быть не собрана/отсутствовать — подключаем опционально
try:
    from app.api.memory import router as memory_router  # type: ignore
    app.include_router(memory_router, prefix="/api/memory", tags=["memory"])
    logging.getLogger(__name__).info("✅ Memory API enabled")
except Exception as e:  # noqa: BLE001
    logging.getLogger(__name__).warning(f"Memory API disabled: {e}")

# Автономность - новые роуты
try:
    from app.api.autonomy_routes import router as autonomy_router
    app.include_router(autonomy_router, prefix="/api", tags=["autonomy"])
    logging.getLogger(__name__).info("✅ Autonomy API enabled")
except Exception as e:
    logging.getLogger(__name__).warning(f"Autonomy API disabled: {e}")

register_prompts_api(app)
metrics.setup_metrics(app)

# --- Логирование и фильтрация шума ---
# 1) Глушим предупреждение о pkg_resources из dependency_tools
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

# 2) Фильтруем шумные строки доступа Uvicorn (healthchecks, сканеры и прочее)
class _EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        msg = record.getMessage()
        noisy_markers = (
            '"GET /health',
            '"GET / HTTP',
            'favicon.ico',
            'device.rsp?',
            'PRI * HTTP/2.0',
            '/cgi-bin/luci',
        )
        return not any(marker in msg for marker in noisy_markers)

try:
    _uvicorn_access = logging.getLogger("uvicorn.access")
    _uvicorn_access.addFilter(_EndpointFilter())
except Exception:
    pass

@app.on_event("startup")
async def _start_metrics_bg_task():
    async def _metrics_bg():
        while True:
            try:
                update_memory_usage()
            except Exception:
                pass
            await asyncio.sleep(10)

    asyncio.create_task(_metrics_bg())

    if os.getenv("DISABLE_GRAPHITI_FALLBACK_WORKER", "0") != "1":
        asyncio.create_task(fallback_worker_loop())

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mark-ai"}

@app.get("/")
async def root():
    return {"message": "Mark AI API", "version": "1.0.0"}

# --- Совместимые эндпоинты под интеграционные тесты ---
@app.post("/memory")
async def create_memory(payload: dict):
    """Создать эпизод в памяти. Ожидает {text, metadata} и возвращает {success, episode_id, text}."""
    try:
        text = payload.get("text") or payload.get("content") or ""
        metadata = payload.get("metadata") or {}
        res = await graphiti_adapter.create_episode(text=text, metadata=metadata)
        if res.get("success"):
            return {"success": True, "episode_id": res.get("id"), "text": text}
        return {"success": False, "error": res.get("error")}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/search")
async def search(q: str, limit: int = 10):
    """Поиск эпизодов. Возвращает {items, total}."""
    try:
        res = await graphiti_adapter.search_episodes(query=q, limit=limit)
        return {"items": res.get("items", []), "total": res.get("total", 0)}
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)