#!/usr/bin/env python3
"""
Система саморефлексии агента
"""

import time
import uuid
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from ..graphiti_config import get_graphiti_config
from neo4j import GraphDatabase, Driver
from langchain_api.utils.openai_proxy_client import chat_model
from langchain.schema import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


class ReflexionAgent:
    """Агент с возможностью саморефлексии"""
    
    def __init__(self):
        self.config = get_graphiti_config()
        self._driver: Optional[Driver] = None
        logger.info("🧠 ReflexionAgent инициализирован")
    
    @property
    def driver(self) -> Driver:
        """Ленивая инициализация драйвера Neo4j"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_username, self.config.neo4j_password)
            )
        return self._driver
    
    def close(self):
        """Закрытие соединения с Neo4j"""
        if self._driver:
            self._driver.close()
            self._driver = None
    
    async def self_reflect(self, 
                          user_question: str,
                          attempt_result: str,
                          error_details: Optional[str] = None,
                          tool_outcomes: Optional[list] = None,
                          user_id: str = "default_user") -> Dict[str, Any]:
        """
        Проведение саморефлексии после неудачной попытки
        
        Args:
            user_question: Исходный вопрос пользователя
            attempt_result: Результат попытки ответа
            error_details: Детали ошибки, если произошла
            tool_outcomes: Список результатов выполнения инструментов
            user_id: ID пользователя
            
        Returns:
            Dict с результатом рефлексии и записью в дневник
        """
        try:
            # Формируем промпт для саморефлексии
            reflection_prompt = self._build_reflection_prompt(
                user_question, attempt_result, error_details, tool_outcomes
            )
            
            # Получаем рефлексию от LLM
            reflection_result = await self._get_llm_reflection_with_status(reflection_prompt)
            reflection_content = reflection_result["content"]
            llm_success = reflection_result["success"]
            
            # Сохраняем запись в дневник
            diary_entry = await self._save_diary_entry(
                user_id=user_id,
                content=reflection_content,
                source="self",
                context={
                    "user_question": user_question,
                    "attempt_result": attempt_result,
                    "error_details": error_details,
                    "tool_outcomes": tool_outcomes
                }
            )
            
            if llm_success and diary_entry.get("success", False):
                logger.info(f"✅ Саморефлексия выполнена, создана запись в дневнике: {diary_entry['id']}")
                return {
                    "success": True,
                    "reflection": reflection_content,
                    "diary_entry": diary_entry,
                    "insights": self._extract_insights(reflection_content)
                }
            else:
                logger.warning(f"⚠️ Саморефлексия частично выполнена. LLM: {llm_success}, Дневник: {diary_entry.get('success', False)}")
                return {
                    "success": False,
                    "reflection": reflection_content,
                    "diary_entry": diary_entry,
                    "insights": self._extract_insights(reflection_content) if llm_success else [],
                    "error": "Partial failure in reflection process"
                }
            
        except Exception as e:
            logger.error(f"❌ Ошибка в саморефлексии: {e}")
            return {
                "success": False,
                "error": str(e),
                "reflection": "",
                "diary_entry": None,
                "insights": []
            }
    
    def _build_reflection_prompt(self, 
                               user_question: str,
                               attempt_result: str,
                               error_details: Optional[str],
                               tool_outcomes: Optional[list]) -> str:
        """Построение промпта для саморефлексии"""
        prompt = f"""Ты - ИИ-агент, который анализирует свои неудачные попытки ответить на вопросы пользователей.

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{user_question}

МОЯ ПОПЫТКА ОТВЕТА:
{attempt_result}
"""
        
        if error_details:
            prompt += f"""
ДЕТАЛИ ОШИБКИ:
{error_details}
"""
        
        if tool_outcomes:
            prompt += f"""
РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ:
{self._format_tool_outcomes(tool_outcomes)}
"""
        
        prompt += """
Проанализируй эту ситуацию и напиши короткий анализ (1-2 абзаца):

1. Что пошло не так? (анализ проблемы)
2. Что можно попробовать в следующий раз? (рекомендации)

