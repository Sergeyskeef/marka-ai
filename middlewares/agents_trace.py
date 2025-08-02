#!/usr/bin/env python3
"""
Tracing middleware для Марк v2
Перехватывает вызовы ToolCall, LLM запросы и ответы, сохраняет в SQLite
"""
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class TraceSpan:
    """Представляет один span в трассировке"""
    
    def __init__(self, span_id: str, name: str, span_type: str, parent_id: Optional[str] = None):
        self.span_id = span_id
        self.name = name
        self.span_type = span_type  # 'llm', 'tool', 'user', 'assistant'
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.input_data: Optional[Dict[str, Any]] = None
        self.output_data: Optional[Dict[str, Any]] = None
        self.metadata: Dict[str, Any] = {}
        self.status = "started"
        self.error: Optional[str] = None
        self.created_at = datetime.now().isoformat()
    
    def finish(self, output_data: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """Завершить span"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.output_data = output_data
        self.error = error
        self.status = "error" if error else "completed"
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь для сохранения"""
        return {
            "span_id": self.span_id,
            "name": self.name,
            "span_type": self.span_type,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "input_data": json.dumps(self.input_data) if self.input_data else None,
            "output_data": json.dumps(self.output_data) if self.output_data else None,
            "metadata": json.dumps(self.metadata),
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at
        }


class TraceCollector:
    """Сборщик трассировки с SQLite хранилищем"""
    
    def __init__(self, db_path: str = "/data/trace.db"):
        self.db_path = db_path
        self.current_spans: Dict[str, TraceSpan] = {}
        self._init_database()
    
    def _init_database(self):
        """Инициализировать базу данных SQLite"""
        try:
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trace_spans (
                        span_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        span_type TEXT NOT NULL,
                        parent_id TEXT,
                        start_time REAL NOT NULL,
                        end_time REAL,
                        duration_ms REAL,
                        input_data TEXT,
                        output_data TEXT,
                        metadata TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Индексы для быстрого поиска
                conn.execute("CREATE INDEX IF NOT EXISTS idx_span_type ON trace_spans(span_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_id ON trace_spans(parent_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON trace_spans(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON trace_spans(status)")
                
                conn.commit()
            
            logger.info(f"✅ База данных трассировки инициализирована: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных трассировки: {e}")
    
    def start_span(self, name: str, span_type: str, parent_id: Optional[str] = None, 
                   input_data: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Начать новый span"""
        span_id = str(uuid.uuid4())
        span = TraceSpan(span_id, name, span_type, parent_id)
        span.input_data = input_data
        if metadata:
            span.metadata.update(metadata)
        
        self.current_spans[span_id] = span
        logger.debug(f"🔍 Начат span: {span_id} ({span_type}) - {name}")
        return span_id
    
    def finish_span(self, span_id: str, output_data: Optional[Dict[str, Any]] = None, 
                   error: Optional[str] = None):
        """Завершить span"""
        if span_id not in self.current_spans:
            logger.warning(f"Span {span_id} не найден для завершения")
            return
        
        span = self.current_spans[span_id]
        span.finish(output_data, error)
        
        # Сохранить в базу данных
        self._save_span(span)
        
        # Удалить из активных spans
        del self.current_spans[span_id]
        
        status_emoji = "❌" if error else "✅"
        logger.debug(f"{status_emoji} Завершен span: {span_id} - {span.duration_ms:.1f}ms")
    
    def _save_span(self, span: TraceSpan):
        """Сохранить span в базу данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Сериализуем словари в JSON строки
                input_data_json = json.dumps(span.input_data) if span.input_data else None
                output_data_json = json.dumps(span.output_data) if span.output_data else None
                metadata_json = json.dumps(span.metadata) if span.metadata else "{}"
                
                conn.execute("""
                    INSERT INTO trace_spans 
                    (span_id, name, span_type, parent_id, start_time, end_time, duration_ms, 
                     input_data, output_data, metadata, status, error, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    span.span_id, span.name, span.span_type, span.parent_id,
                    span.start_time, span.end_time, span.duration_ms,
                    input_data_json, output_data_json, metadata_json,
                    span.status, span.error, span.created_at
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения span {span.span_id}: {e}")
    
    def get_recent_spans(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить последние spans"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM trace_spans 
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,))
                
                spans = []
                for row in cursor.fetchall():
                    span_dict = dict(row)
                    # Парсим JSON поля
                    if span_dict.get('input_data'):
                        span_dict['input_data'] = json.loads(span_dict['input_data'])
                    if span_dict.get('output_data'):
                        span_dict['output_data'] = json.loads(span_dict['output_data'])
                    if span_dict.get('metadata'):
                        span_dict['metadata'] = json.loads(span_dict['metadata'])
                    
                    spans.append(span_dict)
                
                return spans
        except Exception as e:
            logger.error(f"❌ Ошибка получения spans: {e}")
            return []
    
    def get_span_tree(self, root_span_id: str) -> Dict[str, Any]:
        """Получить дерево spans начиная с корневого"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Получить корневой span
                cursor = conn.execute("SELECT * FROM trace_spans WHERE span_id = ?", (root_span_id,))
                root_row = cursor.fetchone()
                if not root_row:
                    return {}
                
                root_span = dict(root_row)
                if root_span.get('input_data'):
                    root_span['input_data'] = json.loads(root_span['input_data'])
                if root_span.get('output_data'):
                    root_span['output_data'] = json.loads(root_span['output_data'])
                if root_span.get('metadata'):
                    root_span['metadata'] = json.loads(root_span['metadata'])
                
                # Получить дочерние spans
                cursor = conn.execute("SELECT * FROM trace_spans WHERE parent_id = ?", (root_span_id,))
                children = []
                for row in cursor.fetchall():
                    child = dict(row)
                    if child.get('input_data'):
                        child['input_data'] = json.loads(child['input_data'])
                    if child.get('output_data'):
                        child['output_data'] = json.loads(child['output_data'])
                    if child.get('metadata'):
                        child['metadata'] = json.loads(child['metadata'])
                    children.append(child)
                
                root_span['children'] = children
                return root_span
        except Exception as e:
            logger.error(f"❌ Ошибка получения дерева spans: {e}")
            return {}


# Глобальный экземпляр сборщика трассировки
trace_collector = TraceCollector()


def get_trace_collector() -> TraceCollector:
    """Получить глобальный экземпляр сборщика трассировки"""
    return trace_collector


@contextmanager
def trace_span(name: str, span_type: str, parent_id: Optional[str] = None, 
               input_data: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None):
    """Контекстный менеджер для автоматического создания и завершения span"""
    span_id = trace_collector.start_span(name, span_type, parent_id, input_data, metadata)
    try:
        yield span_id
        trace_collector.finish_span(span_id)
    except Exception as e:
        trace_collector.finish_span(span_id, error=str(e))
        raise


class AgentsTraceMiddleware(BaseHTTPMiddleware):
    """Middleware для трассировки запросов к агентам"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.trace_collector = get_trace_collector()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Начать span для HTTP запроса
        span_id = self.trace_collector.start_span(
            name=f"{request.method} {request.url.path}",
            span_type="http_request",
            input_data={
                "method": request.method,
                "path": str(request.url.path),
                "query_params": dict(request.query_params),
                "headers": dict(request.headers)
            }
        )
        
        try:
            # Выполнить запрос
            response = await call_next(request)
            
            # Завершить span
            self.trace_collector.finish_span(span_id, output_data={
                "status_code": response.status_code,
                "headers": dict(response.headers)
            })
            
            return response
        except Exception as e:
            # Завершить span с ошибкой
            self.trace_collector.finish_span(span_id, error=str(e))
            raise


# Функции для удобного использования в других модулях
def trace_llm_call(model: str, prompt: str, response: str, duration_ms: float):
    """Трассировать вызов LLM"""
    span_id = trace_collector.start_span(
        name=f"LLM Call: {model}",
        span_type="llm",
        input_data={"model": model, "prompt": prompt},
        metadata={"model": model}
    )
    trace_collector.finish_span(
        span_id=span_id,
        output_data={"response": response, "duration_ms": duration_ms}
    )


def trace_tool_call(tool_name: str, arguments: Dict[str, Any], result: Any, duration_ms: float):
    """Трассировать вызов инструмента"""
    span_id = trace_collector.start_span(
        name=f"Tool Call: {tool_name}",
        span_type="tool",
        input_data={"tool_name": tool_name, "arguments": arguments},
        metadata={"tool_name": tool_name}
    )
    trace_collector.finish_span(
        span_id=span_id,
        output_data={"result": result, "duration_ms": duration_ms}
    ) 