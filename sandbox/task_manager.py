from typing import Dict, List, Optional
import json
from datetime import datetime
from pathlib import Path
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class SandboxTask:
    def __init__(self, 
                 title: str,
                 description: str,
                 priority: TaskPriority = TaskPriority.MEDIUM,
                 dependencies: List[str] = None):
        self.id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.title = title
        self.description = description
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.dependencies = dependencies or []
        self.created_at = datetime.now()
        self.updated_at = self.created_at
        self.completed_at = None
        self.results = {}
        
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "results": self.results
        }
        
    @classmethod
    def from_dict(cls, data: Dict) -> 'SandboxTask':
        task = cls(
            title=data["title"],
            description=data["description"],
            priority=TaskPriority(data["priority"]),
            dependencies=data["dependencies"]
        )
        task.id = data["id"]
        task.status = TaskStatus(data["status"])
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.updated_at = datetime.fromisoformat(data["updated_at"])
        if data["completed_at"]:
            task.completed_at = datetime.fromisoformat(data["completed_at"])
        task.results = data["results"]
        return task

class SandboxTaskManager:
    def __init__(self, sandbox_path: str = "sandbox"):
        self.sandbox_path = Path(sandbox_path)
        self.tasks_path = self.sandbox_path / "tasks"
        self._setup_directories()
        
    def _setup_directories(self):
        """Создание необходимых директорий для работы"""
        self.tasks_path.mkdir(parents=True, exist_ok=True)
        
    def create_task(self, task: SandboxTask) -> str:
        """Создание новой задачи"""
        filepath = self.tasks_path / f"task_{task.id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
        return task.id
        
    def get_task(self, task_id: str) -> Optional[SandboxTask]:
        """Получение задачи по ID"""
        filepath = self.tasks_path / f"task_{task_id}.json"
        if not filepath.exists():
            return None
            
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return SandboxTask.from_dict(data)
            
    def update_task(self, task: SandboxTask) -> bool:
        """Обновление задачи"""
        filepath = self.tasks_path / f"task_{task.id}.json"
        if not filepath.exists():
            return False
            
        task.updated_at = datetime.now()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
        return True
        
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[SandboxTask]:
        """Получение списка задач с возможностью фильтрации по статусу"""
        tasks = []
        for filepath in self.tasks_path.glob("task_*.json"):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                task = SandboxTask.from_dict(data)
                if status is None or task.status == status:
                    tasks.append(task)
        return tasks
        
    def get_next_task(self) -> Optional[SandboxTask]:
        """Получение следующей задачи для выполнения"""
        pending_tasks = self.list_tasks(TaskStatus.PENDING)
        if not pending_tasks:
            return None
            
        # Сортируем по приоритету (по убыванию)
        pending_tasks.sort(key=lambda x: x.priority.value, reverse=True)
        
        # Проверяем зависимости
        for task in pending_tasks:
            if not task.dependencies:
                return task
                
            # Проверяем, все ли зависимости выполнены
            dependencies_completed = True
            for dep_id in task.dependencies:
                dep_task = self.get_task(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    dependencies_completed = False
                    break
                    
            if dependencies_completed:
                return task
                
        return None 