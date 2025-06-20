from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class TaskResult:
    """Результат выполнения задачи"""
    task_id: str
    status: str
    start_time: datetime
    end_time: datetime
    success_rate: float
    performance_metrics: Dict[str, float]
    error_messages: List[str]
    insights: List[str]

@dataclass
class TaskAnalysis:
    """Анализ выполнения задачи"""
    task_id: str
    success_rate: float
    performance_score: float
    error_patterns: Dict[str, int]
    resource_efficiency: float
    recommendations: List[str]

class TaskSelfAnalysis:
    def __init__(self):
        self.task_history: List[TaskResult] = []
        
    def analyze_task_execution(self, task_result: TaskResult) -> Dict:
        """Анализ выполнения конкретной задачи"""
        analysis = {
            "success_rate": task_result.success_rate,
            "performance": self._analyze_performance(task_result),
            "error_patterns": self._analyze_errors(task_result),
            "insights": task_result.insights,
            "recommendations": self._generate_recommendations(task_result)
        }
        return analysis
        
    def _analyze_performance(self, task_result: TaskResult) -> Dict:
        """Анализ производительности выполнения задачи"""
        duration = (task_result.end_time - task_result.start_time).total_seconds()
        return {
            "duration_seconds": duration,
            "metrics": task_result.performance_metrics,
            "efficiency_score": self._calculate_efficiency_score(task_result)
        }
        
    def _analyze_errors(self, task_result: TaskResult) -> Dict:
        """Анализ ошибок и паттернов"""
        return {
            "error_count": len(task_result.error_messages),
            "error_types": self._categorize_errors(task_result.error_messages),
            "common_patterns": self._find_error_patterns(task_result.error_messages)
        }
        
    def _generate_recommendations(self, task_result: TaskResult) -> List[str]:
        """Генерация рекомендаций по улучшению"""
        recommendations = []
        
        # Анализ производительности
        if task_result.performance_metrics.get("cpu_usage", 0) > 80:
            recommendations.append("Оптимизировать использование CPU")
        if task_result.performance_metrics.get("memory_usage", 0) > 80:
            recommendations.append("Оптимизировать использование памяти")
            
        # Анализ ошибок
        if task_result.error_messages:
            recommendations.append("Улучшить обработку ошибок")
            
        # Анализ успешности
        if task_result.success_rate < 0.8:
            recommendations.append("Повысить надежность выполнения")
            
        return recommendations
        
    def _calculate_efficiency_score(self, task_result: TaskResult) -> float:
        """Расчет показателя эффективности"""
        base_score = task_result.success_rate
        
        # Корректировка на основе производительности
        if task_result.performance_metrics.get("cpu_usage", 0) > 80:
            base_score *= 0.8
        if task_result.performance_metrics.get("memory_usage", 0) > 80:
            base_score *= 0.8
            
        return round(base_score, 2)
        
    def _categorize_errors(self, errors: List[str]) -> Dict[str, int]:
        """Категоризация ошибок"""
        categories = {}
        for error in errors:
            category = self._determine_error_category(error)
            categories[category] = categories.get(category, 0) + 1
        return categories
        
    def _determine_error_category(self, error: str) -> str:
        """Определение категории ошибки"""
        error = error.lower()
        if "timeout" in error:
            return "timeout"
        elif "memory" in error:
            return "memory"
        elif "permission" in error:
            return "permission"
        elif "network" in error:
            return "network"
        else:
            return "other"
            
    def _find_error_patterns(self, errors: List[str]) -> List[str]:
        """Поиск паттернов в ошибках"""
        patterns = []
        if len(errors) > 1:
            # Простой анализ повторяющихся фраз
            error_text = " ".join(errors).lower()
            words = error_text.split()
            word_freq = {}
            for word in words:
                if len(word) > 4:  # Игнорируем короткие слова
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # Находим часто встречающиеся слова
            for word, freq in word_freq.items():
                if freq > 1:
                    patterns.append(f"Часто встречается: {word}")
                    
        return patterns

