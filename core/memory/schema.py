"""
Схема памяти для проекта Марк
Основана на рекомендациях Graphiti для agent-based систем
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class TaskStatus(str, Enum):
    """Статусы задач"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactType(str, Enum):
    """Типы артефактов"""
    FILE = "file"
    CODE = "code"
    DOCUMENT = "document"
    IMAGE = "image"
    LOG = "log"
    MEMORY = "memory"
    OTHER = "other"


class MessageRole(str, Enum):
    """Роли сообщений"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# === Узлы (Nodes) ===

class User(BaseModel):
    """Пользователь системы"""
    id: str = Field(..., description="Уникальный идентификатор пользователя")
    name: Optional[str] = Field(None, description="Имя пользователя")
    telegram_id: Optional[str] = Field(None, description="Telegram ID")
    created_at: datetime = Field(default_factory=datetime.now)


class Session(BaseModel):
    """Сессия взаимодействия"""
    id: str = Field(..., description="ID сессии")
    user_id: str = Field(..., description="ID владельца сессии")
    ts_start: datetime = Field(default_factory=datetime.now, description="Время начала")
    ts_end: Optional[datetime] = Field(None, description="Время окончания")
    context: Optional[dict] = Field(default_factory=dict, description="Контекст сессии")


class Message(BaseModel):
    """Сообщение в рамках сессии"""
    id: str = Field(..., description="ID сообщения")
    session_id: str = Field(..., description="ID сессии")
    role: MessageRole = Field(..., description="Роль отправителя")
    text: str = Field(..., description="Текст сообщения")
    ts: datetime = Field(default_factory=datetime.now, description="Временная метка")
    metadata: Optional[dict] = Field(default_factory=dict)


class Task(BaseModel):
    """Задача, созданная из сообщения"""
    id: str = Field(..., description="ID задачи")
    name: str = Field(..., description="Название задачи")
    description: Optional[str] = Field(None, description="Описание")
    status: TaskStatus = Field(TaskStatus.PENDING, description="Статус")
    ts: datetime = Field(default_factory=datetime.now, description="Время создания")
    due_date: Optional[datetime] = Field(None, description="Срок выполнения")
    priority: int = Field(5, ge=1, le=10, description="Приоритет (1-10)")


class Artifact(BaseModel):
    """Артефакт, созданный задачей"""
    id: str = Field(..., description="ID артефакта")
    type: ArtifactType = Field(..., description="Тип артефакта")
    path: Optional[str] = Field(None, description="Путь к файлу")
    content: Optional[str] = Field(None, description="Содержимое (для небольших артефактов)")
    ts: datetime = Field(default_factory=datetime.now, description="Время создания")
    metadata: Optional[dict] = Field(default_factory=dict)


class Mistake(BaseModel):
    """Ошибка, вызванная сообщением или действием"""
    id: str = Field(..., description="ID ошибки")
    summary: str = Field(..., description="Краткое описание ошибки")
    details: Optional[str] = Field(None, description="Подробности")
    error_type: Optional[str] = Field(None, description="Тип ошибки")
    ts: datetime = Field(default_factory=datetime.now, description="Время возникновения")
    severity: int = Field(5, ge=1, le=10, description="Серьезность (1-10)")


class Insight(BaseModel):
    """Инсайт, полученный из анализа ошибок"""
    id: str = Field(..., description="ID инсайта")
    summary: str = Field(..., description="Краткое описание инсайта")
    description: Optional[str] = Field(None, description="Подробное описание")
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Уверенность (0-1)")
    ts: datetime = Field(default_factory=datetime.now, description="Время создания")
    tags: List[str] = Field(default_factory=list, description="Теги для категоризации")


# === Отношения (Relationships) ===

class Owns(BaseModel):
    """User owns Session"""
    user_id: str
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)


class Contains(BaseModel):
    """Session contains Message"""
    session_id: str
    message_id: str
    order: int = Field(..., description="Порядковый номер в сессии")


class Triggers(BaseModel):
    """Message triggers Task"""
    message_id: str
    task_id: str
    confidence: float = Field(1.0, description="Уверенность в связи")
    created_at: datetime = Field(default_factory=datetime.now)


class Produces(BaseModel):
    """Task produces Artifact"""
    task_id: str
    artifact_id: str
    created_at: datetime = Field(default_factory=datetime.now)


class CausedError(BaseModel):
    """Message caused_error Mistake"""
    message_id: str
    mistake_id: str
    created_at: datetime = Field(default_factory=datetime.now)


class ResolvedBy(BaseModel):
    """Mistake resolved_by Insight"""
    mistake_id: str
    insight_id: str
    effectiveness: float = Field(0.8, ge=0.0, le=1.0, description="Эффективность решения")
    created_at: datetime = Field(default_factory=datetime.now)


# === Схема для Graphiti ===

GRAPHITI_SCHEMA = {
    "nodes": [
        {
            "type": "User",
            "properties": ["id", "name", "telegram_id", "created_at"]
        },
        {
            "type": "Session", 
            "properties": ["id", "user_id", "ts_start", "ts_end", "context"]
        },
        {
            "type": "Message",
            "properties": ["id", "session_id", "role", "text", "ts", "metadata"]
        },
        {
            "type": "Task",
            "properties": ["id", "name", "description", "status", "ts", "due_date", "priority"]
        },
        {
            "type": "Artifact",
            "properties": ["id", "type", "path", "content", "ts", "metadata"]
        },
        {
            "type": "Mistake",
            "properties": ["id", "summary", "details", "error_type", "ts", "severity"]
        },
        {
            "type": "Insight",
            "properties": ["id", "summary", "description", "confidence", "ts", "tags"]
        }
    ],
    "relationships": [
        {
            "type": "owns",
            "source": "User",
            "target": "Session",
            "properties": ["created_at"]
        },
        {
            "type": "contains",
            "source": "Session",
            "target": "Message",
            "properties": ["order"]
        },
        {
            "type": "triggers",
            "source": "Message",
            "target": "Task",
            "properties": ["confidence", "created_at"]
        },
        {
            "type": "produces",
            "source": "Task",
            "target": "Artifact",
            "properties": ["created_at"]
        },
        {
            "type": "caused_error",
            "source": "Message",
            "target": "Mistake",
            "properties": ["created_at"]
        },
        {
            "type": "resolved_by",
            "source": "Mistake",
            "target": "Insight",
            "properties": ["effectiveness", "created_at"]
        }
    ]
}