"""
Сервис для работы с памятью
"""

import logging
from typing import Dict, Any, List, Optional
import httpx

from ..config import bot_config

logger = logging.getLogger(__name__)


class MemoryService:
    """Сервис для работы с памятью через API"""
    
    def __init__(self):
        self.api_url = bot_config.APP_HOST
        self.timeout = httpx.Timeout(bot_config.REQUEST_TIMEOUT)
        
    async def search_memory(
        self, 
        query: str, 
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Поиск в памяти
        
        Args:
            query: Поисковый запрос
            user_id: ID пользователя
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных воспоминаний
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/api/v1/memory/search",
                    json={
                        "query": query,
                        "user_id": user_id,
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching memory: {e}")
            return []
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []
    
    async def add_memory(
        self,
        memory_type: str,
        content: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Добавление воспоминания
        
        Args:
            memory_type: Тип памяти (fact, episode, skill)
            content: Содержимое
            user_id: ID пользователя
            metadata: Дополнительные метаданные
            
        Returns:
            True если успешно добавлено
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/api/v1/memory/add",
                    json={
                        "type": memory_type,
                        "content": content,
                        "user_id": user_id,
                        "metadata": metadata or {}
                    }
                )
                response.raise_for_status()
                return True
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error adding memory: {e}")
            return False
        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            return False
    
    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Получение статистики памяти
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Статистика памяти
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.api_url}/api/v1/memory/stats",
                    params={"user_id": user_id}
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting stats: {e}")
            return {
                "total": 0,
                "facts": 0,
                "episodes": 0,
                "skills": 0
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "total": 0,
                "facts": 0,
                "episodes": 0,
                "skills": 0
            }
    
    async def clear_memory(self, user_id: str, memory_type: Optional[str] = None) -> bool:
        """
        Очистка памяти
        
        Args:
            user_id: ID пользователя
            memory_type: Тип памяти для очистки (опционально)
            
        Returns:
            True если успешно очищено
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {"user_id": user_id}
                if memory_type:
                    params["type"] = memory_type
                    
                response = await client.delete(
                    f"{self.api_url}/api/v1/memory/clear",
                    params=params
                )
                response.raise_for_status()
                return True
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error clearing memory: {e}")
            return False
        except Exception as e:
            logger.error(f"Error clearing memory: {e}")
            return False