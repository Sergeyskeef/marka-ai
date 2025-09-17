"""
Тесты для системы внутреннего диалога Марка

Проверяет:
- Менеджер внутреннего диалога
- Обработчик исчезающих сообщений
- Авторешатель проблем
- Состояние диалога
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.internal_dialogue.manager import (
    InternalDialogueManager, 
    ThinkingStep, 
    InternalDialogueResult
)
from app.internal_dialogue.thinking_handler import ThinkingMessageHandler
from app.internal_dialogue.auto_solver import AutoProblemSolver, AutoSolution
from app.internal_dialogue.dialogue_state import DialogueState, DialogueSession


@pytest.fixture
def mock_mark_agent():
    """Мок для MarkAgent"""
    agent = Mock()
    agent.model = "gpt-4.1-mini"
    return agent


@pytest.fixture
def mock_memory_adapter():
    """Мок для AdvancedMemoryAdapter"""
    adapter = Mock()
    adapter.save_episode = AsyncMock()
    adapter.find_similar_episodes = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def mock_thinking_handler():
    """Мок для ThinkingMessageHandler"""
    handler = Mock()
    handler.show_thinking_step = AsyncMock(return_value=123)
    handler.show_progress = AsyncMock(return_value=456)
    handler.show_error = AsyncMock(return_value=789)
    handler.show_success = AsyncMock(return_value=101)
    return handler


@pytest.fixture
def mock_auto_solver():
    """Мок для AutoProblemSolver"""
    solver = Mock()
    solver.has_solution = AsyncMock(return_value=False)
    solver.solve_problem = AsyncMock(return_value=AutoSolution(
        success=False,
        response="Не могу решить автоматически",
        confidence=0.0,
        method="no_solution",
        metadata={}
    ))
    return solver


@pytest.fixture
def internal_dialogue_manager(
    mock_mark_agent, 
    mock_memory_adapter, 
    mock_thinking_handler, 
    mock_auto_solver
):
    """Экземпляр InternalDialogueManager с моками"""
    return InternalDialogueManager(
        mark_agent=mock_mark_agent,
        memory_adapter=mock_memory_adapter,
        thinking_handler=mock_thinking_handler,
        auto_solver=mock_auto_solver
    )


class TestInternalDialogueManager:
    """Тесты для InternalDialogueManager"""
    
    @pytest.mark.asyncio
    async def test_initialization(self, internal_dialogue_manager):
        """Тест инициализации менеджера"""
        assert internal_dialogue_manager.agent is not None
        assert internal_dialogue_manager.memory is not None
        assert internal_dialogue_manager.thinking_handler is not None
        assert internal_dialogue_manager.auto_solver is not None
        assert internal_dialogue_manager.dialogue_state is not None
        assert internal_dialogue_manager.thinking_message_lifetime == 30
    
    @pytest.mark.asyncio
    async def test_analyze_complexity_simple(self, internal_dialogue_manager):
        """Тест анализа сложности простой задачи"""
        step = await internal_dialogue_manager._analyze_complexity("простая задача", {})
        
        assert step.success is True
        assert "низкая" in step.description
        assert step.step_id == "complexity_analysis"
        assert step.duration >= 0
    
    @pytest.mark.asyncio
    async def test_analyze_complexity_complex(self, internal_dialogue_manager):
        """Тест анализа сложности сложной задачи"""
        step = await internal_dialogue_manager._analyze_complexity("сложный проект разработки", {})
        
        assert step.success is True
        assert "высокая" in step.description
        assert step.step_id == "complexity_analysis"
    
    @pytest.mark.asyncio
    async def test_can_auto_solve(self, internal_dialogue_manager):
        """Тест определения возможности авторешения"""
        # Низкая сложность - можно решить
        assert internal_dialogue_manager._can_auto_solve("Сложность задачи: низкая") is True
        
        # Средняя сложность - можно решить
        assert internal_dialogue_manager._can_auto_solve("Сложность задачи: средняя") is True
        
        # Высокая сложность - нельзя решить
        assert internal_dialogue_manager._can_auto_solve("Сложность задачи: высокая") is False
    
    @pytest.mark.asyncio
    async def test_attempt_auto_solve(self, internal_dialogue_manager, mock_auto_solver):
        """Тест попытки авторешения"""
        mock_auto_solver.has_solution.return_value = True
        
        step = await internal_dialogue_manager._attempt_auto_solve("тестовая задача", {})
        
        assert step.success is True
        assert "доступно" in step.description
        assert step.step_id == "auto_solve_attempt"
    
    @pytest.mark.asyncio
    async def test_process_with_thinking_simple(self, internal_dialogue_manager, mock_auto_solver):
        """Тест обработки простого сообщения с авторешением"""
        # Настраиваем авторешатель для успешного решения
        mock_auto_solver.has_solution.return_value = True
        mock_auto_solver.solve_problem.return_value = AutoSolution(
            success=True,
            response="Автоматически решено!",
            confidence=0.9,
            method="pattern_match",
            metadata={}
        )
        
        result = await internal_dialogue_manager.process_with_thinking(
            "привет", 
            chat_id=123, 
            user_id=456
        )
        
        assert result.success is True
        assert result.auto_solved is True
        assert result.learning_applied is True
        assert "Автоматически решено!" in result.final_response
        assert len(result.thinking_steps) >= 2
    
    @pytest.mark.asyncio
    async def test_process_with_thinking_complex(self, internal_dialogue_manager):
        """Тест обработки сложного сообщения через LLM"""
        result = await internal_dialogue_manager.process_with_thinking(
            "сложная задача разработки", 
            chat_id=123, 
            user_id=456
        )
        
        assert result.success is True
        assert result.auto_solved is False
        assert result.learning_applied is True
        assert len(result.thinking_steps) >= 3
    
    @pytest.mark.asyncio
    async def test_process_with_thinking_error(self, internal_dialogue_manager, mock_memory_adapter):
        """Тест обработки сообщения с ошибкой"""
        # Симулируем ошибку в памяти
        mock_memory_adapter.save_episode.side_effect = Exception("Ошибка памяти")
        
        result = await internal_dialogue_manager.process_with_thinking(
            "тестовая задача", 
            chat_id=123, 
            user_id=456
        )
        
        assert result.success is False
        assert "ошибка" in result.final_response.lower()
        assert len(result.thinking_steps) >= 1
    
    @pytest.mark.asyncio
    async def test_save_learning_experience(self, internal_dialogue_manager, mock_memory_adapter):
        """Тест сохранения опыта обучения"""
        await internal_dialogue_manager._save_learning_experience(
            "тестовая задача",
            {"response": "тестовый ответ"},
            "test_method",
            True
        )
        
        mock_memory_adapter.save_episode.assert_called_once()
        call_args = mock_memory_adapter.save_episode.call_args
        assert call_args[1]["situation"] == "тестовая задача"
        assert call_args[1]["outcome"] == "успешно"
    
    @pytest.mark.asyncio
    async def test_get_dialogue_stats(self, internal_dialogue_manager):
        """Тест получения статистики диалогов"""
        stats = await internal_dialogue_manager.get_dialogue_stats()
        
        assert "total_dialogues" in stats
        assert "auto_solved" in stats
        assert "llm_processed" in stats
        assert "average_duration" in stats
        assert "success_rate" in stats


class TestThinkingMessageHandler:
    """Тесты для ThinkingMessageHandler"""
    
    @pytest.fixture
    def thinking_handler(self):
        """Экземпляр ThinkingMessageHandler"""
        return ThinkingMessageHandler()
    
    @pytest.mark.asyncio
    async def test_initialization(self, thinking_handler):
        """Тест инициализации обработчика"""
        assert thinking_handler.active_messages == {}
        assert thinking_handler.message_queue == []
        assert thinking_handler.is_running is False
        assert thinking_handler.max_concurrent_messages == 3
        assert thinking_handler.default_lifetime == 30
    
    @pytest.mark.asyncio
    async def test_start_stop(self, thinking_handler):
        """Тест запуска и остановки обработчика"""
        await thinking_handler.start()
        assert thinking_handler.is_running is True
        
        await thinking_handler.stop()
        assert thinking_handler.is_running is False
    
    @pytest.mark.asyncio
    async def test_show_thinking_step(self, thinking_handler):
        """Тест показа шага мышления"""
        message_id = await thinking_handler.show_thinking_step(
            chat_id=123,
            text="Тестовый шаг",
            lifetime=15
        )
        
        assert message_id is not None
        assert len(thinking_handler.message_queue) == 1
        
        message = thinking_handler.message_queue[0]
        assert message.chat_id == 123
        assert message.text == "Тестовый шаг"
        assert message.lifetime == 15
    
    @pytest.mark.asyncio
    async def test_show_progress(self, thinking_handler):
        """Тест показа прогресса"""
        message_id = await thinking_handler.show_progress(
            chat_id=123,
            current_step=2,
            total_steps=5,
            description="Тестовый шаг"
        )
        
        assert message_id is not None
        assert len(thinking_handler.message_queue) == 1
        
        message = thinking_handler.message_queue[0]
        assert "🔄 Прогресс:" in message.text
        assert "2/5" in message.text
        assert "Тестовый шаг" in message.text
    
    @pytest.mark.asyncio
    async def test_show_error(self, thinking_handler):
        """Тест показа ошибки"""
        message_id = await thinking_handler.show_error(
            chat_id=123,
            error_text="Тестовая ошибка"
        )
        
        assert message_id is not None
        assert len(thinking_handler.message_queue) == 1
        
        message = thinking_handler.message_queue[0]
        assert "❌ Ошибка:" in message.text
        assert "Тестовая ошибка" in message.text
    
    @pytest.mark.asyncio
    async def test_show_success(self, thinking_handler):
        """Тест показа успеха"""
        message_id = await thinking_handler.show_success(
            chat_id=123,
            success_text="Тестовый успех"
        )
        
        assert message_id is not None
        assert len(thinking_handler.message_queue) == 1
        
        message = thinking_handler.message_queue[0]
        assert "✅" in message.text
        assert "Тестовый успех" in message.text
    
    def test_create_progress_bar(self, thinking_handler):
        """Тест создания прогресс-бара"""
        # Пустой прогресс
        bar = thinking_handler._create_progress_bar(0, 0)
        assert len(bar) == 20
        assert "█" in bar
        
        # Половина прогресса
        bar = thinking_handler._create_progress_bar(5, 10)
        assert len(bar) == 20
        assert bar.count("█") == 10
        assert bar.count("░") == 10
        
        # Полный прогресс
        bar = thinking_handler._create_progress_bar(10, 10)
        assert len(bar) == 20
        assert bar.count("█") == 20
        assert bar.count("░") == 0
    
    @pytest.mark.asyncio
    async def test_clear_all_messages(self, thinking_handler):
        """Тест очистки всех сообщений"""
        # Добавляем тестовые сообщения
        await thinking_handler.show_thinking_step(123, "Тест 1")
        await thinking_handler.show_thinking_step(456, "Тест 2")
        
        assert len(thinking_handler.message_queue) == 2
        
        # Очищаем
        await thinking_handler.clear_all_messages()
        
        assert len(thinking_handler.message_queue) == 0
        assert len(thinking_handler.active_messages) == 0


class TestAutoProblemSolver:
    """Тесты для AutoProblemSolver"""
    
    @pytest.fixture
    def auto_solver(self, mock_mark_agent, mock_memory_adapter):
        """Экземпляр AutoProblemSolver с моками"""
        return AutoProblemSolver(
            mark_agent=mock_mark_agent,
            memory_adapter=mock_memory_adapter
        )
    
    def test_initialization(self, auto_solver):
        """Тест инициализации авторешателя"""
        assert auto_solver.agent is not None
        assert auto_solver.memory is not None
        assert len(auto_solver.problem_patterns) > 0
        assert auto_solver.min_confidence == 0.7
        assert auto_solver.max_patterns == 100
    
    def test_basic_patterns_loaded(self, auto_solver):
        """Тест загрузки базовых паттернов"""
        # Проверяем наличие базовых паттернов
        patterns_text = [p.pattern for p in auto_solver.problem_patterns]
        
        assert any("привет" in p for p in patterns_text)
        assert any("python" in p for p in patterns_text)
        assert any("docker" in p for p in patterns_text)
        assert any("помощь" in p for p in patterns_text)
    
    @pytest.mark.asyncio
    async def test_has_solution_pattern_match(self, auto_solver):
        """Тест проверки наличия решения по паттерну"""
        # Проверяем простой паттерн
        has_solution = await auto_solver.has_solution("привет, как дела?")
        assert has_solution is True
        
        # Проверяем сложный паттерн
        has_solution = await auto_solver.has_solution("расскажи о python")
        assert has_solution is True
    
    @pytest.mark.asyncio
    async def test_has_solution_no_match(self, auto_solver):
        """Тест проверки отсутствия решения"""
        has_solution = await auto_solver.has_solution("очень специфичная задача без паттерна")
        assert has_solution is False
    
    @pytest.mark.asyncio
    async def test_solve_problem_pattern_match(self, auto_solver):
        """Тест решения проблемы по паттерну"""
        solution = await auto_solver.solve_problem("привет!")
        
        assert solution.success is True
        assert solution.method == "pattern_match"
        assert solution.confidence >= 0.9
        assert "Привет" in solution.response
    
    @pytest.mark.asyncio
    async def test_solve_problem_no_solution(self, auto_solver):
        """Тест отсутствия решения"""
        solution = await auto_solver.solve_problem("неизвестная задача")
        
        assert solution.success is False
        assert solution.method == "no_solution"
        assert solution.confidence == 0.0
    
    def test_find_best_pattern(self, auto_solver):
        """Тест поиска лучшего паттерна"""
        # Ищем паттерн для приветствия
        pattern = auto_solver._find_best_pattern("привет, как дела?")
        
        assert pattern is not None
        assert "привет" in pattern.pattern.lower()
        assert pattern.confidence >= 0.9
    
    def test_create_pattern_from_text(self, auto_solver):
        """Тест создания паттерна из текста"""
        pattern = auto_solver._create_pattern_from_text("сложная задача разработки")
        
        assert "сложная" in pattern
        assert "задача" in pattern
        assert "разработки" in pattern
    
    def test_get_patterns_stats(self, auto_solver):
        """Тест получения статистики паттернов"""
        stats = auto_solver.get_patterns_stats()
        
        assert "total_patterns" in stats
        assert "active_patterns" in stats
        assert "total_usage" in stats
        assert "average_confidence" in stats
        assert stats["total_patterns"] > 0


class TestDialogueState:
    """Тесты для DialogueState"""
    
    @pytest.fixture
    def dialogue_state(self):
        """Экземпляр DialogueState"""
        return DialogueState()
    
    def test_initialization(self, dialogue_state):
        """Тест инициализации состояния"""
        assert dialogue_state.active_sessions == {}
        assert dialogue_state.session_history == []
        assert dialogue_state.metrics.total_dialogues == 0
        assert dialogue_state.max_history_size == 1000
        assert dialogue_state.session_timeout == 3600
    
    def test_start_session(self, dialogue_state):
        """Тест начала сессии"""
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        
        assert session_id.startswith("session_123_456_")
        assert session_id in dialogue_state.active_sessions
        
        session = dialogue_state.active_sessions[session_id]
        assert session.user_id == 123
        assert session.chat_id == 456
        assert session.start_time is not None
    
    def test_end_session(self, dialogue_state):
        """Тест завершения сессии"""
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        
        # Обновляем сессию
        dialogue_state.update_session(
            session_id,
            message_processed=True,
            auto_solved=True,
            success=True,
            duration=10.0
        )
        
        # Завершаем сессию
        dialogue_state.end_session(session_id)
        
        assert session_id not in dialogue_state.active_sessions
        assert len(dialogue_state.session_history) == 1
        assert dialogue_state.metrics.total_dialogues == 1
        assert dialogue_state.metrics.auto_solved_count == 1
    
    def test_update_session(self, dialogue_state):
        """Тест обновления сессии"""
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        
        dialogue_state.update_session(
            session_id,
            message_processed=True,
            auto_solved=True,
            llm_processed=False,
            success=True,
            duration=5.0
        )
        
        session = dialogue_state.active_sessions[session_id]
        assert session.messages_processed == 1
        assert session.auto_solved == 1
        assert session.llm_processed == 0
        assert session.success_count == 1
        assert session.error_count == 0
        assert session.total_duration == 5.0
    
    def test_get_user_sessions(self, dialogue_state):
        """Тест получения сессий пользователя"""
        # Создаем несколько сессий
        session1 = dialogue_state.start_session(user_id=123, chat_id=456)
        session2 = dialogue_state.start_session(user_id=123, chat_id=789)
        session3 = dialogue_state.start_session(user_id=999, chat_id=456)
        
        user_sessions = dialogue_state.get_user_sessions(123)
        assert len(user_sessions) == 2
        
        user_sessions = dialogue_state.get_user_sessions(999)
        assert len(user_sessions) == 1
    
    def test_get_chat_sessions(self, dialogue_state):
        """Тест получения сессий чата"""
        # Создаем несколько сессий
        session1 = dialogue_state.start_session(user_id=123, chat_id=456)
        session2 = dialogue_state.start_session(user_id=789, chat_id=456)
        session3 = dialogue_state.start_session(user_id=123, chat_id=999)
        
        chat_sessions = dialogue_state.get_chat_sessions(456)
        assert len(chat_sessions) == 2
        
        chat_sessions = dialogue_state.get_chat_sessions(999)
        assert len(chat_sessions) == 1
    
    def test_get_performance_stats(self, dialogue_state):
        """Тест получения статистики производительности"""
        # Создаем и завершаем тестовую сессию
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        dialogue_state.update_session(
            session_id,
            message_processed=True,
            auto_solved=True,
            success=True,
            duration=10.0
        )
        dialogue_state.end_session(session_id)
        
        stats = dialogue_state.get_performance_stats()
        
        assert stats["total_sessions"] == 1
        assert stats["total_messages"] == 1
        assert stats["total_auto_solved"] == 1
        assert stats["total_duration"] == 10.0
        assert stats["success_rate"] == 1.0
        assert stats["auto_solve_rate"] == 1.0
    
    def test_get_user_performance(self, dialogue_state):
        """Тест получения статистики пользователя"""
        # Создаем и завершаем тестовую сессию
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        dialogue_state.update_session(
            session_id,
            message_processed=True,
            auto_solved=True,
            success=True,
            duration=15.0
        )
        dialogue_state.end_session(session_id)
        
        user_stats = dialogue_state.get_user_performance(123)
        
        assert user_stats["user_id"] == 123
        assert user_stats["total_sessions"] == 1
        assert user_stats["total_messages"] == 1
        assert user_stats["total_auto_solved"] == 1
        assert user_stats["total_duration"] == 15.0
        assert user_stats["success_rate"] == 1.0
        assert user_stats["auto_solve_rate"] == 1.0
    
    def test_reset_metrics(self, dialogue_state):
        """Тест сброса метрик"""
        # Создаем тестовую сессию
        session_id = dialogue_state.start_session(user_id=123, chat_id=456)
        
        # Сбрасываем метрики
        dialogue_state.reset_metrics()
        
        assert dialogue_state.active_sessions == {}
        assert dialogue_state.session_history == []
        assert dialogue_state.metrics.total_dialogues == 0
    
    def test_export_data(self, dialogue_state):
        """Тест экспорта данных"""
        data = dialogue_state.export_data()
        
        assert "metrics" in data
        assert "active_sessions_count" in data
        assert "history_sessions_count" in data
        assert "export_timestamp" in data
        
        metrics = data["metrics"]
        assert "total_dialogues" in metrics
        assert "auto_solved_count" in metrics
        assert "success_rate" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
