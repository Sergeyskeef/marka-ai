"""
Менеджер внутреннего диалога для Марка

Управляет процессом внутреннего мышления и показывает его пользователю
через исчезающие сообщения в Telegram
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.agents.mark_agent import MarkAgent
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from .thinking_handler import ThinkingMessageHandler
from .auto_solver import AutoProblemSolver
from .dialogue_state import DialogueState

logger = logging.getLogger(__name__)


@dataclass
class ThinkingStep:
    """Шаг процесса мышления"""
    step_id: str
    description: str
    timestamp: datetime
    duration: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class InternalDialogueResult:
    """Результат внутреннего диалога"""
    success: bool
    final_response: str
    thinking_steps: List[ThinkingStep]
    auto_solved: bool = False
    learning_applied: bool = False
    total_duration: float = 0.0


class InternalDialogueManager:
    """
    Менеджер внутреннего диалога
    
    Основные возможности:
    - Показывает процесс мышления через исчезающие сообщения
    - Автоматически решает простые проблемы
    - Обучается на своих действиях
    - Управляет состоянием диалога
    """
    
    def __init__(
        self,
        mark_agent: MarkAgent,
        memory_adapter: AdvancedMemoryAdapter,
        thinking_handler: Optional[ThinkingMessageHandler] = None,
        auto_solver: Optional[AutoProblemSolver] = None
    ):
        self.agent = mark_agent
        self.memory = memory_adapter
        self.thinking_handler = thinking_handler or ThinkingMessageHandler()
        self.auto_solver = auto_solver or AutoProblemSolver(mark_agent, memory_adapter)
        
        # Состояние диалога
        self.dialogue_state = DialogueState()
        
        # Настройки
        self.thinking_message_lifetime = 30  # секунды
        self.max_thinking_steps = 10
        self.auto_solve_threshold = 0.7  # порог для авторешения
        
        logger.info("🧠 InternalDialogueManager инициализирован")
    
    async def process_with_thinking(
        self, 
        user_message: str, 
        chat_id: int,
        user_id: int,
        context: Optional[Dict[str, Any]] = None
    ) -> InternalDialogueResult:
        """
        Обрабатывает сообщение пользователя с показом процесса мышления
        
        Args:
            user_message: Сообщение пользователя
            chat_id: ID чата в Telegram
            user_id: ID пользователя
            context: Дополнительный контекст
            
        Returns:
            Результат обработки с деталями процесса мышления
        """
        start_time = datetime.now()
        thinking_steps = []
        # Стартуем сессию для корректной статистики
        session_id = self.dialogue_state.start_session(user_id=user_id, chat_id=chat_id)
        
        try:
            logger.info(f"🧠 Начинаю обработку сообщения: {user_message[:100]}...")
            
            # 1. Анализ сообщения и определение сложности
            complexity_step = await self._analyze_complexity(user_message, context)
            thinking_steps.append(complexity_step)
            
            # Показываем первый шаг мышления
            await self.thinking_handler.show_thinking_step(
                chat_id, 
                f"🤔 Анализирую задачу... Сложность: {complexity_step.description}",
                self.thinking_message_lifetime,
                tg_context=(context.get("tg_context") if context else None)
            )
            
            # 2. Авторешение отключено — всегда идём через LLM
            
            # Обновляем долгоживущее статус‑сообщение (показываем пользователю, что делаем)
            try:
                await self.thinking_handler.update_status(
                    chat_id,
                    text=f"💭 Думаю над задачей… {complexity_step.description}",
                    tg_context=(context.get("tg_context") if context else None),
                )
            except Exception:
                pass

            # 3. Если авторешение не удалось или невозможно, используем обычный процесс (LLM)
            thinking_step = await self._process_with_llm(user_message, context)
            thinking_steps.append(thinking_step)
            
            # Показываем процесс мышления
            await self.thinking_handler.show_thinking_step(
                chat_id,
                f"💭 Обрабатываю через LLM: {thinking_step.description}",
                self.thinking_message_lifetime,
                tg_context=(context.get("tg_context") if context else None)
            )
            
            # 4. Получаем финальный ответ из LLM
            # Персонализация без принудительного префикса именем — стиль обращения решает LLM
            final_response = await self._get_final_response(user_message, context)
            if not final_response or not isinstance(final_response, str):
                final_response = "Я здесь. Давайте продолжим. Чем могу помочь?"
            
            # Обновляем статус‑сообщение прогрессом (после LLM шага)
            try:
                await self.thinking_handler.update_status(
                    chat_id,
                    text=f"💭 Обработка через LLM завершена. Мысленных шагов: {len(thinking_steps)}. Формирую ответ…",
                    tg_context=(context.get("tg_context") if context else None),
                )
            except Exception:
                pass

            # 5. Сохраняем опыт в память
            await self._save_learning_experience(
                user_message, {"response": final_response}, "llm_processing", True
            )
            
            total_duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"✅ Сообщение обработано за {total_duration:.2f}с")
            # Обновляем статистику диалога и завершаем сессию
            self.dialogue_state.update_session(
                session_id=session_id,
                message_processed=True,
                auto_solved=False,
                llm_processed=True,
                success=True,
                duration=total_duration
            )
            self.dialogue_state.end_session(session_id)
            
            result_obj = InternalDialogueResult(
                success=True,
                final_response=final_response,
                thinking_steps=thinking_steps,
                auto_solved=False,
                learning_applied=True,
                total_duration=total_duration
            )

            # Очищаем статус‑сообщение после отправки результата (опционально можно оставить)
            try:
                await self.thinking_handler.clear_status(chat_id, tg_context=(context.get("tg_context") if context else None))
            except Exception:
                pass

            return result_obj
            
        except Exception as e:
            error_step = ThinkingStep(
                step_id=f"error_{len(thinking_steps)}",
                description=f"Ошибка обработки: {str(e)}",
                timestamp=datetime.now(),
                success=False,
                error=str(e)
            )
            thinking_steps.append(error_step)
            
            logger.error(f"❌ Ошибка в процессе мышления: {e}")
            
            # Показываем ошибку
            await self.thinking_handler.show_thinking_step(
                chat_id,
                f"❌ Произошла ошибка: {str(e)}",
                self.thinking_message_lifetime,
                tg_context=(context.get("tg_context") if context else None)
            )
            # Обновляем статистику диалога об ошибке и завершаем сессию
            total_duration = (datetime.now() - start_time).total_seconds()
            self.dialogue_state.update_session(
                session_id=session_id,
                message_processed=True,
                auto_solved=False,
                llm_processed=False,
                success=False,
                duration=total_duration
            )
            self.dialogue_state.end_session(session_id)
            
            return InternalDialogueResult(
                success=False,
                final_response=f"Извините, произошла ошибка: {str(e)}",
                thinking_steps=thinking_steps,
                auto_solved=False,
                learning_applied=False,
                total_duration=total_duration
            )
    
    async def _analyze_complexity(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]]
    ) -> ThinkingStep:
        """Анализирует сложность задачи"""
        start_time = datetime.now()
        
        try:
            # Простой анализ сложности на основе ключевых слов
            complexity_keywords = {
                "простой": "низкая",
                "легкий": "низкая", 
                "базовый": "низкая",
                "сложный": "высокая",
                "трудный": "высокая",
                "анализ": "средняя",
                "разработка": "средняя",
                "проект": "высокая"
            }
            
            complexity = "средняя"  # по умолчанию
            for keyword, level in complexity_keywords.items():
                if keyword in message.lower():
                    complexity = level
                    break
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ThinkingStep(
                step_id="complexity_analysis",
                description=f"Сложность задачи: {complexity}",
                timestamp=start_time,
                duration=duration,
                success=True
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ThinkingStep(
                step_id="complexity_analysis",
                description="Ошибка анализа сложности",
                timestamp=start_time,
                duration=duration,
                success=False,
                error=str(e)
            )
    
    def _can_auto_solve(self, complexity_description: str) -> bool:
        """Определяет, можно ли решить задачу автоматически"""
        if "низкая" in complexity_description:
            return True
        elif "средняя" in complexity_description:
            return True
        else:
            return False
    
    async def _attempt_auto_solve(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]]
    ) -> ThinkingStep:
        """Пытается решить задачу автоматически"""
        start_time = datetime.now()
        
        try:
            # Проверяем, есть ли готовое решение в памяти
            has_solution = await self.auto_solver.has_solution(message)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ThinkingStep(
                step_id="auto_solve_attempt",
                description=f"Авторешение: {'доступно' if has_solution else 'не найдено'}",
                timestamp=start_time,
                duration=duration,
                success=True
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ThinkingStep(
                step_id="auto_solve_attempt",
                description="Ошибка авторешения",
                timestamp=start_time,
                duration=duration,
                success=False,
                error=str(e)
            )
    
    async def _process_with_llm(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]]
    ) -> ThinkingStep:
        """Обрабатывает сообщение через LLM"""
        start_time = datetime.now()
        
        try:
            # Здесь реальный вызов через ChatService (если передан)
            chat_service = context.get("chat_service") if context else None
            user_id = context.get("user_id") if context else None
            chat_id = context.get("chat_id") if context else None
            response_text = None
            if chat_service and user_id and chat_id:
                try:
                    resp = await chat_service.ask_question(
                        question=message,
                        user_id=user_id,
                        chat_id=chat_id,
                        mode=context.get("chat_mode") if context else "chat"
                    )
                    response_text = chat_service.format_response(resp)
                except Exception as e:
                    logger.warning(f"LLM через ChatService не доступен: {e}")
            
            # Если не удалось — fallback заглушка
            duration = (datetime.now() - start_time).total_seconds()
            
            return ThinkingStep(
                step_id="llm_processing",
                description="Обработка через LLM завершена" if response_text else "Обработка через LLM (fallback)",
                timestamp=start_time,
                duration=duration,
                success=True
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ThinkingStep(
                step_id="llm_processing",
                description="Ошибка LLM обработки",
                timestamp=start_time,
                duration=duration,
                success=False,
                error=str(e)
            )
    
    async def _get_final_response(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Получает финальный ответ"""
        # Пробуем получить ответ, если ChatService был передан через контекст
        chat_service = context.get("chat_service") if context else None
        user_id = context.get("user_id") if context else None
        chat_id = context.get("chat_id") if context else None
        tg_context = context.get("tg_context") if context else None
        # Параллельно запускаем поллер статуса, который подтягивает логи инструментов и обновляет статус‑сообщение
        progress_task = None
        try:
            if chat_service and user_id and chat_id:
                try:
                    progress_task = asyncio.create_task(
                        self._poll_and_update_status(
                            chat_service=chat_service,
                            chat_id=chat_id,
                            user_id=user_id,
                            tg_context=tg_context,
                        )
                    )
                except Exception:
                    progress_task = None

                resp = await chat_service.ask_question(
                    question=message,
                    user_id=user_id,
                    chat_id=chat_id,
                    mode=context.get("chat_mode") if context else "chat"
                )
                return chat_service.format_response(resp)
        except Exception as e:
            logger.warning(f"Не удалось получить финальный ответ через ChatService: {e}")
        finally:
            if progress_task:
                try:
                    progress_task.cancel()
                except Exception:
                    pass
        
        # Fallback
        return f"Я здесь. Давайте продолжим. Чем могу помочь?"

    async def _poll_and_update_status(
        self,
        chat_service,
        chat_id: int,
        user_id: str | int,
        tg_context: Any | None,
        interval_sec: float = 3.0,
    ) -> None:
        """
        Периодически опрашивает логи инструментов через API и обновляет статус‑сообщение в Telegram.
        Показывает количество вызовов, последний инструмент и длительность, а также прошедшее время.
        """
        start_ts = datetime.now().timestamp()
        started_at = datetime.now()
        while True:
            try:
                await asyncio.sleep(interval_sec)
                # Получаем последние логи инструментов
                r = await chat_service.client.get("/api/memory/tool-logs", params={"limit": 80})
                data = r.json()
                items = data.get("items", [])
                # Фильтруем по user_id и по времени старта
                filtered = []
                for it in items:
                    md = it.get("metadata", {}) or {}
                    if str(md.get("user_id")) != str(user_id):
                        continue
                    if float(md.get("timestamp", 0)) < start_ts:
                        continue
                    filtered.append(it)
                calls = len(filtered)
                last = filtered[-1] if filtered else None
                last_tool = (last.get("metadata", {}) or {}).get("tool") if last else None
                last_ms = (last.get("metadata", {}) or {}).get("duration_ms") if last else None
                elapsed = int((datetime.now() - started_at).total_seconds())
                status_lines = [
                    "🔧 Работа инструментов…",
                    f"Вызовов: {calls}",
                ]
                if last_tool:
                    status_lines.append(f"Текущий/последний: {last_tool}{' ('+str(last_ms)+' мс)' if last_ms is not None else ''}")
                status_lines.append(f"Прошло: ~{elapsed}с")
                await self.thinking_handler.update_status(
                    chat_id,
                    text="\n".join(status_lines),
                    tg_context=tg_context,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"poll status error: {e}")
                # продолжим через следующий такт
                continue
    
    async def _save_learning_experience(
        self, 
        input_message: str, 
        result: Dict[str, Any], 
        method: str, 
        success: bool
    ):
        """Сохраняет опыт обучения в память"""
        try:
            experience = {
                "input": input_message,
                "result": result,
                "method": method,
                "success": success,
                "timestamp": int(datetime.now().timestamp()),
                "type": "internal_dialogue_experience"
            }
            
            await self.memory.save_episode(
                situation=input_message,
                actions_taken=[f"Обработка через {method}"],
                outcome="успешно" if success else "неудачно",
                reasoning=experience.get("result", {}).get("content", ""),
                lesson_learned="",
                satisfaction=0.7 if success else 0.3,
                metadata=experience
            )
            
            logger.info(f"💾 Опыт сохранен в память: {method}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения опыта: {e}")
    
    async def get_dialogue_stats(self) -> Dict[str, Any]:
        """Получает статистику диалогов"""
        return {
            "total_dialogues": self.dialogue_state.metrics.total_dialogues,
            "auto_solved": self.dialogue_state.metrics.auto_solved_count,
            "llm_processed": self.dialogue_state.metrics.llm_processed_count,
            "average_duration": self.dialogue_state.metrics.average_duration,
            "success_rate": self.dialogue_state.metrics.success_rate
        }
    
    async def reset_dialogue_state(self):
        """Сбрасывает состояние диалога"""
        self.dialogue_state = DialogueState()
        logger.info("🔄 Состояние диалога сброшено")
