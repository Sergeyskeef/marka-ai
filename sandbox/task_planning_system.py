"""
Task Planning System - полноценная система планирования задач
"""

import uuid
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# Импортируем LLM клиент
from utils.openai_proxy_client import chat_model

# Импортируем адаптер памяти
from core.memory.graphiti_adapter import graphiti_adapter

# Импортируем Event Bus
from core.event_bus import event_bus, EventTypes

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    id: str
    description: str
    tool_required: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    estimated_time_minutes: int = 30
    actual_time_minutes: Optional[int] = None
    status: TaskStatus = TaskStatus.DRAFT
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует подзадачу в словарь"""
        return {
            "id": self.id,
            "description": self.description,
            "tool_required": self.tool_required,
            "dependencies": self.dependencies,
            "estimated_time_minutes": self.estimated_time_minutes,
            "actual_time_minutes": self.actual_time_minutes,
            "status": self.status.value,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    

@dataclass
class Plan:
    id: str
    goal: str
    subtasks: List[SubTask]
    status: TaskStatus = TaskStatus.DRAFT
    confidence_score: float = 0.8
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def estimated_duration(self) -> timedelta:
        """Общая оценка времени выполнения"""
        total_minutes = sum(t.estimated_time_minutes for t in self.subtasks)
        return timedelta(minutes=total_minutes)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует план в словарь"""
        return {
            "id": self.id,
            "goal": self.goal,
            "subtasks": [t.to_dict() for t in self.subtasks],
            "status": self.status.value,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "user_id": self.user_id,
            "metadata": self.metadata,
            "estimated_duration_minutes": self.estimated_duration.total_seconds() / 60
        }


