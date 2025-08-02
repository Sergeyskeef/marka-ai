"""
Pydantic схемы для Tools
Марка v2 - Spine Upgrade Phase 1, Block 2
"""

from typing import Any

from pydantic import BaseModel, Field

# =====================================================
# Web Search Tools
# =====================================================

class WebSearchIn(BaseModel):
    """Входные данные для веб-поиска"""
    query: str = Field(..., min_length=3, max_length=256, description="Поисковый запрос")
    max_results: int | None = Field(default=5, ge=1, le=20, description="Максимальное количество результатов")


class WebSearchOut(BaseModel):
    """Результат веб-поиска"""
    title: str = Field(..., description="Заголовок страницы")
    url: str = Field(..., description="URL страницы")
    snippet: str = Field(..., description="Краткое описание содержимого")
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Оценка релевантности")


# =====================================================
# Graph Search Tools
# =====================================================

class GraphSearchIn(BaseModel):
    """Входные данные для поиска в графе знаний"""
    query: str = Field(..., min_length=2, max_length=500, description="Поисковый запрос")
    node_types: list[str] | None = Field(default=None, description="Типы узлов для поиска")
    limit: int | None = Field(default=10, ge=1, le=100, description="Лимит результатов")


class GraphSearchOut(BaseModel):
    """Результат поиска в графе"""
    node_id: str = Field(..., description="ID найденного узла")
    node_type: str = Field(..., description="Тип узла")
    content: str = Field(..., description="Содержимое узла")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Оценка сходства")
    metadata: dict[str, Any] | None = Field(default=None, description="Дополнительные метаданные")


# =====================================================
# Summarization Tools
# =====================================================

class SummarizeIn(BaseModel):
    """Входные данные для суммаризации"""
    text: str = Field(..., min_length=10, max_length=10000, description="Текст для суммаризации")
    max_length: int | None = Field(default=200, ge=50, le=1000, description="Максимальная длина резюме")
    style: str | None = Field(default="concise", description="Стиль суммаризации: concise, detailed, bullet_points")


class SummarizeOut(BaseModel):
    """Результат суммаризации"""
    summary: str = Field(..., description="Суммаризированный текст")
    original_length: int = Field(..., description="Длина исходного текста")
    summary_length: int = Field(..., description="Длина резюме")
    compression_ratio: float = Field(..., ge=0.0, le=1.0, description="Коэффициент сжатия")


# =====================================================
# Code Execution Tools
# =====================================================

class CodeExecutionIn(BaseModel):
    """Входные данные для выполнения кода"""
    code: str = Field(..., min_length=1, max_length=10000, description="Код для выполнения")
    language: str | None = Field(default="python", description="Язык программирования")
    timeout: int | None = Field(default=30, ge=1, le=300, description="Таймаут выполнения в секундах")
    sandbox: bool | None = Field(default=True, description="Выполнять в песочнице")


class CodeExecutionOut(BaseModel):
    """Результат выполнения кода"""
    output: str = Field(..., description="Вывод программы")
    error: str | None = Field(default=None, description="Сообщение об ошибке")
    execution_time: float = Field(..., ge=0.0, description="Время выполнения в секундах")
    exit_code: int = Field(..., description="Код завершения")


# =====================================================
# Memory Tools
# =====================================================

class MemoryStoreIn(BaseModel):
    """Входные данные для сохранения в память"""
    content: str = Field(..., min_length=1, max_length=10000, description="Содержимое для сохранения")
    metadata: dict[str, Any] | None = Field(default=None, description="Метаданные")
    tags: list[str] | None = Field(default=None, description="Теги для категоризации")


class MemoryStoreOut(BaseModel):
    """Результат сохранения в память"""
    memory_id: str = Field(..., description="ID сохраненной записи")
    stored_at: str = Field(..., description="Время сохранения")
    success: bool = Field(..., description="Успешность операции")


class MemoryRetrieveIn(BaseModel):
    """Входные данные для поиска в памяти"""
    query: str = Field(..., min_length=1, max_length=500, description="Поисковый запрос")
    limit: int | None = Field(default=5, ge=1, le=50, description="Лимит результатов")
    tags: list[str] | None = Field(default=None, description="Фильтр по тегам")


class MemoryRetrieveOut(BaseModel):
    """Результат поиска в памяти"""
    memories: list[dict[str, Any]] = Field(..., description="Найденные записи")
    total_found: int = Field(..., description="Общее количество найденных записей")
    search_time: float = Field(..., ge=0.0, description="Время поиска в секундах")


# =====================================================
# Analysis Tools
# =====================================================

class TextAnalysisIn(BaseModel):
    """Входные данные для анализа текста"""
    text: str = Field(..., min_length=10, max_length=10000, description="Текст для анализа")
    analysis_type: str = Field(..., description="Тип анализа: sentiment, topics, entities, summary")
    language: str | None = Field(default="auto", description="Язык текста")


class TextAnalysisOut(BaseModel):
    """Результат анализа текста"""
    analysis_type: str = Field(..., description="Тип выполненного анализа")
    results: dict[str, Any] = Field(..., description="Результаты анализа")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность в результатах")
    processing_time: float = Field(..., ge=0.0, description="Время обработки в секундах")


# =====================================================
# Utility Tools
# =====================================================

class FileReadIn(BaseModel):
    """Входные данные для чтения файла"""
    file_path: str = Field(..., description="Путь к файлу")
    encoding: str | None = Field(default="utf-8", description="Кодировка файла")
    max_size: int | None = Field(default=1048576, description="Максимальный размер файла в байтах")


class FileReadOut(BaseModel):
    """Результат чтения файла"""
    content: str = Field(..., description="Содержимое файла")
    file_size: int = Field(..., description="Размер файла в байтах")
    encoding: str = Field(..., description="Использованная кодировка")
    success: bool = Field(..., description="Успешность операции")


class FileWriteIn(BaseModel):
    """Входные данные для записи файла"""
    file_path: str = Field(..., description="Путь к файлу")
    content: str = Field(..., description="Содержимое для записи")
    encoding: str | None = Field(default="utf-8", description="Кодировка файла")
    mode: str | None = Field(default="w", description="Режим записи: w, a")


class FileWriteOut(BaseModel):
    """Результат записи файла"""
    success: bool = Field(..., description="Успешность операции")
    bytes_written: int = Field(..., description="Количество записанных байт")
    file_path: str = Field(..., description="Путь к записанному файлу")
