"""
Сервис для интеграции с системой чата
"""

import logging
from typing import Dict, Any, Optional
import httpx

from ..config import bot_config

logger = logging.getLogger(__name__)


class ChatService:
    """
    Сервис для взаимодействия с enhanced_chat API
    """
    
    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = base_url or bot_config.APP_HOST
        self.timeout = timeout or bot_config.REQUEST_TIMEOUT
        
        # Создаем HTTP клиент с настройками
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers={"Content-Type": "application/json"}
        )
    
    async def close(self):
        """Закрыть HTTP клиент"""
        await self.client.aclose()
    
    async def ask_question(
        self,
        question: str,
        user_id: str,
        chat_id: Optional[int] = None,
        mode: str = "chat"
    ) -> Dict[str, Any]:
        """
        Отправить вопрос в enhanced_chat
        
        Args:
            question: Текст вопроса
            user_id: ID пользователя
            chat_id: ID чата (опционально)
            mode: Режим работы (chat, task, analysis)
            
        Returns:
            Ответ от API
        """
        try:
            # Подготавливаем данные
            payload = {
                "question": question,
                "user_id": str(user_id),
                "mode": mode
            }
            
            if chat_id is not None:
                payload["chat_id"] = chat_id
            
            # Используем новый endpoint если включен enhanced_chat
            if bot_config.USE_ENHANCED_CHAT:
                endpoint = "/chat/enhanced"
            else:
                endpoint = "/chat/ask"
            
            logger.info(f"Sending request to {endpoint}: user={user_id}, mode={mode}")
            
            # Отправляем запрос
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            # Логируем использование инструментов
            if data.get("tool_calls"):
                tools_used = [tc.get("name") for tc in data["tool_calls"]]
                logger.info(f"Tools used: {tools_used}")
            
            return data
            
        except httpx.TimeoutException:
            logger.error(f"Timeout while calling {endpoint}")
            return {
                "error": True,
                "content": "⏱️ Превышено время ожидания ответа. Попробуйте еще раз.",
                "metadata": {"error": "timeout"}
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            return {
                "error": True,
                "content": f"❌ Ошибка сервера: {e.response.status_code}",
                "metadata": {"error": f"http_{e.response.status_code}"}
            }
            
        except Exception as e:
            logger.error(f"Unexpected error in ask_question: {str(e)}")
            return {
                "error": True,
                "content": "😔 Произошла неожиданная ошибка. Попробуйте позже.",
                "metadata": {"error": str(e)}
            }
    
    async def get_chat_modes(self) -> list[Dict[str, str]]:
        """Получить доступные режимы чата"""
        return [
            {"mode": "chat", "name": "💬 Обычный чат", "description": "Дружеская беседа"},
            {"mode": "task", "name": "📋 Режим задач", "description": "Помощь в выполнении задач"},
            {"mode": "analysis", "name": "🔍 Анализ", "description": "Глубокий анализ темы"},
        ]
    
    def format_response(self, response: Dict[str, Any]) -> str:
        """
        Форматировать ответ для отображения в Telegram
        
        Args:
            response: Ответ от API
            
        Returns:
            Отформатированный текст
        """
        if response.get("error"):
            return response.get("content", "Произошла ошибка")
        
        # Основной ответ
        content = response.get("content", response.get("answer", ""))
        
        # Добавляем информацию об использованных инструментах
        if response.get("tool_calls") and len(response["tool_calls"]) > 0:
            tools_info = "\n\n🔧 *Использованные инструменты:*\n"
            for tool in response["tool_calls"]:
                tool_name = tool.get("name", "unknown")
                tools_info += f"• {self._format_tool_name(tool_name)}\n"
            
            content += tools_info
        
        # Добавляем метаданные если есть
        metadata = response.get("metadata", {})
        if metadata.get("tokens_used"):
            content += f"\n\n_Токенов использовано: {metadata['tokens_used']}_"
        
        return content
    
    def _format_tool_name(self, tool_name: str) -> str:
        """Форматировать имя инструмента для отображения"""
        tool_names = {
            "search_memory": "🔍 Поиск в памяти",
            "save_to_memory": "💾 Сохранение в память",
            "remember_fact": "📝 Запоминание факта",
            "save_fact": "📌 Сохранение факта",
            "vector_search": "🔎 Векторный поиск",
            "start_learning_cycle": "🔄 Запуск цикла обучения",
            "analyze_skill_usage": "📊 Анализ навыков",
        }
        return tool_names.get(tool_name, tool_name)