class TaskPlanner:
    """Планировщик задач с использованием LLM"""
    
    def __init__(self):
        self.plans: Dict[str, Plan] = {}
        self.llm = chat_model
        self.memory_adapter = graphiti_adapter
        logger.info("✅ TaskPlanner инициализирован")
        
    async def create_plan(self, goal: str, context: Dict[str, Any] = None) -> Plan:
        """Создает план для достижения цели"""
        logger.info(f"📋 Создание плана для: {goal[:100]}...")
        
        # Подготовка промпта для LLM
        analysis_prompt = f"""
        Ты - эксперт по планированию задач. Создай детальный пошаговый план для достижения следующей цели.
        
        Цель: {goal}
        
        Контекст: {json.dumps(context or {}, ensure_ascii=False)}
        
        Создай структурированный JSON план со следующими полями:
        {{
            "subtasks": [
                {{
                    "description": "Описание подзадачи",
                    "estimated_time": число_минут,
                    "dependencies": [индексы зависимых подзадач],
                    "tool": "название_инструмента или null"
                }}
            ]
        }}
        
        Требования:
        1. Разбей задачу на логические шаги
        2. Оцени время реалистично (в минутах)
        3. Укажи зависимости между задачами (индексы начинаются с 0)
        4. Для технических задач укажи нужные инструменты: write_file, execute_code, search, analyze_code
        5. Каждая подзадача должна быть конкретной и выполнимой
        
        Пример для "Написать скрипт парсинга сайта":
        {{
            "subtasks": [
                {{
                    "description": "Изучить структуру целевого сайта",
                    "estimated_time": 30,
                    "dependencies": [],
                    "tool": "search"
                }},
                {{
                    "description": "Написать код парсера с использованием BeautifulSoup",
                    "estimated_time": 60,
                    "dependencies": [0],
                    "tool": "write_file"
                }},
                {{
                    "description": "Протестировать парсер на примере страницы",
                    "estimated_time": 30,
                    "dependencies": [1],
                    "tool": "execute_code"
                }}
            ]
        }}
        
        Ответь ТОЛЬКО валидным JSON без дополнительного текста.
        """
        
        try:
            # Получаем ответ от LLM
            response = await self.llm.ainvoke(analysis_prompt)
            plan_data = self._parse_llm_response(response.content)
            
            # Создаем подзадачи
            subtasks = []
            for i, task_data in enumerate(plan_data.get("subtasks", [])):
                subtask = SubTask(
                    id=str(uuid.uuid4()),
                    description=task_data.get("description", f"Подзадача {i+1}"),
                    tool_required=task_data.get("tool"),
                    dependencies=[str(d) for d in task_data.get("dependencies", [])],
                    estimated_time_minutes=task_data.get("estimated_time", 30)
                )
                subtasks.append(subtask)
            
            # Создаем план
            plan = Plan(
                id=str(uuid.uuid4()),
                goal=goal,
                subtasks=subtasks,
                user_id=context.get("user_id") if context else None,
                metadata=context or {},
                status=TaskStatus.PLANNED
            )
            
            # Сохраняем в памяти
            await self._save_to_memory(plan)
            
            # Сохраняем в локальном кеше
            self.plans[plan.id] = plan
            
            # Публикуем событие о создании плана
            await event_bus.publish(
                EventTypes.PLAN_CREATED,
                {
                    "plan_id": plan.id,
                    "goal": plan.goal,
                    "subtasks_count": len(plan.subtasks),
                    "user_id": plan.user_id,
                    "confidence_score": plan.confidence_score
                },
                source="TaskPlanner"
            )
            
            logger.info(f"✅ План создан: {plan.id}, подзадач: {len(subtasks)}")
            return plan
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания плана: {e}")
            # Возвращаем простой план по умолчанию
            return self._create_default_plan(goal, context)
    
    async def execute_plan(self, plan_id: str) -> Dict[str, Any]:
        """Выполняет план (пока заглушка для будущей интеграции)"""
        plan = self.plans.get(plan_id)
        if not plan:
            return {"success": False, "error": "План не найден"}
            
        plan.status = TaskStatus.IN_PROGRESS
        plan.updated_at = datetime.now()
        
        # В будущем здесь будет интеграция с TaskExecutor
        # Пока просто помечаем как выполненный
        completed_tasks = 0
        
        for subtask in plan.subtasks:
            subtask.status = TaskStatus.COMPLETED
            subtask.updated_at = datetime.now()
            subtask.actual_time_minutes = subtask.estimated_time_minutes
            completed_tasks += 1
        
        plan.status = TaskStatus.COMPLETED
        plan.updated_at = datetime.now()
        
        # Обновляем в памяти
        await self._save_to_memory(plan)
        
        # Публикуем событие о выполнении плана
        await event_bus.publish(
            EventTypes.PLAN_EXECUTED,
            {
                "plan_id": plan_id,
                "status": plan.status.value,
                "completed_tasks": completed_tasks,
                "total_tasks": len(plan.subtasks)
            },
            source="TaskPlanner"
        )
        
        return {
            "success": True,
            "plan_id": plan_id,
            "completed_tasks": completed_tasks,
            "failed_tasks": 0,
            "total_tasks": len(plan.subtasks)
        }
    
    def get_plan_status(self, plan_id: str) -> Dict[str, Any]:
        """Возвращает статус плана"""
        plan = self.plans.get(plan_id)
        if not plan:
            return {"error": "План не найден"}
            
        completed = sum(1 for t in plan.subtasks if t.status == TaskStatus.COMPLETED)
        in_progress = sum(1 for t in plan.subtasks if t.status == TaskStatus.IN_PROGRESS)
        
        return {
            "plan_id": plan_id,
            "goal": plan.goal,
            "status": plan.status.value,
            "progress": {
                "completed": completed,
                "in_progress": in_progress,
                "total": len(plan.subtasks),
                "percentage": int((completed / len(plan.subtasks) * 100)) if plan.subtasks else 0
            },
            "estimated_time_remaining": self._calculate_remaining_time(plan),
            "subtasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "status": t.status.value,
                    "estimated_time": t.estimated_time_minutes,
                    "tool": t.tool_required
                }
                for t in plan.subtasks
            ]
        }
    
    async def get_all_plans(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получает все планы (опционально для конкретного пользователя)"""
        plans = []
        for plan in self.plans.values():
            if user_id is None or plan.user_id == user_id:
                plans.append({
                    "id": plan.id,
                    "goal": plan.goal,
                    "status": plan.status.value,
                    "created_at": plan.created_at.isoformat(),
                    "subtasks_count": len(plan.subtasks)
                })
        return sorted(plans, key=lambda x: x["created_at"], reverse=True)
    
    # Вспомогательные методы
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Парсит ответ LLM и извлекает JSON"""
        try:
            # Пытаемся найти JSON в ответе
            start = response.find("{")
            end = response.rfind("}") + 1
            
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"Ошибка парсинга ответа LLM: {e}")
            
        # Возвращаем пустой план если парсинг не удался
        return {"subtasks": []}
    
    def _create_default_plan(self, goal: str, context: Dict[str, Any]) -> Plan:
        """Создает план по умолчанию при ошибке"""
        return Plan(
            id=str(uuid.uuid4()),
            goal=goal,
            subtasks=[
                SubTask(
                    id=str(uuid.uuid4()),
                    description=f"Выполнить: {goal}",
                    estimated_time_minutes=60
                )
            ],
            user_id=context.get("user_id") if context else None,
            metadata=context or {},
            confidence_score=0.5  # Низкая уверенность для плана по умолчанию
        )
    
    async def _save_to_memory(self, plan: Plan):
        """Сохраняет план в память через GraphitiAdapter"""
        try:
            # Подготавливаем данные для сохранения
            memory_content = f"План: {plan.goal}\n"
            memory_content += f"Статус: {plan.status.value}\n"
            memory_content += f"Подзадач: {len(plan.subtasks)}\n\n"
            
            for i, task in enumerate(plan.subtasks, 1):
                memory_content += f"{i}. {task.description} ({task.status.value})\n"
            
            # Сохраняем через GraphitiAdapter
            await self.memory_adapter.add_episode(
                content=memory_content,
                metadata={
                    "type": "plan",
                    "plan_id": plan.id,
                    "goal": plan.goal,
                    "status": plan.status.value,
                    "subtasks_count": len(plan.subtasks),
                    "user_id": plan.user_id,
                    "created_at": plan.created_at.isoformat()
                }
            )
            
            logger.info(f"💾 План сохранен в память: {plan.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения плана в память: {e}")
    
    def _calculate_remaining_time(self, plan: Plan) -> int:
        """Вычисляет оставшееся время в минутах"""
        remaining = 0
        for task in plan.subtasks:
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                remaining += task.estimated_time_minutes
        return remaining


# Создаем глобальный экземпляр планировщика
task_planner = TaskPlanner()


# Для обратной совместимости оставляем старые функции
def create_task_plan(description: str) -> dict[str, Any]:
    """Legacy функция - использует новый TaskPlanner"""
    import asyncio
    plan = asyncio.run(task_planner.create_plan(description))
    return {
        "plan_id": plan.id,
        "description": plan.goal,
        "steps": [t.description for t in plan.subtasks],
        "estimated_time": str(plan.estimated_duration)
    }


def execute_task_plan(plan_id: str) -> dict[str, Any]:
    """Legacy функция"""
    import asyncio
    return asyncio.run(task_planner.execute_plan(plan_id))


def get_task_plan_status(plan_id: str) -> dict[str, Any]:
    """Legacy функция"""
    return task_planner.get_plan_status(plan_id)