class MarkSelfAwareness:
    """Система самоанализа и самосовершенствования"""
    
    def __init__(self):
        self.analysis_history: Dict[str, List[TaskAnalysis]] = {}
        self.insights_dir = Path("insights")
        self.insights_dir.mkdir(exist_ok=True)
        
    def analyze_task_execution(self, task_result: TaskResult) -> TaskAnalysis:
        """Анализ выполнения задачи"""
        # Расчет метрик
        success_rate = task_result.success_rate
        performance_score = self._calculate_performance_score(task_result.performance_metrics)
        error_patterns = self._analyze_error_patterns(task_result.error_messages)
        resource_efficiency = self._calculate_resource_efficiency(task_result.performance_metrics)
        
        # Генерация рекомендаций
        recommendations = self._generate_recommendations(
            success_rate,
            performance_score,
            error_patterns,
            resource_efficiency
        )
        
        # Создание анализа
        analysis = TaskAnalysis(
            task_id=task_result.task_id,
            success_rate=success_rate,
            performance_score=performance_score,
            error_patterns=error_patterns,
            resource_efficiency=resource_efficiency,
            recommendations=recommendations
        )
        
        # Сохранение в историю
        if task_result.task_id not in self.analysis_history:
            self.analysis_history[task_result.task_id] = []
        self.analysis_history[task_result.task_id].append(analysis)
        
        # Сохранение инсайтов
        self._save_insights(task_result, analysis)
        
        return analysis
    
    def _calculate_performance_score(self, metrics: Dict[str, float]) -> float:
        """Расчет оценки производительности"""
        weights = {
            "cpu_usage": 0.4,
            "memory_usage": 0.4,
            "execution_time": 0.2
        }
        
        score = 0.0
        for metric, weight in weights.items():
            if metric in metrics:
                # Нормализация метрики (меньше = лучше)
                normalized = 1.0 - (metrics[metric] / 100.0)
                score += normalized * weight
                
        return min(max(score, 0.0), 1.0)
    
    def _analyze_error_patterns(self, error_messages: List[str]) -> Dict[str, int]:
        """Анализ паттернов ошибок"""
        patterns = {
            "timeout": 0,
            "memory": 0,
            "permission": 0,
            "network": 0,
            "other": 0
        }
        
        for error in error_messages:
            error_lower = error.lower()
            if "timeout" in error_lower:
                patterns["timeout"] += 1
            elif "memory" in error_lower or "out of memory" in error_lower:
                patterns["memory"] += 1
            elif "permission" in error_lower or "access denied" in error_lower:
                patterns["permission"] += 1
            elif "network" in error_lower or "connection" in error_lower:
                patterns["network"] += 1
            else:
                patterns["other"] += 1
                
        return patterns
    
    def _calculate_resource_efficiency(self, metrics: Dict[str, float]) -> float:
        """Расчет эффективности использования ресурсов"""
        if not metrics:
            return 0.0
            
        # Нормализация метрик
        cpu_efficiency = 1.0 - (metrics.get("cpu_usage", 0.0) / 100.0)
        memory_efficiency = 1.0 - (metrics.get("memory_usage", 0.0) / 100.0)
        
        # Средняя эффективность
        return (cpu_efficiency + memory_efficiency) / 2.0
    
    def _generate_recommendations(
        self,
        success_rate: float,
        performance_score: float,
        error_patterns: Dict[str, int],
        resource_efficiency: float
    ) -> List[str]:
        """Генерация рекомендаций на основе анализа"""
        recommendations = []
        
        # Рекомендации по производительности
        if performance_score < 0.7:
            recommendations.append("Низкая производительность. Рекомендуется оптимизировать использование ресурсов и время выполнения.")
        
        # Рекомендации по эффективности использования ресурсов
        if resource_efficiency < 0.6:
            recommendations.append("Низкая эффективность использования ресурсов. Рекомендуется оптимизировать распределение ресурсов.")
        
        # Рекомендации по успешности выполнения
        if success_rate < 0.8:
            recommendations.append("Низкая надежность выполнения. Рекомендуется улучшить обработку ошибок и повысить стабильность.")
        
        # Рекомендации по паттернам ошибок
        if error_patterns:
            error_types = list(error_patterns.keys())
            if "timeout" in error_types:
                recommendations.append("Обнаружены таймауты. Рекомендуется оптимизировать время выполнения или увеличить лимиты.")
            if "memory" in error_types:
                recommendations.append("Обнаружены проблемы с памятью. Рекомендуется оптимизировать использование памяти.")
            if "permission" in error_types:
                recommendations.append("Обнаружены проблемы с правами доступа. Рекомендуется проверить настройки безопасности.")
        
        # Если нет других рекомендаций, добавляем общую рекомендацию по оптимизации
        if not recommendations:
            recommendations.append("Рекомендуется провести анализ производительности и оптимизировать выполнение задачи.")
        
        return recommendations
    
    def _save_insights(self, task_result: TaskResult, analysis: TaskAnalysis):
        """Сохранение инсайтов"""
        insight = {
            "task_id": task_result.task_id,
            "timestamp": datetime.now().isoformat(),
            "result": {
                "status": task_result.status,
                "success_rate": task_result.success_rate,
                "performance_metrics": task_result.performance_metrics,
                "error_messages": task_result.error_messages,
                "insights": task_result.insights
            },
            "analysis": {
                "success_rate": analysis.success_rate,
                "performance_score": analysis.performance_score,
                "error_patterns": analysis.error_patterns,
                "resource_efficiency": analysis.resource_efficiency,
                "recommendations": analysis.recommendations
            }
        }
        
        insight_path = self.insights_dir / f"insight_{task_result.task_id}_{int(datetime.now().timestamp())}.json"
        with open(insight_path, "w") as f:
            json.dump(insight, f, indent=2)
        
    def get_task_recommendations(self, task_result: TaskResult) -> List[str]:
        """Получение рекомендаций для задачи"""
        analysis = self.analyze_task_execution(task_result)
        return analysis.recommendations
    
    def get_task_history(self, task_id: str) -> List[TaskAnalysis]:
        """Получение истории анализа задачи"""
        return self.analysis_history.get(task_id, [])
    
    def get_recent_insights(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение последних инсайтов"""
        insights = []
        for insight_file in sorted(
            self.insights_dir.glob("insight_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:limit]:
            with open(insight_file) as f:
                insights.append(json.load(f))
        return insights 