Будь конкретен и конструктивен в своих рекомендациях.
"""
        
        return prompt
    
    def _format_tool_outcomes(self, tool_outcomes: list) -> str:
        """Форматирование результатов инструментов"""
        if not tool_outcomes:
            return "Инструменты не использовались"
        
        formatted = []
        for outcome in tool_outcomes:
            formatted.append(f"- {outcome.get('tool_name', 'Unknown')}: {outcome.get('status', 'unknown')} "
                           f"({outcome.get('duration_ms', 0)}ms)")
            if outcome.get('error'):
                formatted.append(f"  Ошибка: {outcome['error']}")
        
        return "\n".join(formatted)
    
    async def _get_llm_reflection(self, prompt: str) -> str:
        """Получение рефлексии от LLM (совместимость)"""
        result = await self._get_llm_reflection_with_status(prompt)
        return result["content"]
    
    async def _get_llm_reflection_with_status(self, prompt: str) -> Dict[str, Any]:
        """Получение рефлексии от LLM с информацией о статусе"""
        try:
            messages = [
                SystemMessage(content="Ты - система саморефлексии ИИ-агента. Анализируй свои ошибки конструктивно и четко."),
                HumanMessage(content=prompt)
            ]
            
            model = chat_model()
            response = await model.ainvoke(messages)
            return {
                "success": True,
                "content": response.content.strip()
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения рефлексии от LLM: {e}")
            return {
                "success": False,
                "content": f"Не удалось получить рефлексию: {str(e)}"
            }
    
    async def _save_diary_entry(self, 
                              user_id: str,
                              content: str,
                              source: str = "self",
                              context: Optional[Dict] = None) -> Dict[str, Any]:
        """Сохранение записи в дневник"""
        entry_id = f"diary_{uuid.uuid4().hex[:12]}"
        timestamp = time.time()
        
        try:
            with self.driver.session() as session:
                # Создаем запись в дневнике
                query = """
                MERGE (u:User {id: $user_id})
                CREATE (d:DiaryEntry {
                    id: $entry_id,
                    user_id: $user_id,
                    content: $content,
                    source: $source,
                    timestamp: $timestamp,
                    created_at: datetime(),
                    context: $context,
                    tags: ['reflexion', 'self-analysis']
                })
                MERGE (u)-[:WRITES]->(d)
                RETURN d
                """
                
                result = session.run(query, {
                    "user_id": user_id,
                    "entry_id": entry_id,
                    "content": content,
                    "source": source,
                    "timestamp": timestamp,
                    "context": json.dumps(context or {})
                })
                
                record = result.single()
                if record:
                    logger.info(f"✅ Запись в дневнике создана: {entry_id}")
                    return {
                        "id": entry_id,
                        "user_id": user_id,
                        "content": content,
                        "source": source,
                        "timestamp": timestamp,
                        "success": True
                    }
                else:
                    raise Exception("Не удалось создать запись в дневнике")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в дневник: {e}")
            return {
                "id": entry_id,
                "success": False,
                "error": str(e)
            }
    
    def _extract_insights(self, reflection_content: str) -> list:
        """Извлечение ключевых инсайтов из рефлексии"""
        insights = []
        
        # Простое извлечение ключевых фраз
        content_lower = reflection_content.lower()
        
        if "не хватает" in content_lower or "недостаточно" in content_lower:
            insights.append("need_more_info")
        
        if "попробовать" in content_lower or "стоит" in content_lower:
            insights.append("try_different_approach")
        
        if "ошибка" in content_lower or "проблема" in content_lower:
            insights.append("error_analysis")
        
        if "инструмент" in content_lower or "метод" in content_lower:
            insights.append("tool_related")
        
        return insights
    
    async def get_recent_reflections(self, user_id: str, limit: int = 5) -> list:
        """Получение последних записей рефлексии пользователя"""
        try:
            with self.driver.session() as session:
                query = """
                MATCH (u:User {id: $user_id})-[:WRITES]->(d:DiaryEntry)
                WHERE d.source = 'self' AND 'reflexion' IN d.tags
                RETURN d
                ORDER BY d.timestamp DESC
                LIMIT $limit
                """
                
                result = session.run(query, {"user_id": user_id, "limit": limit})
                return [record["d"] for record in result]
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения записей рефлексии: {e}")
            return []
    
    async def get_reflection_stats(self, user_id: str) -> Dict[str, Any]:
        """Получение статистики рефлексии пользователя"""
        try:
            with self.driver.session() as session:
                query = """
                MATCH (u:User {id: $user_id})-[:WRITES]->(d:DiaryEntry)
                WHERE d.source = 'self' AND 'reflexion' IN d.tags
                WITH d
                RETURN 
                    count(d) as total_reflections,
                    max(d.timestamp) as last_reflection_time,
                    min(d.timestamp) as first_reflection_time
                """
                
                result = session.run(query, {"user_id": user_id})
                record = result.single()
                
                if record:
                    return {
                        "total_reflections": record["total_reflections"],
                        "last_reflection_time": record["last_reflection_time"],
                        "first_reflection_time": record["first_reflection_time"]
                    }
                else:
                    return {"total_reflections": 0}
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики рефлексии: {e}")
            return {"error": str(e)}


# Глобальный экземпляр агента рефлексии
reflexion_agent = ReflexionAgent()