"""
Состояние внутреннего диалога для Марка

Отслеживает статистику и состояние диалогов
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DialogueSession:
    """Сессия диалога"""
    session_id: str
    user_id: int
    chat_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    messages_processed: int = 0
    auto_solved: int = 0
    llm_processed: int = 0
    total_duration: float = 0.0
    success_count: int = 0
    error_count: int = 0


@dataclass
class DialogueMetrics:
    """Метрики диалогов"""
    total_dialogues: int = 0
    auto_solved_count: int = 0
    llm_processed_count: int = 0
    total_duration: float = 0.0
    success_count: int = 0
    error_count: int = 0
    
    @property
    def average_duration(self) -> float:
        """Средняя продолжительность диалога"""
        if self.total_dialogues == 0:
            return 0.0
        return self.total_duration / self.total_dialogues
    
    @property
    def success_rate(self) -> float:
        """Процент успешных диалогов"""
        total = self.success_count + self.error_count
        if total == 0:
            return 0.0
        return self.success_count / total
    
    @property
    def auto_solve_rate(self) -> float:
        """Процент авторешенных задач"""
        total = self.auto_solved_count + self.llm_processed_count
        if total == 0:
            return 0.0
        return self.auto_solved_count / total


class DialogueState:
    """
    Состояние внутреннего диалога
    
    Основные возможности:
    - Отслеживает активные сессии
    - Собирает метрики производительности
    - Управляет историей диалогов
    - Предоставляет аналитику
    """
    
    def __init__(self):
        # Активные сессии
        self.active_sessions: Dict[str, DialogueSession] = {}
        
        # История сессий
        self.session_history: List[DialogueSession] = []
        
        # Общие метрики
        self.metrics = DialogueMetrics()
        
        # Настройки
        self.max_history_size = 1000
        self.session_timeout = 3600  # 1 час
        
        logger.info("📊 DialogueState инициализирован")
    
    def start_session(self, user_id: int, chat_id: int) -> str:
        """
        Начинает новую сессию диалога
        
        Args:
            user_id: ID пользователя
            chat_id: ID чата
            
        Returns:
            ID сессии
        """
        try:
            # Генерируем уникальный ID сессии
            session_id = f"session_{user_id}_{chat_id}_{datetime.now().timestamp()}"
            
            # Создаем новую сессию
            session = DialogueSession(
                session_id=session_id,
                user_id=user_id,
                chat_id=chat_id,
                start_time=datetime.now()
            )
            
            # Добавляем в активные сессии
            self.active_sessions[session_id] = session
            
            # Обновляем общее количество диалогов
            self.metrics.total_dialogues = len(self.session_history) + len(self.active_sessions)
            
            logger.info(f"🚀 Начата сессия: {session_id}")
            
            return session_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка начала сессии: {e}")
            return f"error_session_{user_id}_{chat_id}"
    
    def end_session(self, session_id: str):
        """
        Завершает сессию диалога
        
        Args:
            session_id: ID сессии для завершения
        """
        try:
            if session_id not in self.active_sessions:
                logger.warning(f"⚠️ Сессия не найдена: {session_id}")
                return
            
            session = self.active_sessions[session_id]
            session.end_time = datetime.now()
            session.total_duration = (session.end_time - session.start_time).total_seconds()
            
            # Перемещаем в историю
            self.session_history.append(session)
            del self.active_sessions[session_id]
            
            # Ограничиваем размер истории
            if len(self.session_history) > self.max_history_size:
                self.session_history = self.session_history[-self.max_history_size:]
            
            # Метрики обновляются в update_session; здесь не дублируем
            
            logger.info(f"🏁 Завершена сессия: {session_id} (длительность: {session.total_duration:.2f}с)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка завершения сессии: {e}")
    
    def update_session(
        self, 
        session_id: str, 
        message_processed: bool = False,
        auto_solved: bool = False,
        llm_processed: bool = False,
        success: bool = True,
        duration: float = 0.0
    ):
        """
        Обновляет состояние сессии
        
        Args:
            session_id: ID сессии
            message_processed: Обработано ли сообщение
            auto_solved: Авторешена ли задача
            llm_processed: Обработано ли через LLM
            success: Успешность операции
            duration: Продолжительность операции
        """
        try:
            if session_id not in self.active_sessions:
                logger.warning(f"⚠️ Сессия не найдена для обновления: {session_id}")
                return
            
            session = self.active_sessions[session_id]
            
            if message_processed:
                session.messages_processed += 1
            
            if auto_solved:
                session.auto_solved += 1
            
            if llm_processed:
                session.llm_processed += 1
            
            if success:
                session.success_count += 1
            else:
                session.error_count += 1
            
            session.total_duration += duration
            
            logger.debug(f"📝 Обновлена сессия: {session_id}")
            
            # Обновляем общие метрики
            self._update_metrics(session)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сессии: {e}")
    
    def _update_metrics(self, session: DialogueSession):
        """Обновляет общие метрики на основе сессии"""
        try:
            # Обновляем счетчики на основе сессии
            self.metrics.auto_solved_count += session.auto_solved
            self.metrics.llm_processed_count += session.llm_processed
            self.metrics.total_duration += session.total_duration
            self.metrics.success_count += session.success_count
            self.metrics.error_count += session.error_count
            
            # Обновляем общее количество диалогов
            self.metrics.total_dialogues = len(self.session_history) + len(self.active_sessions)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления метрик: {e}")
    
    def get_session(self, session_id: str) -> Optional[DialogueSession]:
        """
        Получает сессию по ID
        
        Args:
            session_id: ID сессии
            
        Returns:
            Сессия или None если не найдена
        """
        return self.active_sessions.get(session_id)
    
    def get_user_sessions(self, user_id: int) -> List[DialogueSession]:
        """
        Получает все сессии пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список сессий пользователя
        """
        try:
            user_sessions = []
            
            # Активные сессии
            for session in self.active_sessions.values():
                if session.user_id == user_id:
                    user_sessions.append(session)
            
            # Исторические сессии
            for session in self.session_history:
                if session.user_id == user_id:
                    user_sessions.append(session)
            
            return user_sessions
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения сессий пользователя: {e}")
            return []
    
    def get_chat_sessions(self, chat_id: int) -> List[DialogueSession]:
        """
        Получает все сессии чата
        
        Args:
            chat_id: ID чата
            
        Returns:
            Список сессий чата
        """
        try:
            chat_sessions = []
            
            # Активные сессии
            for session in self.active_sessions.values():
                if session.chat_id == chat_id:
                    chat_sessions.append(session)
            
            # Исторические сессии
            for session in self.session_history:
                if session.chat_id == chat_id:
                    chat_sessions.append(session)
            
            return chat_sessions
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения сессий чата: {e}")
            return []
    
    def cleanup_expired_sessions(self):
        """Очищает истекшие сессии"""
        try:
            current_time = datetime.now()
            expired_sessions = []
            
            for session_id, session in self.active_sessions.items():
                if current_time - session.start_time > timedelta(seconds=self.session_timeout):
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                self.end_session(session_id)
                logger.info(f"⏰ Очищена истекшая сессия: {session_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки истекших сессий: {e}")
    
    def get_performance_stats(self, time_period: str = "all") -> Dict[str, Any]:
        """
        Получает статистику производительности
        
        Args:
            time_period: Период времени ("hour", "day", "week", "month", "all")
            
        Returns:
            Статистика производительности
        """
        try:
            current_time = datetime.now()
            
            if time_period == "all":
                sessions = list(self.active_sessions.values()) + self.session_history
            else:
                # Фильтруем по времени
                if time_period == "hour":
                    cutoff_time = current_time - timedelta(hours=1)
                elif time_period == "day":
                    cutoff_time = current_time - timedelta(days=1)
                elif time_period == "week":
                    cutoff_time = current_time - timedelta(weeks=1)
                elif time_period == "month":
                    cutoff_time = current_time - timedelta(days=30)
                else:
                    cutoff_time = current_time - timedelta(days=1)
                
                sessions = []
                for session in self.active_sessions.values():
                    if session.start_time >= cutoff_time:
                        sessions.append(session)
                
                for session in self.session_history:
                    if session.start_time >= cutoff_time:
                        sessions.append(session)
            
            # Вычисляем статистику
            total_sessions = len(sessions)
            total_messages = sum(s.messages_processed for s in sessions)
            total_auto_solved = sum(s.auto_solved for s in sessions)
            total_llm_processed = sum(s.llm_processed for s in sessions)
            total_duration = sum(s.total_duration for s in sessions)
            total_success = sum(s.success_count for s in sessions)
            total_errors = sum(s.error_count for s in sessions)
            
            return {
                "period": time_period,
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "total_auto_solved": total_auto_solved,
                "total_llm_processed": total_llm_processed,
                "total_duration": total_duration,
                "total_success": total_success,
                "total_errors": total_errors,
                "average_duration": total_duration / total_sessions if total_sessions > 0 else 0,
                "success_rate": total_success / (total_success + total_errors) if (total_success + total_errors) > 0 else 0,
                "auto_solve_rate": total_auto_solved / (total_auto_solved + total_llm_processed) if (total_auto_solved + total_llm_processed) > 0 else 0,
                "messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики производительности: {e}")
            return {}
    
    def get_user_performance(self, user_id: int) -> Dict[str, Any]:
        """
        Получает статистику производительности пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Статистика производительности пользователя
        """
        try:
            user_sessions = self.get_user_sessions(user_id)
            
            if not user_sessions:
                return {"user_id": user_id, "no_sessions": True}
            
            total_sessions = len(user_sessions)
            total_messages = sum(s.messages_processed for s in user_sessions)
            total_auto_solved = sum(s.auto_solved for s in user_sessions)
            total_llm_processed = sum(s.llm_processed for s in user_sessions)
            total_duration = sum(s.total_duration for s in user_sessions)
            total_success = sum(s.success_count for s in user_sessions)
            total_errors = sum(s.error_count for s in user_sessions)
            
            return {
                "user_id": user_id,
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "total_auto_solved": total_auto_solved,
                "total_llm_processed": total_llm_processed,
                "total_duration": total_duration,
                "total_success": total_success,
                "total_errors": total_errors,
                "average_duration": total_duration / total_sessions if total_sessions > 0 else 0,
                "success_rate": total_success / (total_success + total_errors) if (total_success + total_errors) > 0 else 0,
                "auto_solve_rate": total_auto_solved / (total_auto_solved + total_llm_processed) if (total_auto_solved + total_llm_processed) > 0 else 0,
                "messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0,
                "last_session": max(s.start_time for s in user_sessions).isoformat() if user_sessions else None
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователя: {e}")
            return {"user_id": user_id, "error": str(e)}
    
    def reset_metrics(self):
        """Сбрасывает все метрики"""
        try:
            self.metrics = DialogueMetrics()
            self.session_history.clear()
            self.active_sessions.clear()
            
            logger.info("🔄 Все метрики сброшены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сброса метрик: {e}")
    
    def export_data(self) -> Dict[str, Any]:
        """Экспортирует данные состояния"""
        try:
            return {
                "metrics": {
                    "total_dialogues": self.metrics.total_dialogues,
                    "auto_solved_count": self.metrics.auto_solved_count,
                    "llm_processed_count": self.metrics.llm_processed_count,
                    "total_duration": self.metrics.total_duration,
                    "success_count": self.metrics.success_count,
                    "error_count": self.metrics.error_count,
                    "average_duration": self.metrics.average_duration,
                    "success_rate": self.metrics.success_rate,
                    "auto_solve_rate": self.metrics.auto_solve_rate
                },
                "active_sessions_count": len(self.active_sessions),
                "history_sessions_count": len(self.session_history),
                "export_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта данных: {e}")
            return {"error": str(e)}
