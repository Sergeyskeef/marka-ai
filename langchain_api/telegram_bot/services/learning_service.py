"""
Сервис для работы с системой обучения
"""

import logging
from typing import Dict, Any, Optional
import httpx

from ..config import bot_config

logger = logging.getLogger(__name__)


class LearningService:
    """Сервис для работы с REAP циклом обучения"""
    
    def __init__(self):
        self.api_url = bot_config.APP_HOST
        self.timeout = httpx.Timeout(bot_config.REQUEST_TIMEOUT)
        
    async def start_learning_cycle(
        self,
        user_id: str,
        episode_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Запуск цикла обучения
        
        Args:
            user_id: ID пользователя
            episode_id: ID эпизода для анализа (опционально)
            
        Returns:
            Результат запуска обучения
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/api/v1/learning/start",
                    json={
                        "user_id": user_id,
                        "episode_id": episode_id
                    }
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error starting learning: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error starting learning: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_learning_status(self, user_id: str) -> Dict[str, Any]:
        """
        Получение статуса обучения
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Статус текущего обучения
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/api/v1/learning/status",
                    params={"user_id": user_id}
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting learning status: {e}")
            return {
                "is_running": False,
                "last_run": None,
                "total_cycles": 0
            }
        except Exception as e:
            logger.error(f"Error getting learning status: {e}")
            return {
                "is_running": False,
                "last_run": None,
                "total_cycles": 0
            }
    
    async def get_insights(self, user_id: str, limit: int = 5) -> Dict[str, Any]:
        """
        Получение последних инсайтов из обучения
        
        Args:
            user_id: ID пользователя
            limit: Количество инсайтов
            
        Returns:
            Список инсайтов и рекомендаций
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/api/v1/learning/insights",
                    params={
                        "user_id": user_id,
                        "limit": limit
                    }
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting insights: {e}")
            return {
                "insights": [],
                "recommendations": []
            }
        except Exception as e:
            logger.error(f"Error getting insights: {e}")
            return {
                "insights": [],
                "recommendations": []
            }