#!/usr/bin/env python3
"""
Neo4j backend для векторного поиска по DiaryEntry
"""

import time
import logging
import urllib.parse
import urllib.request
import json
from typing import Dict, Any, List, Optional

from ..graphiti_config import get_graphiti_config

logger = logging.getLogger(__name__)


class Neo4jDiaryBackend:
    """Backend для векторного поиска по DiaryEntry в Neo4j через Graphiti API"""
    
    def __init__(self, base_url: str = "http://graphiti:7878"):
        self.base_url = base_url.rstrip('/')
        self.config = get_graphiti_config()
        logger.info(f"🧠 Neo4jDiaryBackend инициализирован: {base_url}")
    
    async def fetch_similar_successes(self, 
                                     query: str, 
                                     user_id: str = None,
                                     limit: int = 5,
                                     max_duration_ms: int = 150) -> List[Dict[str, Any]]:
        """
        Векторный поиск успешных DiaryEntry записей
        
        Args:
            query: Поисковый запрос (описание проблемы)
            user_id: ID пользователя для фильтрации (опционально)
            limit: Максимальное количество результатов
            max_duration_ms: Максимальное время выполнения в мс
            
        Returns:
            Список успешных DiaryEntry с информацией о решениях
        """
        start_time = time.time()
        
        try:
            # URL-кодируем параметр поиска
            encoded_query = urllib.parse.quote(query)
            
            # Используем векторный поиск через Graphiti API
            # Фильтруем по DiaryEntry с source != 'self' (не рефлексии, а успешные действия)
            search_url = f"{self.base_url}/nodes?search={encoded_query}&limit={limit * 2}"  # Берем больше для фильтрации
            
            response = urllib.request.urlopen(search_url)
            
            if response.status != 200:
                error_text = response.read().decode()
                logger.error(f"❌ Ошибка поиска DiaryEntry: {response.status} - {error_text}")
                return []
            
            data = json.loads(response.read().decode())
            successful_entries = []
            
            for node in data.get("nodes", []):
                # Проверяем время выполнения
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms > max_duration_ms:
                    logger.warning(f"⏱️ Поиск DiaryEntry превысил {max_duration_ms}ms, прерываем")
                    break
                
                # Фильтруем DiaryEntry
                if node.get("type") != "DiaryEntry":
                    continue
                
                properties = node.get("properties", {})
                
                # Пропускаем рефлексии (source='self')
                if properties.get("source") == "self":
                    continue
                
                # Фильтруем по пользователю если указан
                if user_id and properties.get("user_id") != user_id:
                    continue
                
                # Ищем записи которые содержат решения или успешные действия
                content = properties.get("content", "")
                if not self._is_success_entry(content, properties):
                    continue
                
                # Парсим контекст если есть
                context = {}
                if "context" in properties:
                    try:
                        context = json.loads(properties["context"]) if isinstance(properties["context"], str) else properties["context"]
                    except (json.JSONDecodeError, TypeError):
                        context = {}
                
                entry = {
                    "id": node.get("id"),
                    "content": content,
                    "user_id": properties.get("user_id"),
                    "source": properties.get("source", "unknown"),
                    "timestamp": properties.get("timestamp"),
                    "context": context,
                    "tags": properties.get("tags", []),
                    "similarity": node.get("score", 0.8),
                    "insights": self._extract_success_insights(content, context)
                }
                
                successful_entries.append(entry)
                
                # Достигли лимита
                if len(successful_entries) >= limit:
                    break
            
            # Сортируем по релевантности
            successful_entries.sort(key=lambda x: x["similarity"], reverse=True)
            
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"🔍 Найдено {len(successful_entries)} успешных DiaryEntry за {elapsed_ms:.1f}ms")
            
            return successful_entries[:limit]
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"❌ Ошибка поиска DiaryEntry: {e} (за {elapsed_ms:.1f}ms)")
            return []
    
    def _is_success_entry(self, content: str, properties: Dict[str, Any]) -> bool:
        """Определяет является ли запись успешной"""
        content_lower = content.lower()
        
        # Ключевые слова успеха
        success_keywords = [
            "решение", "решил", "решена", "успешно", "работает", "помогло",
            "получилось", "удалось", "исправил", "исправлено", "fixed",
            "solved", "success", "working", "complete", "завершено"
        ]
        
        # Ключевые слова неудач (исключаем) - только если нет слов успеха
        failure_keywords = [
            "не работает", "ошибка", "проблема", "не получается", "failed",
            "error", "не удалось", "не решено", "broke", "broken"
        ]
        
        # Сначала проверяем на успех
        success_found = False
        for keyword in success_keywords:
            if keyword in content_lower:
                success_found = True
                break
        
        # Если найден успех, проверяем что это не ложный позитив
        if success_found:
            # Проверяем на отрицания типа "не решена", "not working"
            negation_patterns = [
                "не решена", "не решено", "не решил", "не исправлена", "не исправлено",
                "не работает", "не получилось", "не удалось", "не завершено",
                "not working", "not solved", "not fixed", "not complete"
            ]
            
            for pattern in negation_patterns:
                if pattern in content_lower:
                    return False
            return True
        
        # Проверяем теги
        tags = properties.get("tags", [])
        if isinstance(tags, list):
            if "success" in tags or "solution" in tags or "resolved" in tags:
                return True
        
        # Проверяем источник
        source = properties.get("source", "")
        if source in ["user", "agent", "system"] and len(content) > 20:
            # Если это не рефлексия и есть содержательный текст
            return True
        
        return False
    
    def _extract_success_insights(self, content: str, context: Dict[str, Any]) -> List[str]:
        """Извлекает инсайты из успешной записи"""
        insights = []
        content_lower = content.lower()
        
        # Анализируем содержание
        if "инструмент" in content_lower or "tool" in content_lower or "использовал" in content_lower:
            insights.append("tool_usage")
        
        if "поиск" in content_lower or "search" in content_lower:
            insights.append("search_strategy")
        
        if "память" in content_lower or "memory" in content_lower or "памяти" in content_lower:
            insights.append("memory_usage")
        
        if "контекст" in content_lower or "context" in content_lower:
            insights.append("context_important")
        
        if "данные" in content_lower or "data" in content_lower or "данных" in content_lower or "получения" in content_lower:
            insights.append("data_access")
        
        if "алгоритм" in content_lower or "algorithm" in content_lower:
            insights.append("algorithmic_approach")
        
        # Анализируем контекст
        if context:
            if context.get("tools_used"):
                insights.append("tool_combination")
                # Если в контексте есть инструменты, добавляем tool_usage если его еще нет
                if "tool_usage" not in insights:
                    insights.append("tool_usage")
            
            if context.get("strategy"):
                insights.append("strategic_approach")
        
        return insights
    
    async def fetch_user_success_patterns(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получение паттернов успешных решений конкретного пользователя
        
        Args:
            user_id: ID пользователя
            limit: Максимальное количество записей
            
        Returns:
            Список успешных паттернов пользователя
        """
        try:
            # Поиск всех DiaryEntry пользователя
            search_url = f"{self.base_url}/nodes?user_id={user_id}&type=DiaryEntry&limit={limit * 2}"
            
            response = urllib.request.urlopen(search_url)
            if response.status != 200:
                return []
            
            data = json.loads(response.read().decode())
            patterns = []
            
            for node in data.get("nodes", []):
                properties = node.get("properties", {})
                
                # Пропускаем рефлексии
                if properties.get("source") == "self":
                    continue
                
                content = properties.get("content", "")
                if not self._is_success_entry(content, properties):
                    continue
                
                context = {}
                if "context" in properties:
                    try:
                        context = json.loads(properties["context"]) if isinstance(properties["context"], str) else properties["context"]
                    except (json.JSONDecodeError, TypeError):
                        context = {}
                
                pattern = {
                    "id": node.get("id"),
                    "content": content,
                    "timestamp": properties.get("timestamp"),
                    "context": context,
                    "insights": self._extract_success_insights(content, context),
                    "success_score": self._calculate_success_score(content, context)
                }
                
                patterns.append(pattern)
            
            # Сортируем по успешности и времени
            patterns.sort(key=lambda x: (x["success_score"], x.get("timestamp", 0)), reverse=True)
            
            logger.info(f"📊 Найдено {len(patterns)} успешных паттернов для пользователя {user_id}")
            return patterns[:limit]
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения паттернов пользователя {user_id}: {e}")
            return []
    
    def _calculate_success_score(self, content: str, context: Dict[str, Any]) -> float:
        """Рассчитывает оценку успешности записи"""
        score = 0.5  # Базовая оценка
        content_lower = content.lower()
        
        # Бонусы за ключевые слова
        success_words = ["успешно", "решено", "работает", "помогло", "получилось"]
        for word in success_words:
            if word in content_lower:
                score += 0.1
        
        # Бонус за длину (более детальные записи)
        if len(content) > 100:
            score += 0.1
        if len(content) > 300:
            score += 0.1
        
        # Бонус за контекст
        if context:
            if context.get("tools_used"):
                score += 0.1
            if context.get("strategy"):
                score += 0.1
            if context.get("result") == "success":
                score += 0.2
        
        return min(score, 1.0)  # Максимум 1.0
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка работоспособности"""
        try:
            response = urllib.request.urlopen(f"{self.base_url}/health")
            if response.status == 200:
                data = json.loads(response.read().decode())
                return {"status": "healthy", "backend": "neo4j", "data": data}
            else:
                return {"status": "unhealthy", "error": f"HTTP {response.status}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# Глобальный экземпляр
neo4j_diary_backend = Neo4jDiaryBackend()