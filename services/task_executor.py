from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
import logging
from pydantic import BaseModel
from langchain_api.services.security import SecurityManager, AccessLevel, TaskCategory
from langchain_api.core.feedback_system import FeedbackSystem
import uuid
from dataclasses import dataclass
import subprocess
import os
import json
from pathlib import Path
import networkx as nx
from collections import defaultdict
import psutil
from langchain_api.core.command_monitoring import CommandMonitoringSystem

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

@dataclass
class Task:
    id: str
    name: str
    description: str
    priority: TaskPriority
    status: TaskStatus
    parameters: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    category: TaskCategory = None
    access_level: AccessLevel = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = self.created_at

@dataclass
class TaskDependency:
    task_id: str
    depends_on: Set[str]  # Set of task IDs this task depends on
    required_resources: Dict[str, float]  # Resource requirements (CPU, RAM, etc.)

class TaskScheduler:
    def __init__(self):
        self.dependency_graph = nx.DiGraph()
        self.resource_limits = {
            'cpu': 4.0,  # 4 CPU cores
            'ram': 8.0,  # 8 GB RAM
            'disk': 20.0  # 20 GB disk space
        }
        self.current_resources = {
            'cpu': 0.0,
            'ram': 0.0,
            'disk': 0.0
        }
        logger.info("TaskScheduler initialized")

    def add_task_dependency(self, task_id: str, depends_on: Set[str], required_resources: Dict[str, float]) -> None:
        """Добавление задачи и её зависимостей в граф"""
        temp_graph = self.dependency_graph.copy()
        # Добавляем узел с ресурсами (или обновляем)
        temp_graph.add_node(task_id, resources=required_resources or {'cpu': 0, 'ram': 0, 'disk': 0})
        for dep_id in depends_on:
            if dep_id not in temp_graph:
                temp_graph.add_node(dep_id, resources={'cpu': 0, 'ram': 0, 'disk': 0})
            elif 'resources' not in temp_graph.nodes[dep_id]:
                temp_graph.nodes[dep_id]['resources'] = {'cpu': 0, 'ram': 0, 'disk': 0}
            temp_graph.add_edge(dep_id, task_id)
        try:
            nx.find_cycle(temp_graph)
            raise ValueError(f"Cyclic dependency detected for task {task_id}")
        except nx.NetworkXNoCycle:
            self.dependency_graph = temp_graph
            logger.info(f"Added task {task_id} with dependencies {depends_on}")

    def get_execution_order(self) -> List[str]:
        """Получение оптимального порядка выполнения задач"""
        try:
            # Проверяем наличие циклов
            if not nx.is_directed_acyclic_graph(self.dependency_graph):
                raise ValueError("Task dependencies contain cycles")

            # Получаем топологическую сортировку
            execution_order = list(nx.topological_sort(self.dependency_graph))
            
            # Оптимизируем порядок с учетом ресурсов
            optimized_order = self._optimize_resource_usage(execution_order)
            
            return optimized_order
        except Exception as e:
            logger.error(f"Error calculating execution order: {str(e)}")
            return []

    def _optimize_resource_usage(self, tasks: List[str]) -> List[str]:
        """Оптимизация порядка выполнения задач с учетом ресурсов"""
        if not tasks:
            return []
            
        # Сортируем задачи по требованию ресурсов (от меньшего к большему)
        def get_resource_score(task_id: str) -> float:
            resources = self.dependency_graph.nodes[task_id].get('resources', {'cpu': 0, 'ram': 0, 'disk': 0})
            return sum(resources.values())
            
        return sorted(tasks, key=get_resource_score)

    def _can_execute_task(self, task_id: str) -> bool:
        """Проверка возможности выполнения задачи с учетом доступных ресурсов"""
        resources = self.dependency_graph.nodes[task_id].get('resources', {'cpu': 0, 'ram': 0, 'disk': 0})
        for resource, required in resources.items():
            available = self.resource_limits.get(resource, 0) - self.current_resources.get(resource, 0)
            if required > available:
                logger.debug(f"Task {task_id} cannot execute: needs {required} {resource}, available {available}")
                return False
        return True

    def _update_resource_usage(self, task_id: str) -> None:
        resources = self.dependency_graph.nodes[task_id].get('resources', {'cpu': 0, 'ram': 0, 'disk': 0})
        for resource, amount in resources.items():
            self.current_resources.setdefault(resource, 0)
            self.current_resources[resource] += amount
        logger.debug(f"Updated resource usage after starting {task_id}: {self.current_resources}")

    def release_resources(self, task_id: str) -> None:
        resources = self.dependency_graph.nodes[task_id].get('resources', {'cpu': 0, 'ram': 0, 'disk': 0})
        for resource, amount in resources.items():
            self.current_resources.setdefault(resource, 0)
            self.current_resources[resource] = max(0, self.current_resources[resource] - amount)
        logger.debug(f"Released resources for {task_id}: {self.current_resources}")

