"""
Планировщик задач для автономного агента
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from app.agents.mark_agent import MarkAgent
from app.memory.advanced_memory_adapter import AdvancedMemoryAdapter

logger = logging.getLogger(__name__)


class TaskPlanner:
    """
    Планировщик задач
    
    Способности:
    - Декомпозиция сложных проектов на задачи
    - Определение зависимостей между задачами
    - Оценка времени выполнения
    - Приоритизация задач
    """
    
    def __init__(self, mark_agent: MarkAgent, memory_adapter: AdvancedMemoryAdapter):
        """
        Инициализация планировщика
        
        Args:
            mark_agent: Агент для генерации планов
            memory_adapter: Адаптер памяти для сохранения планов
        """
        self.agent = mark_agent
        self.memory = memory_adapter
        logger.info("📋 TaskPlanner инициализирован")
    
    async def create_project_plan(self, project_description: str) -> Dict[str, Any]:
        """
        Создать план проекта
        
        Args:
            project_description: Описание проекта
            
        Returns:
            План проекта с задачами
        """
        try:
            logger.info(f"🎯 Создание плана для проекта: {project_description[:100]}...")
            
            # Ищем похожие проекты в памяти
            similar_projects = await self._find_similar_projects(project_description)
            
            # Формируем промпт для планирования
            planning_prompt = self._create_planning_prompt(project_description, similar_projects)
            
            # Генерируем план через агента
            response = await self.agent.generate_response(
                planning_prompt,
                use_tools=False,
                temperature=0.3  # Низкая температура для структурированного вывода
            )
            
            # Парсим план из ответа
            plan = self._parse_plan_from_response(response)
            
            # Обогащаем план дополнительной информацией
            plan = await self._enrich_plan(plan, project_description)
            
            # Сохраняем план в память
            await self._save_plan_to_memory(plan, project_description)
            
            return plan
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании плана: {str(e)}")
            return {
                "error": str(e),
                "tasks": []
            }
    
    def _create_planning_prompt(self, project_description: str, similar_projects: List[Dict]) -> str:
        """Создать промпт для планирования"""
        
        similar_info = ""
        if similar_projects:
            similar_info = "\n\nПохожие проекты из памяти:\n"
            for proj in similar_projects[:3]:
                similar_info += f"- {proj.get('description', 'N/A')}: {proj.get('task_count', 0)} задач\n"
        
        return f"""
        Создай детальный план разработки для следующего проекта:
        
        {project_description}
        {similar_info}
        
        Требования к плану:
        1. Разбей проект на конкретные, выполнимые задачи
        2. Укажи тип каждой задачи (code_generation, testing, refactoring, documentation, general)
        3. Определи зависимости между задачами
        4. Оцени время выполнения каждой задачи в часах
        5. Установи приоритеты (high, medium, low)
        
        Ответ должен быть в формате JSON:
        {{
            "project_name": "Название проекта",
            "description": "Краткое описание",
            "estimated_hours": число,
            "tasks": [
                {{
                    "id": "task_1",
                    "name": "Название задачи",
                    "description": "Описание задачи",
                    "type": "code_generation|testing|refactoring|documentation|general",
                    "priority": "high|medium|low",
                    "estimated_hours": число,
                    "dependencies": ["task_id"],
                    "requirements": ["требование1", "требование2"],
                    "output_file": "путь/к/файлу" // для code_generation
                }}
            ]
        }}
        """
    
    def _parse_plan_from_response(self, response: str) -> Dict[str, Any]:
        """Парсить план из ответа агента"""
        try:
            # Пытаемся найти JSON в ответе
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                plan = json.loads(json_str)
                
                # Валидация структуры
                if "tasks" not in plan:
                    plan["tasks"] = []
                
                # Добавляем ID если их нет
                for i, task in enumerate(plan["tasks"]):
                    if "id" not in task:
                        task["id"] = f"task_{i+1}"
                
                return plan
            else:
                # Если JSON не найден, создаем базовый план
                return {
                    "project_name": "Неизвестный проект",
                    "description": "План не удалось распарсить",
                    "tasks": [],
                    "error": "JSON not found in response"
                }
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {str(e)}")
            return {
                "project_name": "Ошибка парсинга",
                "tasks": [],
                "error": str(e)
            }
    
    async def _enrich_plan(self, plan: Dict[str, Any], project_description: str) -> Dict[str, Any]:
        """Обогатить план дополнительной информацией"""
        
        # Добавляем метаданные
        plan["created_at"] = datetime.now().isoformat()
        plan["original_description"] = project_description
        
        # Вычисляем общее время
        if "tasks" in plan:
            total_hours = sum(task.get("estimated_hours", 0) for task in plan["tasks"])
            plan["estimated_hours"] = total_hours
            
            # Определяем критический путь
            plan["critical_path"] = self._calculate_critical_path(plan["tasks"])
        
        return plan
    
    def _calculate_critical_path(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """Вычислить критический путь проекта"""
        # Упрощенная версия - просто задачи с высоким приоритетом
        critical_tasks = [
            task["id"] for task in tasks 
            if task.get("priority") == "high"
        ]
        return critical_tasks
    
    async def _find_similar_projects(self, project_description: str) -> List[Dict[str, Any]]:
        """Найти похожие проекты в памяти"""
        try:
            # Ищем похожие планы в памяти
            similar = await self.memory.search_memories(
                query=f"project plan {project_description}",
                memory_type="skill",
                limit=5
            )
            
            return [mem.get("metadata", {}) for mem in similar if mem.get("metadata")]
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска похожих проектов: {str(e)}")
            return []
    
    async def _save_plan_to_memory(self, plan: Dict[str, Any], project_description: str):
        """Сохранить план в память"""
        try:
            await self.memory.save_project_plan(
                plan_name=plan.get("project_name", "unknown"),
                plan=plan,
                project_description=project_description,
                metadata={
                    "project_name": plan.get("project_name"),
                    "description": project_description,
                    "task_count": len(plan.get("tasks", [])),
                    "estimated_hours": plan.get("estimated_hours", 0),
                    "created_at": plan.get("created_at"),
                    "source": "task_planner",
                }
            )
            logger.info(f"✅ План сохранен в память")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения плана: {str(e)}")
    
    async def update_task_status(self, plan_id: str, task_id: str, status: str):
        """
        Обновить статус задачи в плане
        
        Args:
            plan_id: ID плана
            task_id: ID задачи
            status: Новый статус (pending, in_progress, completed, failed)
        """
        # TODO: Реализовать обновление статуса в памяти
        logger.info(f"📝 Обновление статуса задачи {task_id} -> {status}")
    
    async def get_next_tasks(self, plan: Dict[str, Any], completed_tasks: List[str]) -> List[Dict[str, Any]]:
        """
        Получить следующие задачи для выполнения
        
        Args:
            plan: План проекта
            completed_tasks: Список выполненных задач
            
        Returns:
            Список задач готовых к выполнению
        """
        available_tasks = []
        
        for task in plan.get("tasks", []):
            # Пропускаем уже выполненные
            if task["id"] in completed_tasks:
                continue
            
            # Проверяем зависимости
            dependencies = task.get("dependencies", [])
            if all(dep in completed_tasks for dep in dependencies):
                available_tasks.append(task)
        
        # Сортируем по приоритету
        priority_order = {"high": 0, "medium": 1, "low": 2}
        available_tasks.sort(key=lambda t: priority_order.get(t.get("priority", "medium"), 1))
        
        return available_tasks