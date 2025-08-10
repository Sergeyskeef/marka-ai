"""
Метрики для мониторинга системы промптов
"""

from prometheus_client import Counter, Histogram, Gauge
import logging

logger = logging.getLogger(__name__)

# Счетчики для промптов
prompt_selections = Counter(
    'prompt_selections_total',
    'Total number of prompt selections',
    ['prompt_name', 'environment']
)

prompt_evolutions = Counter(
    'prompt_evolutions_total',
    'Total number of prompt evolutions',
    ['prompt_name', 'trigger_reason']
)

prompt_errors = Counter(
    'prompt_errors_total',
    'Total number of prompt-related errors',
    ['operation', 'error_type']
)

# Гистограммы для производительности
prompt_selection_duration = Histogram(
    'prompt_selection_duration_seconds',
    'Time spent selecting a prompt',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

prompt_render_duration = Histogram(
    'prompt_render_duration_seconds',
    'Time spent rendering a prompt',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

context_optimization_duration = Histogram(
    'context_optimization_duration_seconds',
    'Time spent optimizing context',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

# Gauges для текущего состояния
active_prompts = Gauge(
    'active_prompts_count',
    'Number of active prompts',
    ['environment']
)

prompt_confidence_score = Gauge(
    'prompt_confidence_score',
    'Latest confidence score for prompt selection',
    ['prompt_name']
)

context_utilization = Gauge(
    'context_utilization_ratio',
    'Context window utilization ratio',
    ['prompt_name']
)

evolution_monitors_active = Gauge(
    'evolution_monitors_active',
    'Number of active evolution monitors'
)

# Метрики качества
prompt_quality_score = Histogram(
    'prompt_quality_score',
    'Quality scores for prompt responses',
    ['prompt_name'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

prompt_reward = Histogram(
    'prompt_reward',
    'Rewards given to prompts',
    ['prompt_name'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)


class PromptMetricsCollector:
    """Коллектор метрик для системы промптов"""
    
    @staticmethod
    def record_selection(prompt_name: str, environment: str, confidence: float, duration: float):
        """Записать выбор промпта"""
        prompt_selections.labels(
            prompt_name=prompt_name,
            environment=environment
        ).inc()
        
        prompt_selection_duration.observe(duration)
        prompt_confidence_score.labels(prompt_name=prompt_name).set(confidence)
    
    @staticmethod
    def record_evolution(prompt_name: str, trigger_reason: str):
        """Записать эволюцию промпта"""
        prompt_evolutions.labels(
            prompt_name=prompt_name,
            trigger_reason=trigger_reason
        ).inc()
    
    @staticmethod
    def record_error(operation: str, error_type: str):
        """Записать ошибку"""
        prompt_errors.labels(
            operation=operation,
            error_type=error_type
        ).inc()
    
    @staticmethod
    def record_render_time(duration: float):
        """Записать время рендеринга"""
        prompt_render_duration.observe(duration)
    
    @staticmethod
    def record_optimization_time(duration: float):
        """Записать время оптимизации"""
        context_optimization_duration.observe(duration)
    
    @staticmethod
    def update_active_prompts(environment: str, count: int):
        """Обновить количество активных промптов"""
        active_prompts.labels(environment=environment).set(count)
    
    @staticmethod
    def update_context_utilization(prompt_name: str, utilization: float):
        """Обновить использование контекста"""
        context_utilization.labels(prompt_name=prompt_name).set(utilization)
    
    @staticmethod
    def update_evolution_monitors(count: int):
        """Обновить количество мониторов эволюции"""
        evolution_monitors_active.set(count)
    
    @staticmethod
    def record_quality(prompt_name: str, score: float):
        """Записать оценку качества"""
        prompt_quality_score.labels(prompt_name=prompt_name).observe(score)
    
    @staticmethod
    def record_reward(prompt_name: str, reward: float):
        """Записать награду"""
        prompt_reward.labels(prompt_name=prompt_name).observe(reward)


# Глобальный экземпляр коллектора
metrics_collector = PromptMetricsCollector()