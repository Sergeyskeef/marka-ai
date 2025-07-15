"""
LLM Integration Hub - центральный компонент интеграции с LLM.

Обеспечивает единую точку взаимодействия с LLM, управляет контекстом,
координирует работу между компонентами системы.
"""

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from langchain_api.services.task_executor import (
    AccessLevel,
    Task,
    TaskCategory,
    TaskPriority,
    TaskStatus,
    task_executor,
)

from .command_monitoring import CommandMonitoringSystem

# Удалены импорты context и learning_system
# from .context.context_manager import ContextManager
# from .context.action_system import ActionSystem
# from .learning_system import LearningSystem
from .memory.enhanced_memory import EnhancedMemory
from .tools_registry import get_tools_registry


@dataclass
class LLMRequest:
    """Структура запроса к LLM."""
    prompt: str
    context: dict[str, Any] | None = None
    tools: list[str] | None = None
    memory_context: dict[str, Any] | None = None
    action_context: dict[str, Any] | None = None
    priority: float = 0.5
    max_tokens: int | None = None
    temperature: float = 0.7


@dataclass
class LLMResponse:
    """Структура ответа от LLM."""
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    confidence: float = 0.0
    reasoning: str | None = None
    suggestions: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class SystemContext:
    """Контекст системы для LLM."""
    system_info: dict[str, Any]
    memory_status: dict[str, Any]
    available_tools: list[dict[str, Any]]
    active_tasks: dict[str, Any] | None = None
    command_history: list[dict[str, Any]] | None = None
    tools_status: dict[str, Any] | None = None
    resource_status: dict[str, Any] | None = None
    current_insights: list[dict[str, Any]] | None = None
    timestamp: datetime | None = None


