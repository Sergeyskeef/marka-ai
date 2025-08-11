"""
Pydantic модели для системы памяти
"""

from typing import Any, Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime


class MemoryMetadata(BaseModel):
    """Модель метаданных для записи в память"""
    user_id: Optional[str] = Field(None, description="ID пользователя")
    chat_id: Optional[str] = Field(None, description="ID чата")
    timestamp: Optional[int] = Field(None, description="Unix timestamp")
    tags: Optional[List[str]] = Field(default_factory=list, description="Теги для категоризации")
    importance: Optional[float] = Field(None, ge=0.0, le=1.0, description="Важность от 0 до 1")
    source: Optional[str] = Field(None, description="Источник данных")
    type: Optional[str] = Field(None, description="Тип записи")
    context: Optional[str] = Field(None, max_length=1000, description="Контекст")
    
    @validator('timestamp', pre=True, always=True)
    def set_timestamp(cls, v):
        """Автоматически устанавливает timestamp если не указан"""
        return v or int(datetime.now().timestamp())
    
    @validator('tags', pre=True)
    def ensure_tags_list(cls, v):
        """Преобразует строку в список если нужно"""
        if isinstance(v, str):
            return [v]
        return v or []
    
    class Config:
        extra = "allow"  # Разрешаем дополнительные поля


class MemoryEntry(BaseModel):
    """Модель записи в памяти"""
    text: str = Field(..., min_length=1, max_length=10000, description="Текст записи")
    metadata: Optional[MemoryMetadata] = Field(default_factory=MemoryMetadata, description="Метаданные")
    
    @validator('text')
    def clean_text(cls, v):
        """Очищает текст от лишних пробелов"""
        return v.strip()


class MemorySearchResult(BaseModel):
    """Модель результата поиска"""
    id: str = Field(..., description="ID записи")
    text: str = Field(..., description="Текст записи")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные")
    score: Optional[float] = Field(None, description="Релевантность результата")
    created_at: Optional[int] = Field(None, description="Время создания")


class MemoryResponse(BaseModel):
    """Модель ответа API памяти"""
    success: bool = Field(..., description="Успешность операции")
    message: Optional[str] = Field(None, description="Сообщение")
    data: Optional[Any] = Field(None, description="Данные ответа")
    error: Optional[str] = Field(None, description="Сообщение об ошибке")
    
    @validator('success', always=True)
    def check_consistency(cls, v, values):
        """Проверяет консистентность success и error"""
        if not v and not values.get('error'):
            raise ValueError("Если success=False, должно быть указано error")
        return v