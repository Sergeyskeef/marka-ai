#!/usr/bin/env python3
"""
Middleware для сбора метрик
"""

import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from langchain_api.core.metrics import metrics_manager

logger = logging.getLogger(__name__)

class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware для автоматического сбора метрик"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Получаем информацию о запросе
        endpoint = request.url.path
        method = request.method
        
        try:
            # Выполняем запрос
            response = await call_next(request)
            
            # Записываем метрики успешного запроса
            duration = time.time() - start_time
            metrics_manager.record_request(
                endpoint=endpoint,
                method=method,
                status=response.status_code,
                duration=duration
            )
            
            # Специальные метрики для чата
            if endpoint == "/chat/ask":
                mode = "unknown"
                try:
                    body = await request.json()
                    mode = body.get("mode", "chat")
                except:
                    pass
                
                metrics_manager.record_chat_request(
                    mode=mode,
                    status="success" if response.status_code == 200 else "error"
                )
            
            # Специальные метрики для инструментов
            if endpoint.startswith("/tools/execute/"):
                tool_name = endpoint.split("/")[-1]
                metrics_manager.record_tool_execution(
                    tool_name=tool_name,
                    status="success" if response.status_code == 200 else "error"
                )
            
            # Специальные метрики для памяти
            if endpoint in ["/memory", "/search"]:
                operation = "add" if endpoint == "/memory" else "search"
                metrics_manager.record_memory_operation(
                    operation=operation,
                    status="success" if response.status_code == 200 else "error"
                )
            
            return response
            
        except Exception as e:
            # Записываем метрики ошибки
            duration = time.time() - start_time
            metrics_manager.record_request(
                endpoint=endpoint,
                method=method,
                status=500,
                duration=duration
            )
            
            logger.error(f"Ошибка в middleware: {e}")
            raise 