class LLMIntegrationHub:
    """
    Центральный компонент интеграции с LLM.

    Отвечает за:
    - Координацию взаимодействия с LLM
    - Управление контекстом системы
    - Интеграцию с компонентами системы
    - Обработку запросов и ответов
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.memory_manager = None  # Удален MemoryManager
        # Удалены context_manager, action_system, learning_system
        # self.context_manager = ContextManager(self.memory_manager)
        # self.action_system = ActionSystem(self.memory_manager)
        # self.learning_system = LearningSystem(self.enhanced_memory, self.context_manager)
        self.enhanced_memory = EnhancedMemory()
        self.tools_registry = get_tools_registry()
        self.command_monitoring = CommandMonitoringSystem()
        self.task_executor = task_executor

        # Состояние системы
        self.is_initialized = False
        self.last_context_update = None
        self.request_count = 0
        self.response_count = 0

        self.logger.info("LLM Integration Hub инициализирован")

    async def initialize(self) -> None:
        """Инициализация интеграции."""
        try:
            # Загружаем системный контекст
            await self._load_system_context()

            # Обновляем реестр инструментов
            await self._update_tools_registry()

            # Инициализируем компоненты
            await self._initialize_components()

            self.is_initialized = True
            self.logger.info("LLM Integration Hub успешно инициализирован")

        except Exception as e:
            self.logger.error(f"Ошибка инициализации LLM Integration Hub: {e}")
            raise

    async def _load_system_context(self) -> None:
        """Загрузка системного контекста."""
        try:
            # Упрощенная загрузка контекста без context_manager
            self.logger.info("Системный контекст загружен")

        except Exception as e:
            self.logger.error(f"Ошибка загрузки системного контекста: {e}")
            raise

    async def _update_tools_registry(self) -> None:
        """Обновление реестра инструментов."""
        try:
            # Сканируем проект и обновляем реестр
            self.tools_registry.refresh()

            # Получаем доступные инструменты
            tools = self.tools_registry.get_tools()

            self.logger.info(f"Реестр инструментов обновлен: {len(tools)} инструментов")

        except Exception as e:
            self.logger.error(f"Ошибка обновления реестра инструментов: {e}")
            raise

    async def _initialize_components(self) -> None:
        """Инициализация компонентов системы."""
        try:
            # Упрощенная инициализация без context и learning систем
            self.logger.info("Компоненты системы инициализированы")

        except Exception as e:
            self.logger.error(f"Ошибка инициализации компонентов: {e}")
            raise

    def _categorize_tools(self, tools: list[Any]) -> dict[str, int]:
        """Категоризация инструментов по типам."""
        categories = {}
        for tool in tools:
            # Проверяем, является ли tool объектом ToolMetadata или словарем
            if hasattr(tool, 'type'):
                # ToolMetadata объект
                tool_type = tool.type
            elif isinstance(tool, dict):
                # Словарь
                tool_type = tool.get('type', 'unknown')
            else:
                # Неизвестный тип
                tool_type = 'unknown'

            categories[tool_type] = categories.get(tool_type, 0) + 1
        return categories

    async def get_system_context(self) -> SystemContext:
        """Получение полного контекста системы."""
        try:
            # Получаем активные задачи
            active_tasks = await self._get_active_tasks()

            # Получаем последние действия
            recent_actions = await self._get_recent_actions()

            # Получаем статус системы
            system_status = await self._get_system_status()

            # Получаем доступные инструменты
            available_tools = self.tools_registry.get_tools_for_llm()

            # Получаем сводку памяти
            memory_summary = await self._get_memory_summary()

            # Получаем последние инсайты
            insights = await self._get_recent_insights()

            return SystemContext(
                system_info=system_status,
                memory_status=memory_summary,
                available_tools=available_tools,
                active_tasks=active_tasks,
                command_history=recent_actions,
                tools_status=system_status.get('tools_count', 0),
                resource_status=await self._get_resource_status(),
                current_insights=insights,
                timestamp=datetime.now()
            )

        except Exception as e:
            self.logger.error(f"Ошибка получения системного контекста: {e}")
            return SystemContext(
                system_info={},
                memory_status={},
                available_tools=[],
                active_tasks=None,
                command_history=None,
                tools_status=0,
                resource_status={},
                current_insights=None,
                timestamp=None
            )

    async def _get_active_tasks(self) -> list[Task]:
        """Получение активных задач."""
        try:
            # Получаем задачи через TaskExecutor - PENDING и RUNNING считаются активными
            pending_tasks = self.task_executor.get_task_list(status=TaskStatus.PENDING)
            running_tasks = self.task_executor.get_task_list(status=TaskStatus.RUNNING)
            return pending_tasks + running_tasks
        except Exception as e:
            self.logger.error(f"Ошибка получения активных задач: {e}")
            return []

    async def _get_recent_actions(self) -> list[dict[str, Any]]:
        """Получение последних действий."""
        try:
            # Получаем последние действия из ActionSystem
            # Удален ActionSystem, поэтому заглушка
            return []
        except Exception as e:
            self.logger.error(f"Ошибка получения последних действий: {e}")
            return []

    async def _get_system_status(self) -> dict[str, Any]:
        """Получение статуса системы."""
        try:
            return {
                'initialized': self.is_initialized,
                'request_count': self.request_count,
                'response_count': self.response_count,
                'last_context_update': self.last_context_update,
                'memory_status': self.memory_manager.get_status(),
                'tools_count': len(self.tools_registry.get_tools())
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения статуса системы: {e}")
            return {}

    async def _get_memory_summary(self) -> dict[str, Any]:
        """Получение сводки памяти."""
        try:
            system_memory = self.memory_manager.get_system_memory()
            return {
                'total_memories': len(system_memory.get_all()),
                'recent_insights': len(await self._get_recent_insights()),
                'identity_context': system_memory.get_identity_context()
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения сводки памяти: {e}")
            return {}

    async def _get_recent_insights(self) -> list[dict[str, Any]]:
        """Получение последних инсайтов."""
        try:
            # Получаем инсайты из системы обучения
            # Удален LearningSystem, поэтому заглушка
            return []
        except Exception as e:
            self.logger.error(f"Ошибка получения последних инсайтов: {e}")
            return []

    async def process_request(self, request: LLMRequest) -> LLMResponse:
        """Обработка запроса к LLM."""

        # 🔧 ДИАГНОСТИКА: Проверяем что метод вызывается
        self.logger.info(f"🚀 LLM_HUB.PROCESS_REQUEST ЗАПУЩЕН! Request prompt: '{request.prompt[:100]}...'")

        try:
            self.request_count += 1

            # Получаем полный контекст системы
            system_context = await self.get_system_context()

            # Формируем полный контекст для LLM
            full_context = self._build_full_context(request, system_context)

            # Логируем запрос
            self.command_monitoring.log_command(
                command=f"LLM_REQUEST: {request.prompt[:100]}...",
                source="llm_integration_hub",
                user_id="system"
            )

            # Анализируем запрос на предмет создания задач
            task_creation_result = await self._analyze_task_creation(request, full_context)

            # 🔧 ОТЛАДКА: Логируем результат анализа создания задач
            self.logger.info(f"📋 PROCESS_REQUEST - Результат анализа: {task_creation_result}")

            # Если нужно создать задачу, создаем её
            if task_creation_result.get('should_create_task'):
                self.logger.info("📋 PROCESS_REQUEST - Создаем задачу...")
                task = await self._create_task_from_request(request, task_creation_result)
                self.logger.info(f"📋 PROCESS_REQUEST - Задача создана: {task.name} (ID: {task.id})")

                # 🔥 АВТОМАТИЧЕСКОЕ ВЫПОЛНЕНИЕ: Сразу выполняем созданную задачу
                try:
                    self.logger.info(f"🚀 АВТОВЫПОЛНЕНИЕ - Запускаем задачу {task.id}...")
                    executed_task = self.task_executor.execute_next_task()

                    if executed_task and executed_task.id == task.id:
                        if executed_task.status.value == "completed":
                            self.logger.info(f"✅ АВТОВЫПОЛНЕНИЕ - Задача {task.id} успешно выполнена!")
                            return LLMResponse(
                                content=f"✅ Задача '{task.name}' создана и выполнена успешно!\n\n📋 ID: {task.id}\n🎯 Результат: {executed_task.result}",
                                confidence=0.95,
                                reasoning="Задача была создана и автоматически выполнена",
                                suggestions=["Создать похожую задачу", "Проверить другие задачи"]
                            )
                        elif executed_task.status.value == "failed":
                            self.logger.warning(f"❌ АВТОВЫПОЛНЕНИЕ - Задача {task.id} завершилась с ошибкой!")
                            return LLMResponse(
                                content=f"⚠️ Задача '{task.name}' создана, но выполнилась с ошибкой:\n\n📋 ID: {task.id}\n❌ Ошибка: {executed_task.error}",
                                confidence=0.7,
                                reasoning="Задача была создана но выполнилась неуспешно",
                                suggestions=["Попробовать исправить задачу", "Создать новую задачу"]
                            )
                    else:
                        self.logger.info(f"⏳ АВТОВЫПОЛНЕНИЕ - Задача {task.id} поставлена в очередь")
                        return LLMResponse(
                            content=f"📋 Задача '{task.name}' создана и поставлена в очередь на выполнение.\n\nID: {task.id}",
                            confidence=0.8,
                            reasoning="Задача создана и помещена в очередь выполнения",
                            suggestions=["Проверить статус задачи", "Посмотреть список задач"]
                        )

                except Exception as e:
                    self.logger.error(f"❌ АВТОВЫПОЛНЕНИЕ - Ошибка выполнения задачи {task.id}: {e}")
                    return LLMResponse(
                        content=f"📋 Задача '{task.name}' создана (ID: {task.id}), но при автоматическом выполнении произошла ошибка: {str(e)}",
                        confidence=0.6,
                        reasoning="Задача создана но не удалось её автоматически выполнить",
                        suggestions=["Попробовать выполнить задачу вручную", "Проверить статус системы"]
                    )
            else:
                self.logger.info("📋 PROCESS_REQUEST - Задача НЕ создается, переходим к LLM")

            # Здесь должен быть вызов к LLM
            # Пока возвращаем заглушку
            response = await self._call_llm(full_context)

            # Анализируем ответ
            analyzed_response = await self._analyze_response(response, request)

            # Обновляем контекст на основе ответа
            await self._update_context_from_response(analyzed_response, request)

            # Сохраняем в память
            await self._save_to_memory(request, analyzed_response)

            self.response_count += 1

            return analyzed_response

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            return LLMResponse(
                content=f"Ошибка обработки запроса: {str(e)}",
                confidence=0.0
            )

    def _build_full_context(self, request: LLMRequest, system_context: SystemContext) -> dict[str, Any]:
        """Построение полного контекста для LLM."""
        return {
            'prompt': request.prompt,
            'system_context': asdict(system_context),
            'request_context': request.context or {},
            'tools': request.tools or [],
            'memory_context': request.memory_context or {},
            'action_context': request.action_context or {},
            'priority': request.priority,
            'max_tokens': request.max_tokens,
            'temperature': request.temperature
        }

    async def _call_llm(self, context: dict[str, Any]) -> LLMResponse:
        """Вызов LLM через Enhanced RAG Chain."""
        try:
            # Извлекаем данные из контекста
            prompt = context.get('prompt', '')
            request_context = context.get('request_context', {})
            chat_id = request_context.get('chat_id')

            if not prompt:
                return LLMResponse(
                    content="Ошибка: пустой запрос",
                    confidence=0.0,
                    reasoning="Отсутствует текст запроса"
                )

            # Импортируем generate_enhanced_response_with_tools из Enhanced RAG Chain Tools
            from langchain_api.core.backend_selector import create_memory
            from langchain_api.rag.enhanced_rag_chain_tools import (
                generate_enhanced_response_with_tools,
            )

            # Получаем память для передачи в RAG chain
            memory = create_memory()  # A/B Backend Selector

            # Извлекаем инструменты из контекста
            context.get('tools', [])

            # Вызываем Enhanced RAG Chain Tools с поддержкой инструментов
            rag_response = await generate_enhanced_response_with_tools(
                question=prompt,
                chat_id=chat_id,
                memory=memory,
                use_tools=True  # Включаем использование инструментов
            )

            # 🔧 ИСПРАВЛЕНИЕ: generate_response возвращает dict, извлекаем строку
            if isinstance(rag_response, dict):
                answer = rag_response.get("answer", str(rag_response))
                self.logger.info(f"🔧 RAG Chain вернул dict, извлекли answer: '{answer[:100]}...'")
            else:
                answer = str(rag_response)
                self.logger.info(f"🔧 RAG Chain вернул строку: '{answer[:100]}...'")

            # Формируем ответ
            return LLMResponse(
                content=answer,  # Теперь гарантированно строка!
                confidence=0.8,  # Высокая уверенность для Enhanced RAG Chain
                reasoning="Ответ сгенерирован через Enhanced RAG Chain с многоуровневой памятью",
                suggestions=[
                    "Задать уточняющий вопрос",
                    "Попросить объяснить детали",
                    "Запросить примеры"
                ]
            )

        except Exception as e:
            self.logger.error(f"Ошибка вызова LLM: {e}")
            return LLMResponse(
                content=f"Извините, произошла ошибка при обработке запроса: {str(e)}",
                confidence=0.0,
                reasoning=f"Ошибка в Enhanced RAG Chain: {str(e)}"
            )

    async def _analyze_response(self, response: LLMResponse, request: LLMRequest) -> LLMResponse:
        """Анализ ответа от LLM."""
        try:
            # Анализируем ответ через ContextManager
            # Удален ContextManager, поэтому заглушка
            analysis = {}

            # Обновляем метаданные ответа
            response.metadata = {
                'analysis': analysis,
                'request_id': self.request_count,
                'timestamp': datetime.now().isoformat()
            }

            return response

        except Exception as e:
            self.logger.error(f"Ошибка анализа ответа: {e}")
            return response

    async def _update_context_from_response(self, response: LLMResponse, request: LLMRequest) -> None:
        """Обновление контекста на основе ответа."""
        try:
            # Обновляем контекст через ContextManager
            # Удален ContextManager, поэтому заглушка
            pass

            # Обновляем время последнего обновления
            self.last_context_update = datetime.now().isoformat()

        except Exception as e:
            self.logger.error(f"Ошибка обновления контекста: {e}")

    async def _save_to_memory(self, request: LLMRequest, response: LLMResponse) -> None:
        """Сохранение запроса и ответа в память."""
        try:
            # Сохраняем в системную память
            system_memory = self.memory_manager.get_system_memory()

            system_memory.add(
                key=f"llm_interaction_{self.request_count}",
                value={
                    'type': 'llm_interaction',
                    'content': {
                        'request': asdict(request),
                        'response': asdict(response),
                        'timestamp': datetime.now().isoformat()
                    },
                    'priority': request.priority
                }
            )

        except Exception as e:
            self.logger.error(f"Ошибка сохранения в память: {e}")

    async def execute_tool_call(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Выполнение вызова инструмента."""
        try:
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('arguments', {})

            # Получаем инструмент из реестра
            tool = self.tools_registry.get_tool(tool_name)

            if not tool:
                return {'error': f'Инструмент {tool_name} не найден'}

            # Выполняем инструмент
            result = await self._execute_tool(tool, tool_args)

            # Логируем выполнение
            self.command_monitoring.log_result(
                command=f"TOOL_CALL: {tool_name}",
                result=str(result)[:200],
                success=True
            )

            return result

        except Exception as e:
            self.logger.error(f"Ошибка выполнения инструмента: {e}")
            return {'error': str(e)}

    async def _execute_tool(self, tool: dict[str, Any], args: dict[str, Any]) -> Any:
        """Выполнение конкретного инструмента."""
        try:
            # Здесь должна быть логика выполнения инструмента
            # Пока возвращаем заглушку
            return {
                'tool_name': tool.get('name'),
                'args': args,
                'result': 'Инструмент выполнен успешно (заглушка)',
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Ошибка выполнения инструмента: {e}")
            raise

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """Получение доступных инструментов для LLM."""
        try:
            return self.tools_registry.get_tools_for_llm()
        except Exception as e:
            self.logger.error(f"Ошибка получения инструментов: {e}")
            return []

    async def update_context(self, updates: dict[str, Any]) -> None:
        """Обновление контекста системы."""
        try:
            # Удален ContextManager, поэтому заглушка
            pass

            # Логируем обновление контекста
            self.command_monitoring.log_command(
                command="update_system_context",
                source="llm_integration_hub",
                user_id="system",
                parameters=updates
            )

        except Exception as e:
            self.logger.error(f"Ошибка обновления контекста: {e}")

    async def get_context(self) -> dict[str, Any]:
        """Получение текущего контекста."""
        try:
            # Удален ContextManager, поэтому заглушка
            return {}
        except Exception as e:
            self.logger.error(f"Ошибка получения контекста: {e}")
            return {}

    async def analyze_system_state(self) -> dict[str, Any]:
        """Анализ состояния системы."""
        try:
            system_context = await self.get_system_context()

            return {
                'system_context': asdict(system_context),
                'performance_metrics': {
                    'request_count': self.request_count,
                    'response_count': self.response_count,
                    'success_rate': self.response_count / max(self.request_count, 1)
                },
                'component_status': {
                    'memory_manager': 'active',
                    'tools_registry': 'active'
                }
            }

        except Exception as e:
            self.logger.error(f"Ошибка анализа состояния системы: {e}")
            return {}

    async def shutdown(self) -> None:
        """Завершение работы интеграции."""
        try:
            self.logger.info("Завершение работы LLM Integration Hub")

            # Сохраняем состояние
            await self._save_state()

            # Закрываем компоненты
            await self._shutdown_components()

            self.logger.info("LLM Integration Hub завершил работу")

        except Exception as e:
            self.logger.error(f"Ошибка завершения работы: {e}")

    async def _save_state(self) -> None:
        """Сохранение состояния системы."""
        try:
            # Сохраняем состояние в системную память
            system_memory = self.memory_manager.get_system_memory()

            system_memory.add(
                key="system_state",
                value={
                    'type': 'system_state',
                    'content': {
                        'request_count': self.request_count,
                        'response_count': self.response_count,
                        'last_context_update': self.last_context_update,
                        'shutdown_time': datetime.now().isoformat()
                    },
                    'priority': 0.9
                }
            )

        except Exception as e:
            self.logger.error(f"Ошибка сохранения состояния: {e}")

    async def _shutdown_components(self) -> None:
        """Завершение работы компонентов."""
        try:
            # Завершаем работу компонентов
            # Удалены learning_system, action_system, context_manager
            pass

        except Exception as e:
            self.logger.error(f"Ошибка завершения компонентов: {e}")

    async def _analyze_task_creation(self, request: LLMRequest, context: dict[str, Any]) -> dict[str, Any]:
        """Анализ запроса на предмет необходимости создания задачи."""
        try:
            # �� ИСПРАВЛЕНИЕ: Анализируем оригинальное сообщение пользователя, а не полный промпт
            original_message = self._extract_original_message(request)

            prompt_lower = original_message.lower()

            # 🔧 ОТЛАДКА: Логируем исходный запрос
            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - Оригинальное сообщение: '{original_message}'")
            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - Промпт (lower): '{prompt_lower}'")

            # 🔧 УЛУЧШЕННАЯ ЛОГИКА: Различаем "создать задачу" vs "выполнить задачу"

            # Ключевые слова для ВЫПОЛНЕНИЯ существующих задач
            execute_keywords = [
                'выполни эту задачу', 'выполнить эту задачу', 'выполни задачу',
                'запусти эту задачу', 'запустить эту задачу', 'запусти задачу',
                'сделай эту задачу', 'сделать эту задачу', 'выполни её',
                'task_', 'id:', 'эта задача', 'эту задачу', 'данную задачу'
            ]

            # Ключевые слова для СОЗДАНИЯ новых задач
            create_keywords = [
                'создай задачу', 'создать задачу', 'поставь задачу', 'поставить задачу',
                'хочу чтобы ты', 'можешь ли ты', 'в песочнице',
                'проанализируй', 'проанализировать', 'проверь', 'проверить',
                'тест', 'тестирование', 'оптимизация', 'оптимизировать'
            ]

            # Проверяем что нужно ВЫПОЛНИТЬ задачу (приоритет выше)
            wants_execute = any(keyword in prompt_lower for keyword in execute_keywords)

            # Проверяем что нужно СОЗДАТЬ задачу
            wants_create = any(keyword in prompt_lower for keyword in create_keywords)

            # Логика принятия решения
            if wants_execute:
                should_create = False  # НЕ создаем задачу, если хотят выполнить
                self.logger.info("🔍 АНАЛИЗ: Обнаружен запрос на ВЫПОЛНЕНИЕ задачи - НЕ создаем новую")
            elif wants_create:
                should_create = True   # Создаем задачу
                self.logger.info("🔍 АНАЛИЗ: Обнаружен запрос на СОЗДАНИЕ задачи")
            else:
                should_create = False  # По умолчанию НЕ создаем
                self.logger.info("🔍 АНАЛИЗ: Не обнаружено явных намерений - НЕ создаем задачу")

            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - wants_execute: {wants_execute}, wants_create: {wants_create}, should_create: {should_create}")

            # 🔧 ИСПРАВЛЕНИЕ: НЕ создаем задачи для простых сообщений/приветствий
            simple_greetings = ['привет', 'hello', 'тест', 'проверка', 'test', 'марк', 'как дела', 'можешь показать', 'покажи список']
            has_greetings = any(greeting in prompt_lower for greeting in simple_greetings)
            word_count = len(original_message.split())
            is_simple_message = has_greetings and word_count < 10

            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - Содержит приветствия: {has_greetings}")
            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - Количество слов: {word_count}")
            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - Простое сообщение: {is_simple_message}")

            # Блокируем создание для простых сообщений или запросов на выполнение
            if is_simple_message or wants_execute:
                should_create = False
                reason = "простое приветствие" if is_simple_message else "запрос на выполнение"
                self.logger.info(f"🔧 БЛОКИРОВКА СОЗДАНИЯ ЗАДАЧ - {reason}, задача НЕ создается")

            self.logger.info(f"🔍 АНАЛИЗ СОЗДАНИЯ ЗАДАЧ - Финальное решение should_create: {should_create}")

            # Определяем приоритет на основе контекста
            priority = TaskPriority.MEDIUM
            if any(word in prompt_lower for word in ['срочно', 'важно', 'критично', 'немедленно']):
                priority = TaskPriority.HIGH
            elif any(word in prompt_lower for word in ['неважно', 'потом', 'позже']):
                priority = TaskPriority.LOW

            # Определяем категорию (используем только существующие значения enum)
            category = TaskCategory.CUSTOM  # По умолчанию пользовательская задача
            if any(word in prompt_lower for word in ['анализ', 'исследование', 'изучение', 'анализировать']):
                category = TaskCategory.ANALYSIS
            elif any(word in prompt_lower for word in ['память', 'memory', 'mem']):
                category = TaskCategory.MEMORY
            elif any(word in prompt_lower for word in ['песочница', 'sandbox', 'тест', 'тестирование']):
                category = TaskCategory.SANDBOX
            elif any(word in prompt_lower for word in ['система', 'system', 'системный']):
                category = TaskCategory.SYSTEM

            return {
                'should_create_task': should_create,
                'priority': priority,
                'category': category,
                'extracted_parameters': self._extract_task_parameters(original_message)
            }

        except Exception as e:
            self.logger.error(f"Ошибка анализа создания задачи: {e}")
            return {'should_create_task': False}

    def _extract_task_parameters(self, prompt: str) -> dict[str, Any]:
        """Извлечение параметров задачи из промпта."""
        parameters = {}

        # Извлекаем timeout
        timeout_match = re.search(r'timeout[:\s]*(\d+)', prompt, re.IGNORECASE)
        if timeout_match:
            parameters['timeout'] = int(timeout_match.group(1))
        else:
            parameters['timeout'] = 30  # Значение по умолчанию

        # Извлекаем retry_count
        retry_match = re.search(r'retry[:\s]*(\d+)', prompt, re.IGNORECASE)
        if retry_match:
            parameters['retry_count'] = int(retry_match.group(1))
        else:
            parameters['retry_count'] = 3  # Значение по умолчанию

        # Извлекаем другие параметры
        priority_match = re.search(r'priority[:\s]*(high|medium|low)', prompt, re.IGNORECASE)
        if priority_match:
            priority_str = priority_match.group(1).lower()
            if priority_str == 'high':
                parameters['priority'] = TaskPriority.HIGH
            elif priority_str == 'low':
                parameters['priority'] = TaskPriority.LOW
            else:
                parameters['priority'] = TaskPriority.MEDIUM

        return parameters

    async def _create_task_from_request(self, request: LLMRequest, analysis: dict[str, Any]) -> Task:
        """Создание задачи на основе запроса."""
        try:
            # 🔧 ИСПРАВЛЕНИЕ: Извлекаем оригинальное сообщение пользователя для имени задачи
            original_message = self._extract_original_message(request)

            # Генерируем имя задачи на основе оригинального сообщения
            task_name = self._generate_task_name(original_message)

            # Создаем задачу через TaskExecutor
            task = self.task_executor.create_task(
                name=task_name,
                description=original_message,  # Используем оригинальное сообщение и в описании
                priority=analysis['priority'],
                parameters=analysis['extracted_parameters'],
                category=analysis['category'],
                access_level=AccessLevel.EXECUTE
            )

            # Логируем создание задачи
            self.command_monitoring.log_command(
                command=f"create_task_from_llm: {task_name}",
                source="llm_integration_hub",
                user_id="system",
                parameters={
                    "task_id": task.id,
                    "priority": analysis['priority'].value,
                    "category": analysis['category'].value
                }
            )

            return task

        except Exception as e:
            self.logger.error(f"Ошибка создания задачи: {e}")
            raise

    def _extract_original_message(self, request: LLMRequest) -> str:
        """Извлечение оригинального сообщения пользователя из контекста запроса."""
        try:
            # Проверяем context.original_message (новая архитектура)
            if request.context and 'original_message' in request.context:
                return request.context['original_message']

            # Если нет контекста, ищем в самом промпте
            if "Сообщение пользователя:" in request.prompt:
                # Извлекаем между "Сообщение пользователя:" и следующим переносом строки
                import re
                match = re.search(r'Сообщение пользователя:\s*(.+)', request.prompt)
                if match:
                    # Берем до первого двойного переноса или конца строки
                    message = match.group(1).split('\n')[0].strip()
                    self.logger.info(f"🔧 ИЗВЛЕЧЕНО: '{message}' из промпта")
                    return message

            # Fallback - возвращаем весь промпт (как было раньше)
            self.logger.warning("⚠️ Не удалось извлечь оригинальное сообщение, используем полный промпт")
            return request.prompt

        except Exception as e:
            self.logger.error(f"Ошибка извлечения оригинального сообщения: {e}")
            return request.prompt

    def _generate_task_name(self, prompt: str) -> str:
        """Генерация имени задачи на основе промпта."""
        # 🔧 ОТЛАДКА: Логируем исходный промпт для генерации имени
        self.logger.info(f"🏷️ ГЕНЕРАЦИЯ ИМЕНИ ЗАДАЧИ - Исходный промпт: '{prompt}'")

        # Извлекаем ключевые слова для имени
        words = prompt.split()[:5]  # Берем первые 5 слов
        self.logger.info(f"🏷️ ГЕНЕРАЦИЯ ИМЕНИ ЗАДАЧИ - Первые 5 слов: {words}")

        name = "_".join(words).lower()
        self.logger.info(f"🏷️ ГЕНЕРАЦИЯ ИМЕНИ ЗАДАЧИ - Объединенное имя: '{name}'")

        # Очищаем от специальных символов
        import re
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '_', name)
        self.logger.info(f"🏷️ ГЕНЕРАЦИЯ ИМЕНИ ЗАДАЧИ - Очищенное имя: '{name}'")

        final_name = f"llm_task_{name}"
        self.logger.info(f"🏷️ ГЕНЕРАЦИЯ ИМЕНИ ЗАДАЧИ - Финальное имя: '{final_name}'")

        return final_name

    async def execute_task(self, task_id: str) -> dict[str, Any]:
        """Выполнение задачи через TaskExecutor."""
        try:
            # Получаем задачу
            task = self.task_executor.get_task(task_id)
            if not task:
                return {'error': f'Задача {task_id} не найдена'}

            # Выполняем следующую задачу (TaskExecutor сам выберет подходящую)
            executed_task = self.task_executor.execute_next_task()

            if executed_task and executed_task.id == task_id:
                return {
                    'success': True,
                    'task_id': task_id,
                    'status': executed_task.status.value,
                    'result': executed_task.result,
                    'error': executed_task.error
                }
            else:
                return {
                    'success': False,
                    'message': f'Задача {task_id} не была выполнена (возможно, не в очереди)'
                }

        except Exception as e:
            self.logger.error(f"Ошибка выполнения задачи {task_id}: {e}")
            return {'error': str(e)}

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Получение статуса задачи."""
        try:
            task = self.task_executor.get_task(task_id)
            if not task:
                return {'error': f'Задача {task_id} не найдена'}

            return {
                'task_id': task.id,
                'name': task.name,
                'status': task.status.value,
                'priority': task.priority.value,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                'result': task.result,
                'error': task.error
            }

        except Exception as e:
            self.logger.error(f"Ошибка получения статуса задачи {task_id}: {e}")
            return {'error': str(e)}

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Отмена задачи."""
        try:
            success = self.task_executor.cancel_task(task_id)
            return {
                'success': success,
                'task_id': task_id,
                'message': 'Задача отменена' if success else 'Не удалось отменить задачу'
            }

        except Exception as e:
            self.logger.error(f"Ошибка отмены задачи {task_id}: {e}")
            return {'error': str(e)}

    async def get_full_system_context(self) -> SystemContext:
        """Получение полного контекста системы для LLM."""
        try:
            # Получаем базовый контекст
            base_context = await self.get_system_context()

            # Добавляем информацию об активных задачах
            active_tasks = await self._get_active_tasks()
            task_context = {
                'active_tasks_count': len(active_tasks),
                'tasks_by_status': {},
                'recent_tasks': []
            }

            # Группируем задачи по статусу
            for task in active_tasks:
                status = task.status.value
                if status not in task_context['tasks_by_status']:
                    task_context['tasks_by_status'][status] = []
                task_context['tasks_by_status'][status].append({
                    'id': task.id,
                    'name': task.name,
                    'priority': task.priority.value,
                    'category': task.category.value
                })

            # Получаем историю команд
            command_history = self.command_monitoring.get_recent_commands(limit=10)

            # Получаем состояние инструментов
            tools_status = self.tools_registry.get_tools_status()

            # Получаем состояние ресурсов
            resource_status = await self._get_resource_status()

            # Получаем текущие проблемы и инсайты
            current_insights = await self._get_current_insights()

            # Формируем полный контекст
            full_context = SystemContext(
                system_info=base_context.system_info,
                memory_status=base_context.memory_status,
                available_tools=base_context.available_tools,
                active_tasks=task_context,
                command_history=command_history,
                tools_status=tools_status,
                resource_status=resource_status,
                current_insights=current_insights,
                timestamp=datetime.now()
            )

            return full_context

        except Exception as e:
            self.logger.error(f"Ошибка получения полного контекста: {e}")
            raise

    async def _get_resource_status(self) -> dict[str, Any]:
        """Получение статуса ресурсов системы."""
        try:
            import psutil

            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'active_connections': len(psutil.net_connections()),
                'load_average': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            }
        except ImportError:
            self.logger.warning("psutil не установлен, возвращаем базовый статус ресурсов")
            return {
                'cpu_percent': 'unknown',
                'memory_percent': 'unknown',
                'disk_percent': 'unknown',
                'active_connections': 'unknown',
                'load_average': 'unknown'
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения статуса ресурсов: {e}")
            return {
                'error': str(e)
            }

    async def _get_current_insights(self) -> list[dict[str, Any]]:
        """Получение текущих инсайтов и проблем."""
        try:
            insights = []

            # Анализируем активные задачи
            active_tasks = await self._get_active_tasks()
            if len(active_tasks) > 5:
                insights.append({
                    'type': 'warning',
                    'message': f'Высокая нагрузка: {len(active_tasks)} активных задач',
                    'priority': 'medium'
                })

            # Анализируем ошибки в логах
            recent_errors = self.command_monitoring.get_recent_errors(limit=5)
            if recent_errors:
                insights.append({
                    'type': 'error',
                    'message': f'Обнаружено {len(recent_errors)} ошибок в последних командах',
                    'priority': 'high',
                    'details': recent_errors
                })

            # Анализируем производительность
            resource_status = await self._get_resource_status()
            if isinstance(resource_status.get('cpu_percent'), int | float):
                if resource_status['cpu_percent'] > 80:
                    insights.append({
                        'type': 'warning',
                        'message': f'Высокая загрузка CPU: {resource_status["cpu_percent"]}%',
                        'priority': 'medium'
                    })

            if isinstance(resource_status.get('memory_percent'), int | float):
                if resource_status['memory_percent'] > 85:
                    insights.append({
                        'type': 'warning',
                        'message': f'Высокая загрузка памяти: {resource_status["memory_percent"]}%',
                        'priority': 'high'
                    })

            return insights

        except Exception as e:
            self.logger.error(f"Ошибка получения инсайтов: {e}")
            return []

    async def update_system_context(self, changes: dict[str, Any]) -> bool:
        """Обновление контекста системы на основе изменений."""
        try:
            # Обновляем контекст в ContextManager
            # Удален ContextManager, поэтому заглушка
            pass

            # Логируем обновление контекста
            self.command_monitoring.log_command(
                command="update_system_context",
                source="llm_integration_hub",
                user_id="system",
                parameters=changes
            )

            return True

        except Exception as e:
            self.logger.error(f"Ошибка обновления контекста: {e}")
            return False

    async def link_related_events(self, event_id: str, related_events: list[str]) -> bool:
        """Связывание связанных событий в контексте."""
        try:
            # Добавляем связи в контекст
            # Удален ContextManager, поэтому заглушка
            pass

            # Логируем связывание
            self.command_monitoring.log_command(
                command="link_related_events",
                source="llm_integration_hub",
                user_id="system",
                parameters={
                    "event_id": event_id,
                    "related_events": related_events
                }
            )

            return True

        except Exception as e:
            self.logger.error(f"Ошибка связывания событий: {e}")
            return False


# Глобальный экземпляр
_llm_hub: LLMIntegrationHub | None = None


async def get_llm_hub() -> LLMIntegrationHub:
    """Получение глобального экземпляра LLM Integration Hub."""
    global _llm_hub
    if _llm_hub is None:
        _llm_hub = LLMIntegrationHub()
        await _llm_hub.initialize()
    return _llm_hub


async def shutdown_llm_hub() -> None:
    """Завершение работы глобального экземпляра."""
    global _llm_hub
    if _llm_hub is not None:
        await _llm_hub.shutdown()
        _llm_hub = None
