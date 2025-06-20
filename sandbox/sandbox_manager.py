import os
import uuid
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path

@dataclass
class Sandbox:
    id: str
    path: Path
    is_active: bool = True

@dataclass
class CommandResult:
    status: str
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    success_rate: float = 0.0
    performance_metrics: Dict[str, float] = None
    error_messages: List[str] = None
    task_id: str = None
    insights: Dict[str, Any] = None

    def __post_init__(self):
        """Рассчитывает success_rate и performance_metrics"""
        if self.status == "completed":
            self.success_rate = 1.0
        elif self.status == "failed":
            self.success_rate = 0.0
        else:
            self.success_rate = 0.5

        # Инициализируем метрики производительности
        if self.performance_metrics is None:
            self.performance_metrics = {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "execution_time": self.execution_time
            }

        # Инициализируем сообщения об ошибках
        if self.error_messages is None:
            self.error_messages = []
            if self.error:
                self.error_messages.append(self.error)

        # Генерируем task_id если он не задан
        if self.task_id is None:
            self.task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # Инициализируем insights
        if self.insights is None:
            self.insights = {
                "performance": {
                    "efficiency_score": self.success_rate,
                    "resource_usage": self.performance_metrics
                },
                "error_patterns": {
                    "error_types": [],
                    "frequency": 0
                },
                "recommendations": []
            }

class SandboxManager:
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or "/tmp/sandboxes")
        self.active_sandboxes: Dict[str, Sandbox] = {}
        self._ensure_base_path()

    def _ensure_base_path(self):
        """Создает базовую директорию для песочниц"""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def create_sandbox(self) -> Sandbox:
        """Создает новую изолированную песочницу"""
        sandbox_id = str(uuid.uuid4())
        sandbox_path = self.base_path / sandbox_id
        sandbox_path.mkdir(parents=True, exist_ok=True)
        
        sandbox = Sandbox(id=sandbox_id, path=sandbox_path)
        self.active_sandboxes[sandbox_id] = sandbox
        return sandbox

    def is_sandbox_active(self, sandbox_id: str) -> bool:
        """Проверяет, активна ли песочница"""
        return sandbox_id in self.active_sandboxes and self.active_sandboxes[sandbox_id].is_active

    def execute_command(self, sandbox_id: str, command: str) -> CommandResult:
        """Выполняет команду в песочнице"""
        if not self.is_sandbox_active(sandbox_id):
            raise ValueError(f"Sandbox {sandbox_id} is not active")

        sandbox = self.active_sandboxes[sandbox_id]
        start_time = time.time()
        task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        try:
            process = subprocess.run(
                command,
                shell=True,
                cwd=str(sandbox.path),
                capture_output=True,
                text=True,
                timeout=30  # Ограничение времени выполнения
            )
            
            execution_time = time.time() - start_time
            error_messages = []
            if process.stderr:
                error_messages.append(process.stderr)
            
            return CommandResult(
                status="completed" if process.returncode == 0 else "failed",
                output=process.stdout,
                error=process.stderr,
                execution_time=execution_time,
                performance_metrics={
                    "cpu_usage": 0.0,  # TODO: Добавить реальное измерение CPU
                    "memory_usage": 0.0,  # TODO: Добавить реальное измерение памяти
                    "execution_time": execution_time
                },
                error_messages=error_messages,
                task_id=task_id,
                insights={
                    "performance": {
                        "efficiency_score": 1.0 if process.returncode == 0 else 0.0,
                        "resource_usage": {
                            "cpu_usage": 0.0,
                            "memory_usage": 0.0,
                            "execution_time": execution_time
                        }
                    },
                    "error_patterns": {
                        "error_types": [],
                        "frequency": 0
                    },
                    "recommendations": []
                }
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                status="failed",
                output="",
                error="Command execution timed out",
                execution_time=30.0,
                performance_metrics={
                    "cpu_usage": 0.0,
                    "memory_usage": 0.0,
                    "execution_time": 30.0
                },
                error_messages=["Command execution timed out"],
                task_id=task_id,
                insights={
                    "performance": {
                        "efficiency_score": 0.0,
                        "resource_usage": {
                            "cpu_usage": 0.0,
                            "memory_usage": 0.0,
                            "execution_time": 30.0
                        }
                    },
                    "error_patterns": {
                        "error_types": ["timeout"],
                        "frequency": 1
                    },
                    "recommendations": ["Увеличить таймаут выполнения команды"]
                }
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return CommandResult(
                status="failed",
                output="",
                error=str(e),
                execution_time=execution_time,
                performance_metrics={
                    "cpu_usage": 0.0,
                    "memory_usage": 0.0,
                    "execution_time": execution_time
                },
                error_messages=[str(e)],
                task_id=task_id,
                insights={
                    "performance": {
                        "efficiency_score": 0.0,
                        "resource_usage": {
                            "cpu_usage": 0.0,
                            "memory_usage": 0.0,
                            "execution_time": execution_time
                        }
                    },
                    "error_patterns": {
                        "error_types": ["exception"],
                        "frequency": 1
                    },
                    "recommendations": ["Проверить корректность команды и параметров"]
                }
            )

    def create_diff(self, sandbox_id: str) -> str:
        """Создает дифф изменений в песочнице"""
        if not self.is_sandbox_active(sandbox_id):
            raise ValueError(f"Sandbox {sandbox_id} is not active")

        sandbox = self.active_sandboxes[sandbox_id]
        try:
            process = subprocess.run(
                ["git", "diff"],
                cwd=str(sandbox.path),
                capture_output=True,
                text=True
            )
            return process.stdout
        except Exception as e:
            return f"Error creating diff: {str(e)}"

    def validate_changes(self, sandbox_id: str) -> bool:
        """Валидирует изменения в песочнице"""
        if not self.is_sandbox_active(sandbox_id):
            raise ValueError(f"Sandbox {sandbox_id} is not active")

        # TODO: Реализовать валидацию изменений
        return True

    def create_snapshot(self, sandbox_id: str) -> str:
        """Создает снапшот песочницы"""
        if not self.is_sandbox_active(sandbox_id):
            raise ValueError(f"Sandbox {sandbox_id} is not active")

        snapshot_id = str(uuid.uuid4())
        sandbox = self.active_sandboxes[sandbox_id]
        snapshot_path = self.base_path / f"{sandbox_id}_snapshot_{snapshot_id}"
        
        # Копируем содержимое песочницы
        subprocess.run(["cp", "-r", str(sandbox.path), str(snapshot_path)])
        
        return snapshot_id

    def rollback(self, sandbox_id: str, snapshot_id: str):
        """Откатывает песочницу к снапшоту"""
        if not self.is_sandbox_active(sandbox_id):
            raise ValueError(f"Sandbox {sandbox_id} is not active")

        sandbox = self.active_sandboxes[sandbox_id]
        snapshot_path = self.base_path / f"{sandbox_id}_snapshot_{snapshot_id}"
        
        if not snapshot_path.exists():
            raise ValueError(f"Snapshot {snapshot_id} not found")

        # Очищаем текущую песочницу
        subprocess.run(["rm", "-rf", str(sandbox.path)])
        # Восстанавливаем из снапшота
        subprocess.run(["cp", "-r", str(snapshot_path), str(sandbox.path)])

    def cleanup(self, sandbox_id: str):
        """Очищает песочницу"""
        if sandbox_id in self.active_sandboxes:
            sandbox = self.active_sandboxes[sandbox_id]
            subprocess.run(["rm", "-rf", str(sandbox.path)])
            del self.active_sandboxes[sandbox_id] 