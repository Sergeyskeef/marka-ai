"""
Тесты для LLM Integration Hub.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
import pytest_asyncio

from langchain_api.core.llm_integration_hub import (
    LLMIntegrationHub,
    LLMRequest,
    LLMResponse,
    SystemContext,
    get_llm_hub,
    shutdown_llm_hub
)
from langchain_api.services.task_executor import Task, TaskPriority, TaskStatus, TaskCategory, AccessLevel


class TestLLMRequest:
    """Тесты для структуры LLMRequest."""
    
    def test_llm_request_creation(self):
        """Тест создания LLMRequest."""
        request = LLMRequest(
            prompt="Тестовый запрос",
            context={"key": "value"},
            tools=["tool1", "tool2"],
            priority=0.8,
            temperature=0.5
        )
        
        assert request.prompt == "Тестовый запрос"
        assert request.context == {"key": "value"}
        assert request.tools == ["tool1", "tool2"]
        assert request.priority == 0.8
        assert request.temperature == 0.5
    
    def test_llm_request_defaults(self):
        """Тест значений по умолчанию для LLMRequest."""
        request = LLMRequest(prompt="Тест")
        
        assert request.context is None
        assert request.tools is None
        assert request.priority == 0.5
        assert request.temperature == 0.7


class TestLLMResponse:
    """Тесты для структуры LLMResponse."""
    
    def test_llm_response_creation(self):
        """Тест создания LLMResponse."""
        response = LLMResponse(
            content="Тестовый ответ",
            tool_calls=[{"name": "tool1"}],
            confidence=0.9,
            reasoning="Тестовое рассуждение",
            suggestions=["suggestion1"]
        )
        
        assert response.content == "Тестовый ответ"
        assert response.tool_calls == [{"name": "tool1"}]
        assert response.confidence == 0.9
        assert response.reasoning == "Тестовое рассуждение"
        assert response.suggestions == ["suggestion1"]
    
    def test_llm_response_defaults(self):
        """Тест значений по умолчанию для LLMResponse."""
        response = LLMResponse(content="Тест")
        
        assert response.tool_calls is None
        assert response.confidence == 0.0
        assert response.reasoning is None
        assert response.suggestions is None
        assert response.metadata is None


class TestSystemContext:
    """Тесты для структуры SystemContext."""
    
    def test_system_context_creation(self):
        """Тест создания SystemContext."""
        context = SystemContext(
            system_info={"test": "info"},
            memory_status={"test": "status"},
            available_tools=[{"name": "test_tool"}],
            active_tasks={"count": 0},
            command_history=[],
            tools_status={"total": 1},
            resource_status={"cpu": 50},
            current_insights=[],
            timestamp=datetime.now()
        )
        
        assert context.system_info == {"test": "info"}
        assert context.memory_status == {"test": "status"}
        assert len(context.available_tools) == 1
        assert context.available_tools[0]["name"] == "test_tool"


class TestLLMIntegrationHub:
    """Тесты для LLMIntegrationHub."""
    
    @pytest.fixture
    def hub(self):
        """Фикстура для создания тестового экземпляра."""
        with patch('langchain_api.core.llm_integration_hub.ContextManager'), \
             patch('langchain_api.core.llm_integration_hub.MemoryManager'), \
             patch('langchain_api.core.llm_integration_hub.ActionSystem'), \
             patch('langchain_api.core.llm_integration_hub.LearningSystem'), \
             patch('langchain_api.core.llm_integration_hub.get_tools_registry'), \
             patch('langchain_api.core.llm_integration_hub.CommandMonitoringSystem'):
            
            hub = LLMIntegrationHub()
            return hub
    
    def test_hub_initialization(self, hub):
        """Тест инициализации хаба."""
        assert hub.is_initialized is False
        assert hub.request_count == 0
        assert hub.response_count == 0
        assert hub.last_context_update is None
    
    @pytest.mark.asyncio
    async def test_initialize(self, hub):
        """Тест инициализации хаба."""
        # Мокаем методы
        hub._load_system_context = AsyncMock()
        hub._update_tools_registry = AsyncMock()
        hub._initialize_components = AsyncMock()
        
        await hub.initialize()
        
        assert hub.is_initialized is True
        hub._load_system_context.assert_called_once()
        hub._update_tools_registry.assert_called_once()
        hub._initialize_components.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_load_system_context(self, hub):
        """Тест загрузки системного контекста."""
        # Мокаем async методы
        hub.context_manager.update_context = AsyncMock()
        hub.memory_manager.load_core_documents = AsyncMock()
        
        await hub._load_system_context()
        
        # Проверяем, что методы были вызваны
        hub.context_manager.update_context.assert_called_once()
        hub.memory_manager.load_core_documents.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_tools_registry(self, hub):
        """Тест обновления реестра инструментов."""
        # Мокаем методы
        hub.context_manager.update_context = AsyncMock()
        hub.tools_registry.refresh = Mock(return_value={})
        hub.tools_registry.get_tools = Mock(return_value=[])
        
        await hub._update_tools_registry()
        
        # Проверяем, что методы были вызваны
        hub.context_manager.update_context.assert_called_once()
        hub.tools_registry.refresh.assert_called_once()
    
    def test_categorize_tools(self, hub):
        """Тест категоризации инструментов."""
        tools = [
            {"type": "script"},
            {"type": "function"},
            {"type": "script"},
            {"type": "class"}
        ]
        
        categories = hub._categorize_tools(tools)
        
        assert categories["script"] == 2
        assert categories["function"] == 1
        assert categories["class"] == 1
    
    @pytest.mark.asyncio
    async def test_get_system_context(self, hub):
        """Тест получения системного контекста."""
        context = await hub.get_system_context()
        
        assert context.system_info is not None
        assert context.memory_status is not None
        assert context.available_tools is not None
        assert context.active_tasks is not None
        assert context.command_history is not None
        assert context.tools_status is not None
        assert context.resource_status is not None
        assert context.current_insights is not None
        assert context.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_process_request(self, hub):
        """Тест обработки запроса."""
        # Мокаем методы для избежания реальных вызовов
        hub._analyze_task_creation = AsyncMock(return_value={'should_create_task': False})
        hub._call_llm = AsyncMock(return_value=LLMResponse(content="Test response"))
        hub._analyze_response = AsyncMock(return_value=LLMResponse(content="Test response"))
        hub._update_context_from_response = AsyncMock()
        hub._save_to_memory = AsyncMock()
        
        request = LLMRequest(prompt="тестовый запрос")
        response = await hub.process_request(request)
        
        assert response.content == "Test response"
        assert hub.request_count == 1
        assert hub.response_count == 1
    
    @pytest.mark.asyncio
    async def test_process_request_error(self, hub):
        """Тест обработки ошибки в запросе."""
        hub.get_system_context = AsyncMock(side_effect=Exception("Тестовая ошибка"))
        
        request = LLMRequest(prompt="Тестовый запрос")
        response = await hub.process_request(request)
        
        assert response.content.startswith("Ошибка обработки запроса")
        assert response.confidence == 0.0
    
    def test_build_full_context(self, hub):
        """Тест построения полного контекста."""
        request = LLMRequest(
            prompt="Тест",
            context={"req": "value"},
            tools=["tool1"],
            priority=0.8
        )
        
        system_context = SystemContext([], [], {}, [], {}, [])
        
        context = hub._build_full_context(request, system_context)
        
        assert context["prompt"] == "Тест"
        assert context["request_context"] == {"req": "value"}
        assert context["tools"] == ["tool1"]
        assert context["priority"] == 0.8
    
    @pytest.mark.asyncio
    async def test_call_llm(self, hub):
        """Тест вызова LLM (допускает любой ответ, не только заглушку)."""
        context = {"prompt": "Тест"}
        
        response = await hub._call_llm(context)
        
        assert isinstance(response, LLMResponse)
        assert isinstance(response.content, str)
        assert response.content.strip() != ""
        assert isinstance(response.confidence, float)
    
    @pytest.mark.asyncio
    async def test_analyze_response(self, hub):
        """Тест анализа ответа."""
        response = LLMResponse(content="Тестовый ответ")
        request = LLMRequest(prompt="Тест")
        
        hub.context_manager.analyze_llm_response = AsyncMock(return_value={"analysis": "test"})
        
        analyzed_response = await hub._analyze_response(response, request)
        
        assert analyzed_response.metadata is not None
        assert "analysis" in analyzed_response.metadata
        assert "request_id" in analyzed_response.metadata
    
    @pytest.mark.asyncio
    async def test_execute_tool_call(self, hub):
        """Тест выполнения вызова инструмента."""
        tool_call = {"name": "test_tool", "arguments": {"arg1": "value1"}}
        
        # Мокаем инструмент
        mock_tool = {"name": "test_tool", "type": "function"}
        hub.tools_registry.get_tool = AsyncMock(return_value=mock_tool)
        hub._execute_tool = AsyncMock(return_value={"result": "success"})
        hub.command_monitoring.log_result = MagicMock()
        
        result = await hub.execute_tool_call(tool_call)
        
        assert result["result"] == "success"
        hub.command_monitoring.log_result.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_tool_call_not_found(self, hub):
        """Тест выполнения несуществующего инструмента."""
        # Мокаем реестр инструментов
        hub.tools_registry.get_tool = Mock(return_value=None)
        
        tool_call = {"name": "nonexistent_tool", "arguments": {}}
        result = await hub.execute_tool_call(tool_call)
        
        assert "error" in result
        assert "не найден" in result["error"]
    
    @pytest.mark.asyncio
    async def test_get_available_tools(self, hub):
        """Тест получения доступных инструментов."""
        # Мокаем реестр инструментов
        mock_tools = [{"name": "tool1"}, {"name": "tool2"}]
        hub.tools_registry.get_tools_for_llm = Mock(return_value=mock_tools)
        
        tools = await hub.get_available_tools()
        
        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[1]["name"] == "tool2"
    
    @pytest.mark.asyncio
    async def test_analyze_system_state(self, hub):
        """Тест анализа состояния системы."""
        hub.get_system_context = AsyncMock(return_value=SystemContext([], [], {}, [], {}, []))
        hub.tools_registry.get_available_tools = AsyncMock(return_value=[])
        hub.memory_manager.get_status = AsyncMock(return_value={})
        
        state = await hub.analyze_system_state()
        
        assert "system_context" in state
        assert "performance_metrics" in state
        assert "component_status" in state
    
    @pytest.mark.asyncio
    async def test_shutdown(self, hub):
        """Тест завершения работы."""
        hub._save_state = AsyncMock()
        hub._shutdown_components = AsyncMock()
        
        await hub.shutdown()
        
        hub._save_state.assert_called_once()
        hub._shutdown_components.assert_called_once()


class TestGlobalFunctions:
    """Тесты для глобальных функций."""
    
    @pytest.mark.asyncio
    async def test_get_llm_hub(self):
        """Тест получения глобального экземпляра."""
        with patch('langchain_api.core.llm_integration_hub._llm_hub', None), \
             patch('langchain_api.core.llm_integration_hub.LLMIntegrationHub') as mock_hub_class:
            
            mock_hub = MagicMock()
            mock_hub_class.return_value = mock_hub
            mock_hub.initialize = AsyncMock()
            
            hub = await get_llm_hub()
            
            assert hub == mock_hub
            mock_hub.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_llm_hub(self):
        """Тест завершения работы глобального экземпляра."""
        with patch('langchain_api.core.llm_integration_hub._llm_hub') as mock_hub:
            mock_hub.shutdown = AsyncMock()
            
            await shutdown_llm_hub()
            
            mock_hub.shutdown.assert_called_once()


class TestLLMIntegrationHubTaskExecutor:
    """Тесты интеграции TaskExecutor с LLM Integration Hub."""

    @pytest_asyncio.fixture
    async def hub(self):
        """Фикстура для LLM Integration Hub."""
        hub = LLMIntegrationHub()
        await hub.initialize()
        yield hub
        await hub.shutdown()

    @pytest.fixture
    def sample_task(self):
        """Фикстура для тестовой задачи."""
        return Task(
            id="test_task_123",
            name="test_task",
            description="Тестовая задача",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            parameters={"timeout": 60},
            category=TaskCategory.CUSTOM,
            access_level=AccessLevel.EXECUTE,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    @pytest.mark.asyncio
    async def test_get_active_tasks(self, hub, sample_task):
        """Тест получения активных задач."""
        # Мокаем TaskExecutor - метод get_task_list вызывается дважды
        # для PENDING и RUNNING задач
        hub.task_executor.get_task_list = Mock(side_effect=[
            [sample_task],  # PENDING задачи
            []              # RUNNING задачи
        ])
        
        tasks = await hub._get_active_tasks()
        
        assert len(tasks) == 1
        assert tasks[0].id == sample_task.id
        assert tasks[0].name == sample_task.name

    @pytest.mark.asyncio
    async def test_analyze_task_creation_should_create(self, hub):
        """Тест анализа создания задачи - должен создать задачу."""
        request = LLMRequest(prompt="Создай задачу для тестирования системы")
        
        result = await hub._analyze_task_creation(request, {})
        
        assert result['should_create_task'] is True
        assert result['priority'] == TaskPriority.MEDIUM
        assert result['category'] == TaskCategory.SANDBOX

    @pytest.mark.asyncio
    async def test_analyze_task_creation_high_priority(self, hub):
        """Тест анализа создания задачи с высоким приоритетом."""
        request = LLMRequest(prompt="Срочно создай задачу для критичного анализа")
        
        result = await hub._analyze_task_creation(request, {})
        
        assert result['should_create_task'] is True
        assert result['priority'] == TaskPriority.HIGH
        assert result['category'] == TaskCategory.ANALYSIS

    @pytest.mark.asyncio
    async def test_analyze_task_creation_should_not_create(self, hub):
        """Тест анализа создания задачи - не должен создавать задачу."""
        request = LLMRequest(prompt="Просто вопрос о системе")
        
        result = await hub._analyze_task_creation(request, {})
        
        assert result['should_create_task'] is False

    @pytest.mark.asyncio
    async def test_extract_task_parameters_timeout(self, hub):
        """Тест извлечения параметров задачи - timeout."""
        prompt = "Создай задачу с таймаутом 30 сек"
        
        parameters = hub._extract_task_parameters(prompt)
        
        assert parameters['timeout'] == 30

    @pytest.mark.asyncio
    async def test_extract_task_parameters_retry(self, hub):
        """Тест извлечения параметров задачи - retry."""
        prompt = "Создай задачу с повторными попытками"
        
        parameters = hub._extract_task_parameters(prompt)
        
        assert parameters['retry_count'] == 3

    @pytest.mark.asyncio
    async def test_create_task_from_request(self, hub):
        """Тест создания задачи из запроса."""
        request = LLMRequest(prompt="Создай задачу для тестирования")
        analysis = {
            'should_create_task': True,
            'priority': TaskPriority.MEDIUM,
            'category': TaskCategory.CUSTOM,
            'extracted_parameters': {'timeout': 60}
        }
        
        with patch.object(hub.task_executor, 'create_task') as mock_create:
            mock_task = Mock()
            mock_task.id = "test_task_123"
            mock_task.name = "llm_task_создай_задачу_для_тестирования"
            mock_create.return_value = mock_task
            
            task = await hub._create_task_from_request(request, analysis)
            
            assert task.id == "test_task_123"
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_task_name(self, hub):
        """Тест генерации имени задачи."""
        prompt = "Создай задачу для тестирования системы"
        
        name = hub._generate_task_name(prompt)
        
        assert name.startswith("llm_task_")
        assert "создай" in name
        assert "задачу" in name

    @pytest.mark.asyncio
    async def test_process_request_with_task_creation(self, hub):
        """Тест обработки запроса с созданием задачи."""
        request = LLMRequest(prompt="Создай задачу для тестирования")
        
        with patch.object(hub, '_analyze_task_creation') as mock_analyze:
            mock_analyze.return_value = {
                'should_create_task': True,
                'priority': TaskPriority.MEDIUM,
                'category': TaskCategory.CUSTOM,
                'extracted_parameters': {}
            }
            
            with patch.object(hub, '_create_task_from_request') as mock_create:
                mock_task = Mock()
                mock_task.id = "test_task_123"
                mock_task.name = "test_task"
                mock_create.return_value = mock_task
                
                response = await hub.process_request(request)
                
                assert "создана успешно" in response.content
                assert response.confidence == 0.9

    @pytest.mark.asyncio
    async def test_execute_task_success(self, hub, sample_task):
        """Тест успешного выполнения задачи."""
        with patch.object(hub.task_executor, 'get_task') as mock_get:
            mock_get.return_value = sample_task
            
            with patch.object(hub.task_executor, 'execute_next_task') as mock_execute:
                mock_execute.return_value = sample_task
                
                result = await hub.execute_task("test_task_123")
                
                assert result['success'] is True
                assert result['task_id'] == "test_task_123"

    @pytest.mark.asyncio
    async def test_execute_task_not_found(self, hub):
        """Тест выполнения несуществующей задачи."""
        with patch.object(hub.task_executor, 'get_task') as mock_get:
            mock_get.return_value = None
            
            result = await hub.execute_task("nonexistent_task")
            
            assert 'error' in result
            assert "не найдена" in result['error']

    @pytest.mark.asyncio
    async def test_get_task_status(self, hub, sample_task):
        """Тест получения статуса задачи."""
        with patch.object(hub.task_executor, 'get_task') as mock_get:
            mock_get.return_value = sample_task
            
            result = await hub.get_task_status("test_task_123")
            
            assert result['task_id'] == sample_task.id
            assert result['name'] == sample_task.name
            assert result['status'] == TaskStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, hub):
        """Тест получения статуса несуществующей задачи."""
        with patch.object(hub.task_executor, 'get_task') as mock_get:
            mock_get.return_value = None
            
            result = await hub.get_task_status("nonexistent_task")
            
            assert 'error' in result
            assert "не найдена" in result['error']

    @pytest.mark.asyncio
    async def test_cancel_task_success(self, hub):
        """Тест успешной отмены задачи."""
        with patch.object(hub.task_executor, 'cancel_task') as mock_cancel:
            mock_cancel.return_value = True
            
            result = await hub.cancel_task("test_task_123")
            
            assert result['success'] is True
            assert "отменена" in result['message']

    @pytest.mark.asyncio
    async def test_cancel_task_failure(self, hub):
        """Тест неудачной отмены задачи."""
        with patch.object(hub.task_executor, 'cancel_task') as mock_cancel:
            mock_cancel.return_value = False
            
            result = await hub.cancel_task("test_task_123")
            
            assert result['success'] is False
            assert "Не удалось" in result['message']

    @pytest.mark.asyncio
    async def test_system_context_includes_tasks(self, hub, sample_task):
        """Тест включения задач в системный контекст."""
        with patch.object(hub, '_get_active_tasks') as mock_get_tasks:
            mock_get_tasks.return_value = [{
                'id': sample_task.id,
                'name': sample_task.name,
                'status': sample_task.status.value
            }]
            
            context = await hub.get_system_context()
            
            assert len(context.active_tasks) == 1
            assert context.active_tasks[0]['id'] == sample_task.id

    @pytest.mark.asyncio
    async def test_task_creation_with_different_categories(self, hub):
        """Тест создания задач с разными категориями."""
        test_cases = [
            ("Создай задачу для тестирования", TaskCategory.SANDBOX),
            ("Создай задачу для оптимизации", TaskCategory.CUSTOM),
            ("Создай задачу для анализа", TaskCategory.ANALYSIS),
            ("Создай обычную задачу", TaskCategory.CUSTOM)
        ]
        
        for prompt, expected_category in test_cases:
            request = LLMRequest(prompt=prompt)
            result = await hub._analyze_task_creation(request, {})
            
            if result['should_create_task']:
                assert result['category'] == expected_category

    @pytest.mark.asyncio
    async def test_task_creation_with_different_priorities(self, hub):
        """Тест создания задач с разными приоритетами."""
        test_cases = [
            ("Срочно создай задачу", TaskPriority.HIGH),
            ("Создай важную задачу", TaskPriority.HIGH),
            ("Создай обычную задачу", TaskPriority.MEDIUM),
            ("Создай неважную задачу", TaskPriority.LOW),
            ("Создай задачу потом", TaskPriority.LOW)
        ]
        
        for prompt, expected_priority in test_cases:
            request = LLMRequest(prompt=prompt)
            result = await hub._analyze_task_creation(request, {})
            
            if result['should_create_task']:
                assert result['priority'] == expected_priority


class TestLLMIntegrationHubFullContext:
    """Тесты полного контекста системы."""
    
    @pytest_asyncio.fixture
    async def hub(self):
        """Фикстура для LLM Integration Hub."""
        hub = LLMIntegrationHub()
        await hub.initialize()
        yield hub
        await hub.shutdown()
    
    @pytest.mark.asyncio
    async def test_get_full_system_context(self, hub):
        """Тест получения полного контекста системы."""
        context = await hub.get_full_system_context()
        
        assert context.system_info is not None
        assert context.memory_status is not None
        assert context.available_tools is not None
        assert context.active_tasks is not None
        assert context.command_history is not None
        assert context.tools_status is not None
        assert context.resource_status is not None
        assert context.current_insights is not None
        assert context.timestamp is not None
        
        # Проверяем структуру active_tasks
        assert 'active_tasks_count' in context.active_tasks
        assert 'tasks_by_status' in context.active_tasks
        assert 'recent_tasks' in context.active_tasks
    
    @pytest.mark.asyncio
    async def test_get_resource_status(self, hub):
        """Тест получения статуса ресурсов."""
        status = await hub._get_resource_status()
        
        # Проверяем, что статус содержит ожидаемые поля
        expected_fields = ['cpu_percent', 'memory_percent', 'disk_percent', 'active_connections']
        for field in expected_fields:
            assert field in status
    
    @pytest.mark.asyncio
    async def test_get_current_insights(self, hub):
        """Тест получения текущих инсайтов."""
        insights = await hub._get_current_insights()
        
        # Проверяем, что insights - это список
        assert isinstance(insights, list)
        
        # Если есть инсайты, проверяем их структуру
        for insight in insights:
            assert 'type' in insight
            assert 'message' in insight
            assert 'priority' in insight
            assert insight['type'] in ['warning', 'error', 'info']
            assert insight['priority'] in ['low', 'medium', 'high']
    
    @pytest.mark.asyncio
    async def test_update_system_context(self, hub):
        """Тест обновления контекста системы."""
        changes = {
            'new_feature': 'test_feature',
            'status': 'updated'
        }
        
        result = await hub.update_system_context(changes)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_link_related_events(self, hub):
        """Тест связывания связанных событий."""
        event_id = "test_event_123"
        related_events = ["event_1", "event_2", "event_3"]
        
        result = await hub.link_related_events(event_id, related_events)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_full_context_with_active_tasks(self, hub):
        """Тест полного контекста с активными задачами."""
        # Создаем тестовую задачу
        request = LLMRequest(prompt="Создай задачу для тестирования контекста")
        task = await hub._create_task_from_request(request, {
            'should_create_task': True,
            'priority': TaskPriority.MEDIUM,
            'category': TaskCategory.CUSTOM,
            'extracted_parameters': {}
        })
        
        # Получаем полный контекст
        context = await hub.get_full_system_context()
        
        # Проверяем, что задача отражена в контексте
        assert context.active_tasks['active_tasks_count'] >= 1
        
        # Проверяем, что задача есть в группировке по статусу
        task_status = task.status.value
        assert task_status in context.active_tasks['tasks_by_status']
        assert len(context.active_tasks['tasks_by_status'][task_status]) >= 1
        
        # Очищаем тестовую задачу
        await hub.cancel_task(task.id)


if __name__ == "__main__":
    pytest.main([__file__]) 