"""Сервис для проверки здоровья приложения."""

import logging
import time
from typing import Dict, Any
import httpx
from weaviate import WeaviateClient
import os

logger = logging.getLogger(__name__)

class HealthService:
    """Сервис для проверки здоровья приложения."""
    
    def __init__(self, weaviate_client: WeaviateClient):
        self.weaviate_client = weaviate_client
        self.start_time = time.time()
        self.last_check = {
            "weaviate": None,
            "openai": None
        }
    
    async def check_weaviate(self) -> Dict[str, Any]:
        """Проверка доступности Weaviate."""
        try:
            is_ready = self.weaviate_client.is_ready()
            self.last_check["weaviate"] = time.time()
            return {
                "status": "healthy" if is_ready else "unhealthy",
                "latency": time.time() - self.last_check["weaviate"]
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке Weaviate: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def check_openai(self) -> Dict[str, Any]:
        """Проверка доступности OpenAI API."""
        try:
            async with httpx.AsyncClient() as client:
                start_time = time.time()
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
                    timeout=5.0
                )
                latency = time.time() - start_time
                self.last_check["openai"] = start_time
                
                return {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "latency": latency,
                    "status_code": response.status_code
                }
        except Exception as e:
            logger.error(f"Ошибка при проверке OpenAI API: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def get_health(self) -> Dict[str, Any]:
        """Получить полный отчет о здоровье системы."""
        weaviate_status = await self.check_weaviate()
        openai_status = await self.check_openai()
        
        uptime = time.time() - self.start_time
        
        return {
            "status": "healthy" if all(s["status"] == "healthy" for s in [weaviate_status, openai_status]) else "unhealthy",
            "uptime": uptime,
            "version": "0.6",
            "services": {
                "weaviate": weaviate_status,
                "openai": openai_status
            },
            "last_check": self.last_check
        } 