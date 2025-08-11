"""
API routes для автономного режима
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging

from app.autonomy import AutonomousAgent, AutonomyLevel
from app.agents.mark_agent import MarkAgent
from app.learning.reap_cycle import REAPLearningCycle
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autonomy", tags=["autonomy"])

# Глобальный экземпляр автономного агента
autonomous_agent: Optional[AutonomousAgent] = None


class ProjectRequest(BaseModel):
    """Запрос на запуск проекта"""
    description: str = Field(..., description="Описание проекта для разработки")
    autonomy_level: str = Field(
        default="supervised", 
        description="Уровень автономности: manual, assisted, supervised, autonomous"
    )


class TaskRequest(BaseModel):
    """Запрос на выполнение задачи"""
    task_description: str = Field(..., description="Описание задачи")
    task_type: str = Field(
        default="general",
        description="Тип задачи: code_generation, testing, refactoring, documentation, general"
    )
    requirements: List[str] = Field(default_factory=list, description="Дополнительные требования")


class StatusResponse(BaseModel):
    """Ответ со статусом"""
    is_active: bool
    autonomy_level: str
    current_project: Optional[str]
    tasks_total: int
    tasks_completed: int
    current_task: Optional[Dict[str, Any]]


async def get_autonomous_agent() -> AutonomousAgent:
    """Получить или создать экземпляр автономного агента"""
    global autonomous_agent
    
    if autonomous_agent is None:
        # Создаем необходимые компоненты
        openai_client = AsyncOpenAI()
        mark_agent = MarkAgent(openai_client)
        memory_adapter = AdvancedMemoryAdapter()
        learning_cycle = REAPLearningCycle(memory_adapter, openai_client)
        
        # Регистрируем инструменты в агенте
        await _register_tools(mark_agent)
        
        # Создаем автономного агента
        autonomous_agent = AutonomousAgent(
            mark_agent=mark_agent,
            memory_adapter=memory_adapter,
            learning_cycle=learning_cycle
        )
        
        logger.info("✅ Автономный агент создан")
    
    return autonomous_agent


async def _register_tools(agent: MarkAgent):
    """Регистрировать инструменты в агенте"""
    # TODO: Загрузить и зарегистрировать все инструменты
    from app.agents import tools
    
    # Пример регистрации инструментов
    tool_modules = [
        "file_tools",
        "code_analysis_tools",
        "memory_tools",
        "test_tools"
    ]
    
    for module_name in tool_modules:
        try:
            # Динамически импортируем модуль
            module = __import__(f"app.agents.{module_name}", fromlist=["*"])
            
            # Регистрируем инструменты из модуля
            # TODO: Реализовать автоматическую регистрацию
            
        except Exception as e:
            logger.error(f"Ошибка загрузки модуля {module_name}: {str(e)}")


@router.post("/start_project")
async def start_project(request: ProjectRequest) -> Dict[str, Any]:
    """
    Запустить автономную разработку проекта
    
    Args:
        request: Описание проекта
        
    Returns:
        Результаты работы
    """
    try:
        agent = await get_autonomous_agent()
        
        # Устанавливаем уровень автономности
        autonomy_level = AutonomyLevel(request.autonomy_level)
        agent.set_autonomy_level(autonomy_level)
        
        # Запускаем проект
        result = await agent.start_autonomous_mode(request.description)
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Неверный уровень автономности: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка запуска проекта: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute_task")
async def execute_task(request: TaskRequest) -> Dict[str, Any]:
    """
    Выполнить отдельную задачу
    
    Args:
        request: Описание задачи
        
    Returns:
        Результат выполнения
    """
    try:
        agent = await get_autonomous_agent()
        
        # Формируем задачу
        task = {
            "name": f"Manual task: {request.task_description[:50]}",
            "description": request.task_description,
            "type": request.task_type,
            "requirements": request.requirements,
            "priority": "high"
        }
        
        # Выполняем
        result = await agent._execute_task(task)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка выполнения задачи: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """
    Получить текущий статус автономного агента
    
    Returns:
        Статус агента
    """
    try:
        agent = await get_autonomous_agent()
        status = await agent.get_status()
        
        return StatusResponse(**status)
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_autonomous_mode() -> Dict[str, str]:
    """
    Остановить автономный режим
    
    Returns:
        Сообщение об остановке
    """
    try:
        agent = await get_autonomous_agent()
        agent.stop()
        
        return {"message": "Автономный режим остановлен"}
        
    except Exception as e:
        logger.error(f"Ошибка остановки: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set_autonomy_level/{level}")
async def set_autonomy_level(level: str) -> Dict[str, str]:
    """
    Установить уровень автономности
    
    Args:
        level: Уровень автономности (manual, assisted, supervised, autonomous)
        
    Returns:
        Подтверждение изменения
    """
    try:
        agent = await get_autonomous_agent()
        autonomy_level = AutonomyLevel(level)
        agent.set_autonomy_level(autonomy_level)
        
        return {"message": f"Уровень автономности изменен на: {level}"}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Неверный уровень: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка изменения уровня: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capabilities")
async def get_capabilities() -> Dict[str, Any]:
    """
    Получить список возможностей автономного агента
    
    Returns:
        Список возможностей
    """
    return {
        "capabilities": [
            "Планирование проектов",
            "Генерация кода",
            "Рефакторинг",
            "Написание тестов",
            "Запуск тестов в песочнице",
            "Создание документации",
            "Самообучение на результатах"
        ],
        "task_types": [
            "code_generation",
            "testing",
            "refactoring",
            "documentation",
            "general"
        ],
        "autonomy_levels": [
            {
                "level": "manual",
                "description": "Полностью управляется пользователем"
            },
            {
                "level": "assisted",
                "description": "Помогает, но требует подтверждения"
            },
            {
                "level": "supervised",
                "description": "Действует самостоятельно под наблюдением"
            },
            {
                "level": "autonomous",
                "description": "Полная автономность"
            }
        ]
    }