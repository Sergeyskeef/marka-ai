from typing import Dict, List, Optional
from .self_analysis import SandboxSelfAnalysis
from .task_manager import SandboxTask, SandboxTaskManager, TaskStatus, TaskPriority

class SandboxIntegrator:
    def __init__(self, sandbox_path: str = "sandbox"):
        self.self_analysis = SandboxSelfAnalysis(sandbox_path)
        self.task_manager = SandboxTaskManager(sandbox_path)
        
    def create_experiment_task(self, 
                             title: str,
                             description: str,
                             priority: TaskPriority = TaskPriority.MEDIUM,
                             dependencies: List[str] = None) -> str:
        """Создание задачи для эксперимента"""
        task = SandboxTask(
            title=title,
            description=description,
            priority=priority,
            dependencies=dependencies
        )
        return self.task_manager.create_task(task)
        
    def run_experiment(self, task_id: str, experiment_data: Dict) -> Dict:
        """Запуск эксперимента и сохранение результатов"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
            
        # Сохраняем данные эксперимента
        experiment_filename = self.self_analysis.save_experiment(experiment_data)
        
        # Анализируем результаты
        analysis = self.self_analysis.analyze_experiment(experiment_filename)
        
        # Сохраняем рефлексию
        reflection_data = {
            "task_id": task_id,
            "experiment_filename": experiment_filename,
            "analysis": analysis,
            "timestamp": experiment_data.get("timestamp")
        }
        reflection_filename = self.self_analysis.save_reflection(reflection_data)
        
        # Обновляем задачу
        task.status = TaskStatus.COMPLETED
        task.results = {
            "experiment_filename": experiment_filename,
            "reflection_filename": reflection_filename,
            "analysis": analysis
        }
        self.task_manager.update_task(task)
        
        return analysis
        
    def get_experiment_history(self, task_id: str) -> List[Dict]:
        """Получение истории экспериментов для задачи"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
            
        history = []
        if task.results:
            history.append({
                "experiment": task.results.get("experiment_filename"),
                "reflection": task.results.get("reflection_filename"),
                "analysis": task.results.get("analysis")
            })
            
        return history
        
    def analyze_task_progress(self, task_id: str) -> Dict:
        """Анализ прогресса выполнения задачи"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
            
        history = self.get_experiment_history(task_id)
        
        analysis = {
            "task_status": task.status.value,
            "experiments_count": len(history),
            "success_rate": sum(h["analysis"]["success_rate"] for h in history) / len(history) if history else 0,
            "improvements": [imp for h in history for imp in h["analysis"]["improvements"]],
            "learnings": [learn for h in history for learn in h["analysis"]["learnings"]]
        }
        
        return analysis
        
    def get_next_experiment(self) -> Optional[Dict]:
        """Получение следующего эксперимента для выполнения"""
        next_task = self.task_manager.get_next_task()
        if not next_task:
            return None
            
        return {
            "task_id": next_task.id,
            "title": next_task.title,
            "description": next_task.description,
            "priority": next_task.priority.value,
            "dependencies": next_task.dependencies
        } 