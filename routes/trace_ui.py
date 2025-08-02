#!/usr/bin/env python3
"""
Trace UI роуты для Марк v2
Предоставляет веб-интерфейс для просмотра трассировки агентов
"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from langchain_api.middlewares.agents_trace import get_trace_collector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trace", tags=["trace"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def trace_ui(request: Request):
    """Главная страница UI трассировки"""
    return templates.TemplateResponse("trace.html", {"request": request})


@router.get("/api/spans")
async def get_spans(limit: int = 50, span_type: Optional[str] = None):
    """API для получения последних spans"""
    try:
        trace_collector = get_trace_collector()
        spans = trace_collector.get_recent_spans(limit)
        
        # Фильтрация по типу если указан
        if span_type:
            spans = [span for span in spans if span.get('span_type') == span_type]
        
        return JSONResponse(content={
            "success": True,
            "spans": spans,
            "count": len(spans)
        })
    except Exception as e:
        logger.error(f"❌ Ошибка получения spans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/spans/{span_id}")
async def get_span_details(span_id: str):
    """API для получения деталей конкретного span"""
    try:
        trace_collector = get_trace_collector()
        span_tree = trace_collector.get_span_tree(span_id)
        
        if not span_tree:
            raise HTTPException(status_code=404, detail="Span не найден")
        
        return JSONResponse(content={
            "success": True,
            "span": span_tree
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения span {span_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats")
async def get_trace_stats():
    """API для получения статистики трассировки"""
    try:
        trace_collector = get_trace_collector()
        spans = trace_collector.get_recent_spans(1000)  # Больше данных для статистики
        
        # Статистика по типам
        type_stats = {}
        status_stats = {}
        total_duration = 0
        error_count = 0
        
        for span in spans:
            span_type = span.get('span_type', 'unknown')
            status = span.get('status', 'unknown')
            duration = span.get('duration_ms', 0)
            
            type_stats[span_type] = type_stats.get(span_type, 0) + 1
            status_stats[status] = status_stats.get(status, 0) + 1
            total_duration += duration
            
            if status == 'error':
                error_count += 1
        
        return JSONResponse(content={
            "success": True,
            "stats": {
                "total_spans": len(spans),
                "type_distribution": type_stats,
                "status_distribution": status_stats,
                "total_duration_ms": total_duration,
                "avg_duration_ms": total_duration / len(spans) if spans else 0,
                "error_rate": error_count / len(spans) if spans else 0
            }
        })
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/spans")
async def clear_spans():
    """API для очистки всех spans (только для разработки)"""
    try:
        # В продакшене эту функцию нужно отключить
        trace_collector = get_trace_collector()
        
        # Очистка базы данных
        import sqlite3
        with sqlite3.connect(trace_collector.db_path) as conn:
            conn.execute("DELETE FROM trace_spans")
            conn.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": "Все spans очищены"
        })
    except Exception as e:
        logger.error(f"❌ Ошибка очистки spans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/health")
async def trace_health():
    """API для проверки здоровья системы трассировки"""
    try:
        trace_collector = get_trace_collector()
        
        # Проверка подключения к базе данных
        spans = trace_collector.get_recent_spans(1)
        
        return JSONResponse(content={
            "success": True,
            "status": "healthy",
            "database_accessible": True,
            "recent_spans_count": len(spans)
        })
    except Exception as e:
        logger.error(f"❌ Ошибка проверки здоровья трассировки: {e}")
        return JSONResponse(content={
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        }, status_code=500) 