from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import sys
import asyncio

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.chat import router as chat_router
from app.api.prompts_api import register_prompts_api
from core.monitoring import metrics, update_memory_usage

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

@app.on_event("startup")
async def _start_metrics_bg_task():
    async def _bg():
        while True:
            try:
                update_memory_usage()
            except Exception:
                pass
            await asyncio.sleep(10)
    asyncio.create_task(_bg())

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mark-ai"}

@app.get("/")
async def root():
    return {"message": "Mark AI API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)