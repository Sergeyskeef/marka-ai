"""
Двух-шаговый цикл агента с рефлексией.

Этот модуль реализует алгоритм попыток ответа агента с возможностью
получения подсказок из прошлого опыта при неудаче.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from langchain_core.messages import SystemMessage, HumanMessage

from langchain_api.core.agent.reflexion import ReflexionAgent
from langchain_api.core.graphiti.backend_neo4j import neo4j_diary_backend
from langchain_api.core.metrics.outcome_logger import outcome_logger
from langchain_api.core.prometheus_metrics import metrics_manager
from langchain_api.utils.openai_proxy_client import chat_model


logger = logging.getLogger(__name__)


class AgentRunner:
    """Двух-шаговый цикл агента с рефлексией"""
    
    def __init__(self):
        self.reflexion_agent = ReflexionAgent()
        self.max_attempts = 2  # Максимум попыток во избежание бесконечного цикла
        
    async def try_answer(self, 
                        question: str, 
                        user_id: str = "default_user",
                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Двух-шаговый цикл ответа агента:
        1. Первая попытка ответа
        2. Если неудача - ищем подсказки из прошлого опыта
        3. Вторая попытка с учетом подсказок
        
        Args:
            question: Вопрос пользователя
            user_id: ID пользователя
            context: Дополнительный контекст
            
        Returns:
            Dict с результатом попытки ответа
        """
        start_time = time.time()
        attempts = []
        final_success = False
        
        try:
            # Попытка 1: Прямой ответ
            logger.info(f"🔄 Попытка 1: Прямой ответ на вопрос '{question[:50]}...'")
            
            first_attempt = await self._attempt_answer(
                question=question,
                attempt_number=1,
                hints=None,
                user_id=user_id,
                context=context
            )
            attempts.append(first_attempt)
            
            # Оцениваем результат первой попытки
            first_success = self._evaluate_answer_quality(first_attempt["answer"], question)
            
            if first_success:
                logger.info("✅ Первая попытка успешна")
                final_success = True
                
                # Логируем успешный исход
                outcome_logger.log_success(
                    tool_call_id=f"try_answer_{int(time.time())}",
                    tool_name="agent_try_answer",
                    duration_ms=int((time.time() - start_time) * 1000),
                    details=f"Успех с первой попытки на вопрос: {question[:100]}"
                )
                
                # Логируем метрику успешной рефлексии (без рефлексии)
                metrics_manager.record_reflexion_attempt("success")
                
                return {
                    "success": True,
                    "answer": first_attempt["answer"],
                    "attempts": attempts,
                    "final_attempt": 1,
                    "used_reflexion": False,
                    "processing_time_ms": int((time.time() - start_time) * 1000)
                }
            
            # Попытка 2: С подсказками из рефлексии
            logger.info("⚠️ Первая попытка неудачна, ищем подсказки...")
            
            # Выполняем саморефлексию по первой попытке
            reflexion_result = await self.reflexion_agent.self_reflect(
                user_question=question,
                attempt_result=first_attempt["answer"],
                error_details=first_attempt.get("error"),
                tool_outcomes=None,  # TODO: В будущем можно добавить tool outcomes
                user_id=user_id
            )
            
            # Ищем похожие успешные случаи
            hints = await self._fetch_hints(question, user_id)
            
            logger.info(f"🔍 Найдено {len(hints)} подсказок из прошлого опыта")
            
            # Вторая попытка с подсказками
            second_attempt = await self._attempt_answer(
                question=question,
                attempt_number=2,
                hints=hints,
                user_id=user_id,
                context=context,
                reflexion_insights=reflexion_result.get("insights", [])
            )
            attempts.append(second_attempt)
            
            # Оцениваем результат второй попытки
            second_success = self._evaluate_answer_quality(second_attempt["answer"], question)
            
            if second_success:
                logger.info("✅ Вторая попытка успешна")
                final_success = True
                
                # Логируем успешный исход рефлексии
                outcome_logger.log_success(
                    tool_call_id=f"try_answer_reflexion_{int(time.time())}",
                    tool_name="agent_try_answer_with_reflexion",
                    duration_ms=int((time.time() - start_time) * 1000),
                    details=f"Успех со второй попытки с рефлексией на вопрос: {question[:100]}"
                )
                
                # Логируем метрику успешной рефлексии
                metrics_manager.record_reflexion_attempt("success")
            else:
                logger.warning("❌ Вторая попытка также неудачна")
                
                # Логируем окончательную неудачу
                outcome_logger.log_failure(
                    tool_call_id=f"try_answer_final_fail_{int(time.time())}",
                    tool_name="agent_try_answer_complete_failure",
                    duration_ms=int((time.time() - start_time) * 1000),
                    error="Обе попытки ответа завершились неудачей",
                    details=f"Вопрос: {question[:100]}, Попытки: {len(attempts)}"
                )
                
                # Логируем метрику неудачной рефлексии
                metrics_manager.record_reflexion_attempt("failure")
            
            return {
                "success": final_success,
                "answer": second_attempt["answer"],
                "attempts": attempts,
                "final_attempt": 2,
                "used_reflexion": True,
                "reflexion_result": reflexion_result,
                "hints_used": len(hints),
                "processing_time_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка в try_answer: {e}")
            
            # Логируем исключение
            outcome_logger.log_failure(
                tool_call_id=f"try_answer_exception_{int(time.time())}",
                tool_name="agent_try_answer_exception",
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e),
                details=f"Исключение при обработке вопроса: {question[:100]}"
            )
            
            # Логируем метрику неудачной рефлексии при исключении
            metrics_manager.record_reflexion_attempt("failure")
            
            return {
                "success": False,
                "answer": f"Извините, произошла ошибка: {str(e)}",
                "attempts": attempts,
                "final_attempt": len(attempts),
                "used_reflexion": False,
                "error": str(e),
                "processing_time_ms": int((time.time() - start_time) * 1000)
            }
    
    async def _attempt_answer(self, 
                             question: str, 
                             attempt_number: int,
                             hints: Optional[List[Dict[str, Any]]] = None,
                             user_id: str = "default_user",
                             context: Optional[Dict[str, Any]] = None,
                             reflexion_insights: Optional[List[str]] = None) -> Dict[str, Any]:
        """Выполняет одну попытку ответа на вопрос"""
        
        attempt_start = time.time()
        
        try:
            # Строим системный промпт с учетом подсказок
            system_prompt = self._build_system_prompt(
                attempt_number=attempt_number,
                hints=hints,
                reflexion_insights=reflexion_insights
            )
            
            # Готовим сообщения для LLM
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question)
            ]
            
            # Получаем ответ от LLM
            model = chat_model()
            response = await model.ainvoke(messages)
            answer = response.content.strip()
            
            return {
                "attempt": attempt_number,
                "answer": answer,
                "system_prompt": system_prompt,
                "hints_count": len(hints) if hints else 0,
                "duration_ms": int((time.time() - attempt_start) * 1000),
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка в попытке {attempt_number}: {e}")
            return {
                "attempt": attempt_number,
                "answer": f"Ошибка при попытке ответа: {str(e)}",
                "error": str(e),
                "hints_count": len(hints) if hints else 0,
                "duration_ms": int((time.time() - attempt_start) * 1000),
                "success": False
            }
    
    def _build_system_prompt(self, 
                           attempt_number: int,
                           hints: Optional[List[Dict[str, Any]]] = None,
                           reflexion_insights: Optional[List[str]] = None) -> str:
        """Строит системный промпт с учетом номера попытки и подсказок"""
        
        base_prompt = """Ты - полезный AI-ассистент. Отвечай максимально точно и полезно на вопросы пользователя."""
        
        if attempt_number == 1:
            return base_prompt
        
        # Для второй попытки добавляем подсказки и инсайты
        enhanced_prompt = base_prompt + "\n\n"
        
        if reflexion_insights and len(reflexion_insights) > 0:
            enhanced_prompt += "🔍 **Инсайты из рефлексии:**\n"
            for insight in reflexion_insights[:3]:  # Берем топ-3 инсайта
                enhanced_prompt += f"- {insight}\n"
            enhanced_prompt += "\n"
        
        if hints and len(hints) > 0:
            enhanced_prompt += "💡 **Подсказки из прошлого успешного опыта:**\n"
            for i, hint in enumerate(hints[:3], 1):  # Берем топ-3 подсказки
                content = hint.get("content", "")
                insights = hint.get("insights", [])
                enhanced_prompt += f"{i}. {content[:200]}{'...' if len(content) > 200 else ''}\n"
                if insights:
                    enhanced_prompt += f"   Ключевые стратегии: {', '.join(insights[:3])}\n"
            enhanced_prompt += "\n"
        
        enhanced_prompt += "Используй эти подсказки для улучшения ответа. Будь более внимательным и детальным."
        
        return enhanced_prompt
    
    async def _fetch_hints(self, question: str, user_id: str) -> List[Dict[str, Any]]:
        """Получает подсказки из похожих успешных случаев"""
        try:
            # Ищем похожие успешные эпизоды
            similar_successes = await neo4j_diary_backend.fetch_similar_successes(
                query=question,
                user_filter=user_id,
                limit=5
            )
            
            return similar_successes
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения подсказок: {e}")
            return []
    
    def _evaluate_answer_quality(self, answer: str, question: str) -> bool:
        """
        Простая эвристика для оценки качества ответа.
        В продакшене можно заменить на более сложную логику или отдельную LLM-оценку.
        """
        if not answer or len(answer.strip()) < 10:
            return False
        
        # Проверяем на явные признаки неудачи
        failure_indicators = [
            "не знаю",
            "не могу ответить", 
            "извините, произошла ошибка",
            "не понимаю",
            "недостаточно информации",
            "sorry, i don't know",
            "i can't answer"
        ]
        
        answer_lower = answer.lower()
        for indicator in failure_indicators:
            if indicator in answer_lower:
                return False
        
        # Если ответ достаточно длинный и не содержит явных признаков неудачи - считаем успешным
        return len(answer.strip()) >= 20


# Глобальный экземпляр для использования
agent_runner = AgentRunner()