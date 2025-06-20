"""
Модуль для анализа выполнения задач и генерации рекомендаций по улучшению.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class TaskMetrics:
    """Метрики выполнения задачи."""
    task_id: str
    task_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    execution_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует метрики в словарь."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "start_time": str(self.start_time),
            "end_time": str(self.end_time) if self.end_time else None,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time": self.execution_time
        }

@dataclass
class TaskAnalysis:
    """Результаты анализа задачи."""
    task_id: str
    task_type: str
    performance_score: float
    resource_efficiency: float
    recommendations: List[str]
    patterns: List[str]

class DateTimeEncoder(json.JSONEncoder):
    """Кастомный JSON энкодер для datetime."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def convert_all_dt_to_str(obj):
    if isinstance(obj, dict):
        return {k: convert_all_dt_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_all_dt_to_str(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

class TaskAnalyzer:
    """Анализатор выполнения задач."""
    
    def __init__(self):
        self.metrics_history: List[TaskMetrics] = []
        self.analysis_history: List[TaskAnalysis] = []
        
    def add_metrics(self, metrics: TaskMetrics) -> None:
        """Добавляет метрики выполнения задачи."""
        self.metrics_history.append(metrics)
        logger.info(f"Added metrics for task {metrics.task_id}")
        
    def analyze_task(self, task_id: str) -> TaskAnalysis:
        """Анализирует выполнение конкретной задачи."""
        task_metrics = next((m for m in self.metrics_history if m.task_id == task_id), None)
        if not task_metrics:
            raise ValueError(f"Metrics not found for task {task_id}")
            
        # Анализ производительности
        performance_score = self._calculate_performance_score(task_metrics)
        
        # Анализ эффективности использования ресурсов
        resource_efficiency = self._calculate_resource_efficiency(task_metrics)
        
        # Генерация рекомендаций
        recommendations = self._generate_recommendations(task_metrics)
        
        # Выявление паттернов
        patterns = self._identify_patterns(task_metrics)
        
        analysis = TaskAnalysis(
            task_id=task_id,
            task_type=task_metrics.task_type,
            performance_score=performance_score,
            resource_efficiency=resource_efficiency,
            recommendations=recommendations,
            patterns=patterns
        )
        
        self.analysis_history.append(analysis)
        return analysis
    
    def _calculate_performance_score(self, metrics: TaskMetrics) -> float:
        """Рассчитывает оценку производительности задачи."""
        if not metrics.success:
            return 0.0
            
        # Базовая оценка на основе времени выполнения
        base_score = 1.0 - (metrics.execution_time / 3600)  # Нормализация к часу
        
        # Корректировка на основе использования ресурсов
        resource_penalty = (metrics.cpu_usage + metrics.memory_usage) / 200  # Нормализация к 100%
        
        return max(0.0, min(1.0, base_score - resource_penalty))
    
    def _calculate_resource_efficiency(self, metrics: TaskMetrics) -> float:
        """Рассчитывает эффективность использования ресурсов."""
        if not metrics.success:
            return 0.0
            
        # Эффективность = результат / затраченные ресурсы
        resource_usage = metrics.cpu_usage + metrics.memory_usage
        if resource_usage == 0:
            return 1.0
            
        return 1.0 / resource_usage
    
    def _generate_recommendations(self, metrics: TaskMetrics) -> List[str]:
        """Генерирует рекомендации по улучшению выполнения задачи."""
        recommendations = []
        
        if not metrics.success:
            recommendations.append(f"Исправить ошибку: {metrics.error_message}")
            
        if metrics.cpu_usage > 80:
            recommendations.append("Оптимизировать использование CPU")
            
        if metrics.memory_usage > 80:
            recommendations.append("Оптимизировать использование памяти")
            
        if metrics.execution_time > 300:  # 5 минут
            recommendations.append("Рассмотреть возможность оптимизации времени выполнения")
            
        return recommendations
    
    def _identify_patterns(self, metrics: TaskMetrics) -> List[str]:
        """Выявляет паттерны в выполнении задачи."""
        patterns = []
        
        # Анализ похожих задач
        similar_tasks = [
            m for m in self.metrics_history 
            if m.task_type == metrics.task_type and m.task_id != metrics.task_id
        ]
        
        if similar_tasks:
            avg_execution_time = sum(t.execution_time for t in similar_tasks) / len(similar_tasks)
            if metrics.execution_time > avg_execution_time * 1.5:
                patterns.append("Время выполнения значительно выше среднего")
            elif metrics.execution_time < avg_execution_time * 0.5:
                patterns.append("Время выполнения значительно ниже среднего")
                
        return patterns
    
    def get_task_statistics(self) -> Dict:
        """Возвращает общую статистику по всем задачам."""
        if not self.metrics_history:
            return {}
            
        total_tasks = len(self.metrics_history)
        successful_tasks = sum(1 for m in self.metrics_history if m.success)
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0,
            "average_execution_time": sum(m.execution_time for m in self.metrics_history) / total_tasks,
            "average_cpu_usage": sum(m.cpu_usage for m in self.metrics_history) / total_tasks,
            "average_memory_usage": sum(m.memory_usage for m in self.metrics_history) / total_tasks
        }
    
    def export_analysis(self, filepath: str) -> None:
        """Экспорт анализа в JSON файл."""
        data = {
            "task_metrics": [metrics.to_dict() for metrics in self.metrics_history],
            "statistics": self.get_task_statistics()
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Analysis exported to {filepath}") 