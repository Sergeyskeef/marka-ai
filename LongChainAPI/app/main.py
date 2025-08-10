from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.chat import router as chat_router
from app.api.memory import router as memory_router
from app.api.prompts_api import register_prompts_api

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
app.include_router(memory_router, prefix="/api/memory", tags=["memory"])
register_prompts_api(app)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mark-ai"}

@app.get("/")
async def root():
    return {"message": "Mark AI API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)