# models_memory.py - модели для валидации метаданных памяти
from pydantic import BaseModel, Field
from typing import Optional, List

class MemoryMetadata(BaseModel):
    user_id: Optional[str] = None
    timestamp: Optional[int] = None
    tags: Optional[List[str]] = None
    importance: Optional[float] = Field(default=None, ge=0, le=1)
    source: Optional[str] = None
