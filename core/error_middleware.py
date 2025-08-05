#!/usr/bin/env python3
"""
Error Middleware с централизованной обработкой ошибок и retry логикой
"""

import time
import logging
import asyncio
import json
from typing import Callable
from functools import wraps
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import httpx

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware для централизованной обработки ошибок"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
            
        except HTTPException as e:
            # HTTP исключения обрабатываем как есть
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": e.detail,
                    "status_code": e.status_code,
                    "path": request.url.path
                }
            )
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout error on {request.url.path}")
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Request timeout",
                    "status_code": 504,
                    "path": request.url.path
                }
            )
            
        except Exception as e:
            # Логируем неожиданные ошибки
            logger.error(f"Unhandled error on {request.url.path}: {str(e)}", exc_info=True)
            
            # Возвращаем общую ошибку
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(e) if logger.level <= logging.DEBUG else "An unexpected error occurred",
                    "status_code": 500,
                    "path": request.url.path
                }
            )


def retry_on_failure(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)
):
    """
    Декоратор для повторных попыток при ошибках внешних HTTP запросов
    
    Args:
        max_retries: Максимальное количество попыток
        initial_delay: Начальная задержка между попытками (секунды)
        backoff_factor: Множитель для экспоненциальной задержки
        exceptions: Кортеж исключений, при которых делать retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"All {max_retries} attempts failed for {func.__name__}: {str(e)}"
                        )
            
            # Если все попытки провалились, бросаем последнее исключение
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class RetryableHTTPClient:
    """HTTP клиент с встроенной retry логикой"""
    
    def __init__(self, 
                 timeout: float = 30.0,
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 backoff_factor: float = 2.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.client = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            http2=True
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    @retry_on_failure()
    async def get(self, url: str, **kwargs):
        """GET запрос с retry"""
        return await self.client.get(url, **kwargs)
    
    @retry_on_failure()
    async def post(self, url: str, **kwargs):
        """POST запрос с retry"""
        return await self.client.post(url, **kwargs)
    
    @retry_on_failure()
    async def put(self, url: str, **kwargs):
        """PUT запрос с retry"""
        return await self.client.put(url, **kwargs)
    
    @retry_on_failure()
    async def delete(self, url: str, **kwargs):
        """DELETE запрос с retry"""
        return await self.client.delete(url, **kwargs)


def handle_errors(func: Callable) -> Callable:
    """
    Декоратор для обработки ошибок в endpoint'ах
    
    Преобразует различные типы исключений в HTTPException
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
            
        except HTTPException:
            # HTTPException пробрасываем как есть
            raise
            
        except ValueError as e:
            # Ошибки валидации
            raise HTTPException(status_code=400, detail=str(e))
            
        except PermissionError as e:
            # Ошибки доступа
            raise HTTPException(status_code=403, detail=str(e))
            
        except FileNotFoundError as e:
            # Ресурс не найден
            raise HTTPException(status_code=404, detail=str(e))
            
        except asyncio.TimeoutError:
            # Таймауты
            raise HTTPException(status_code=504, detail="Request timeout")
            
        except Exception as e:
            # Все остальные ошибки
            logger.error(f"Unhandled error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    
    return wrapper