class TaskExecutor:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.security_manager = SecurityManager()
        self.sandbox_path = Path("langchain_api/sandbox")
        self.scheduler = TaskScheduler()
        self.feedback_system = FeedbackSystem()
        self.command_monitor = CommandMonitoringSystem()
        logger.info("TaskExecutor initialized")

    def create_task(self, name: str, description: str, priority: TaskPriority,
                   parameters: Dict[str, Any], category: TaskCategory,
                   access_level: AccessLevel, depends_on: Set[str] = None,
                   required_resources: Dict[str, float] = None) -> Task:
        """Создание новой задачи с проверкой безопасности и зависимостями"""
        # Логируем команду создания задачи
        self.command_monitor.log_command(
            command=f"create_task: {name}",
            source="TaskExecutor",
            parameters={
                "description": description,
                "priority": priority.name,
                "parameters": parameters,
                "category": category.name,
                "access_level": access_level.name
            }
        )
        if not self.security_manager.validate_task(name, category, parameters, access_level):
            raise ValueError("Task validation failed")
        
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            name=name,
            description=description,
            priority=priority,
            status=TaskStatus.PENDING,
            parameters=parameters,
            category=category,
            access_level=access_level
        )
        self.tasks[task_id] = task

        # Добавляем задачу в планировщик
        if depends_on is None:
            depends_on = set()
        if required_resources is None:
            required_resources = {
                'cpu': 1.0,
                'ram': 1.0,
                'disk': 1.0
            }
        self.scheduler.add_task_dependency(task_id, depends_on, required_resources)
        
        logger.info(f"Created new task: {task_id}")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Получение задачи по ID"""
        return self.tasks.get(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus,
                          result: Any = None, error: str = None) -> Optional[Task]:
        """Обновление статуса задачи с проверкой прав"""
        task = self.get_task(task_id)
        if not task:
            return None
        
        if not self.security_manager.validate_task(
            task.name, task.category, task.parameters, task.access_level
        ):
            raise ValueError("Insufficient permissions")
        
        old_status = task.status
        task.status = status
        task.result = result
        task.error = error
        task.updated_at = datetime.now()
        logger.info(f"Updated task {task_id} status to {status}")
        # Логируем обновление статуса задачи
        self.command_monitor.log_command(
            command=f"update_task_status: {task_id}",
            source="TaskExecutor",
            parameters={
                "old_status": old_status.name,
                "new_status": status.name,
                "result": result,
                "error": error
            }
        )
        return task

    def cancel_task(self, task_id: str) -> bool:
        """Отмена задачи с проверкой прав"""
        task = self.get_task(task_id)
        if not task or task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return False
            
        if not self.security_manager.validate_task(
            task.name, task.category, task.parameters, task.access_level
        ):
            raise ValueError("Insufficient permissions")
            
        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.now()
        logger.info(f"Cancelled task {task_id}")
        return True

    def pause_task(self, task_id: str) -> bool:
        """Приостановка задачи с проверкой прав"""
        task = self.get_task(task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return False
            
        if not self.security_manager.validate_task(
            task.name, task.category, task.parameters, task.access_level
        ):
            raise ValueError("Insufficient permissions")
            
        task.status = TaskStatus.PAUSED
        task.updated_at = datetime.now()
        logger.info(f"Paused task {task_id}")
        return True

    def resume_task(self, task_id: str) -> bool:
        """Возобновление задачи с проверкой прав"""
        task = self.get_task(task_id)
        if not task or task.status != TaskStatus.PAUSED:
            return False
            
        if not self.security_manager.validate_task(
            task.name, task.category, task.parameters, task.access_level
        ):
            raise ValueError("Insufficient permissions")
            
        task.status = TaskStatus.RUNNING
        task.updated_at = datetime.now()
        logger.info(f"Resumed task {task_id}")
        return True

    def get_task_list(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """Получение списка задач с возможной фильтрацией по статусу"""
        if status:
            return [task for task in self.tasks.values() if task.status == status]
        return list(self.tasks.values())

    def get_queue_status(self) -> List[Task]:
        """Получение статуса очереди задач"""
        pending_tasks = [task for task in self.tasks.values() 
                        if task.status == TaskStatus.PENDING]
        
        # Сортировка по приоритету (HIGH > MEDIUM > LOW) и времени создания
        priority_order = {
            TaskPriority.HIGH: 3,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 1
        }
        
        return sorted(
            pending_tasks,
            key=lambda x: (priority_order[x.priority], -x.created_at.timestamp()),
            reverse=True
        )

    def execute_sandbox_command(self, task_id: str, command: str) -> Tuple[bool, str]:
        """Выполнение команды в песочнице"""
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found"
            
        if not self.security_manager.validate_task(
            task.name, task.category, task.parameters, task.access_level
        ):
            return False, "Insufficient permissions"

        try:
            # Создаем снапшот перед выполнением команды
            snapshot_path = self._create_sandbox_snapshot(task_id)
            
            # Выполняем команду в контейнере app
            result = subprocess.run(
                ["docker", "exec", "app", "bash", "-c", f"cd /app/langchain_api && {command}"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # Восстанавливаем снапшот в случае ошибки
                self._restore_sandbox_snapshot(snapshot_path)
                return False, f"Ошибка выполнения команды:\n\n{result.stderr or result.stdout}"
                
            return True, "Команда выполнена успешно:\n\n" + result.stdout
            
        except Exception as e:
            logger.error(f"Error executing sandbox command: {str(e)}")
            return False, f"Ошибка выполнения команды:\n\n{str(e)}"

    def create_sandbox_diff(self, task_id: str) -> Tuple[bool, str]:
        """Создание диффа изменений в песочнице"""
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found"
            
        try:
            result = subprocess.run(
                ["docker", "exec", "app", "bash", "-c", "cd /app/langchain_api && git diff"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False, f"Ошибка получения изменений:\n\n{result.stderr or result.stdout}"
                
            return True, "Дифф успешно создан:\n\n" + result.stdout
            
        except Exception as e:
            logger.error(f"Error creating sandbox diff: {str(e)}")
            return False, f"Ошибка получения изменений:\n\n{str(e)}"

    def apply_sandbox_changes(self, task_id: str) -> Tuple[bool, str]:
        """Применение изменений в песочнице"""
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found"
            
        try:
            # Создаем снапшот перед применением изменений
            snapshot_path = self._create_sandbox_snapshot(task_id)
            
            # Применяем изменения
            result = subprocess.run(
                ["docker", "exec", "app", "bash", "-c", "cd /app/langchain_api && git add . && git commit -m 'Applied sandbox changes'"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # Восстанавливаем снапшот в случае ошибки
                self._restore_sandbox_snapshot(snapshot_path)
                return False, f"Ошибка применения изменений:\n\n{result.stderr or result.stdout}"
                
            return True, "Изменения успешно применены"
            
        except Exception as e:
            logger.error(f"Error applying sandbox changes: {str(e)}")
            return False, f"Ошибка применения изменений:\n\n{str(e)}"

    def _create_sandbox_snapshot(self, task_id: str) -> str:
        """Создание снапшота песочницы"""
        snapshot_dir = self.sandbox_path / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{task_id}_snapshot.tar.gz"
        
        try:
            subprocess.run(
                ["docker", "exec", "app", "bash", "-c", f"cd /app/langchain_api && git stash push -m 'Snapshot {task_id}'"],
                check=True
            )
            return str(snapshot_path)
        except Exception as e:
            logger.error(f"Error creating sandbox snapshot: {str(e)}")
            raise

    def _restore_sandbox_snapshot(self, snapshot_path: str) -> bool:
        """Восстановление песочницы из снапшота"""
        try:
            result = subprocess.run([
                "docker", "exec", "app", "bash", "-c",
                f"cd /app/langchain_api && tar -xzf {snapshot_path} -C ."
            ], capture_output=True, text=True)
            if result.returncode != 0:
                return False
            return True
        except Exception as e:
            logger.error(f"Error restoring sandbox snapshot: {str(e)}")
            return False

    def validate_sandbox_changes(self, task_id: str) -> Tuple[bool, str]:
        """Валидация изменений в песочнице"""
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found"
            
        try:
            # Проверяем наличие изменений
            diff_result = subprocess.run(
                ["docker", "exec", "app", "bash", "-c", "cd /app/langchain_api && git diff"],
                capture_output=True,
                text=True
            )
            
            if not diff_result.stdout.strip():
                return False, "Нет изменений для валидации"
                
            # Запускаем тесты
            test_result = subprocess.run(
                ["docker", "exec", "app", "bash", "-c", "cd /app/langchain_api && python -m pytest"],
                capture_output=True,
                text=True
            )
            
            if test_result.returncode != 0:
                return False, f"Тесты не прошли: {test_result.stderr or test_result.stdout}"
                
            return True, "Изменения прошли валидацию"
            
        except Exception as e:
            logger.error(f"Error validating sandbox changes: {str(e)}")
            return False, f"Ошибка валидации изменений:\n\n{str(e)}"

    def get_optimized_execution_order(self) -> List[Task]:
        """Получение оптимизированного порядка выполнения задач"""
        task_ids = self.scheduler.get_execution_order()
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]

    def execute_next_task(self) -> Optional[Task]:
        """Выполнение следующей задачи из очереди"""
        # Получаем оптимизированный порядок выполнения
        execution_order = self.scheduler.get_execution_order()
        
        for task_id in execution_order:
            task = self.get_task(task_id)
            if not task or task.status != TaskStatus.PENDING:
                continue
                
            # Проверяем возможность выполнения
            if not self.scheduler._can_execute_task(task_id):
                continue
                
            try:
                # Обновляем статус на RUNNING
                task.status = TaskStatus.RUNNING
                task.updated_at = datetime.now()
                
                # Обновляем использование ресурсов
                self.scheduler._update_resource_usage(task_id)
                
                # Выполняем задачу
                result = self._execute_task(task)
                
                # Обновляем статус и результат
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.updated_at = datetime.now()
                
                # Записываем метрики
                if self.feedback_system:
                    self.feedback_system.record_task_execution(
                        task.id,
                        {
                            'execution_time': (task.updated_at - task.created_at).total_seconds(),
                            'success': True,
                            'cpu_usage': psutil.cpu_percent(),
                            'memory_usage': psutil.virtual_memory().percent
                        }
                    )
                
                # Освобождаем ресурсы
                self.scheduler.release_resources(task_id)
                
                # Сохраняем копию задачи для возврата
                task_copy = Task(
                    id=task.id,
                    name=task.name,
                    description=task.description,
                    priority=task.priority,
                    status=task.status,
                    parameters=task.parameters.copy(),
                    result=task.result,
                    error=task.error,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    category=task.category,
                    access_level=task.access_level
                )
                
                # Сбрасываем статус для возможности повторного выполнения
                task.status = TaskStatus.PENDING
                
                return task_copy
                
            except Exception as e:
                logger.error(f"Error executing task {task_id}: {str(e)}")
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.updated_at = datetime.now()
                
                # Записываем метрики ошибки
                if self.feedback_system:
                    self.feedback_system.record_task_execution(
                        task.id,
                        {
                            'execution_time': (task.updated_at - task.created_at).total_seconds(),
                            'success': False,
                            'error': str(e),
                            'cpu_usage': psutil.cpu_percent(),
                            'memory_usage': psutil.virtual_memory().percent
                        }
                    )
                
                # Освобождаем ресурсы
                self.scheduler.release_resources(task_id)
                
                # Сохраняем копию задачи для возврата
                task_copy = Task(
                    id=task.id,
                    name=task.name,
                    description=task.description,
                    priority=task.priority,
                    status=task.status,
                    parameters=task.parameters.copy(),
                    result=task.result,
                    error=task.error,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    category=task.category,
                    access_level=task.access_level
                )
                
                # Сбрасываем статус для возможности повторного выполнения
                task.status = TaskStatus.PENDING
                
                return task_copy
                
        return None

    def get_task_optimization_suggestions(self, task_id: str) -> List[Dict[str, Any]]:
        """Получение предложений по оптимизации задачи"""
        return self.feedback_system.get_optimization_suggestions(task_id)

    def get_task_performance_analysis(self, task_id: str) -> Dict[str, Any]:
        """Получение анализа производительности задачи"""
        return self.feedback_system.analyze_task_performance(task_id)

    def complete_task(self, task_id: str, result: Any = None) -> Optional[Task]:
        """Завершение задачи и освобождение ресурсов"""
        task = self.update_task_status(task_id, TaskStatus.COMPLETED, result=result)
        if task:
            self.scheduler.release_resources(task_id)
        return task

    def fail_task(self, task_id: str, error: str) -> Optional[Task]:
        """Отметка задачи как неудачной и освобождение ресурсов"""
        task = self.update_task_status(task_id, TaskStatus.FAILED, error=error)
        if task:
            self.scheduler.release_resources(task_id)
        return task

    def _execute_task(self, task: Task) -> Any:
        """Выполнение задачи в зависимости от её категории"""
        if task.category == TaskCategory.SYSTEM:
            if 'command' not in task.parameters:
                raise ValueError("System task must have 'command' parameter")
            result = subprocess.run(
                ["docker", "exec", "app", "bash", "-c", task.parameters['command']],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Command failed: {result.stderr}")
            return result.stdout
            
        elif task.category == TaskCategory.MEMORY:
            if 'operation' not in task.parameters:
                raise ValueError("Memory task must have 'operation' parameter")
            # Здесь будет логика работы с памятью
            return f"Memory operation {task.parameters['operation']} completed"
            
        elif task.category == TaskCategory.SANDBOX:
            if 'code' not in task.parameters:
                raise ValueError("Sandbox task must have 'code' parameter")
            # Здесь будет логика выполнения кода в песочнице
            return f"Sandbox code execution completed"
            
        elif task.category == TaskCategory.ANALYSIS:
            # Здесь будет логика аналитических задач
            return f"Analysis task completed"
            
        elif task.category == TaskCategory.CUSTOM:
            # Для пользовательских задач просто возвращаем параметры
            return task.parameters
            
        else:
            raise ValueError(f"Unknown task category: {task.category}") 