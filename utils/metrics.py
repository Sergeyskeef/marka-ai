from prometheus_client import Counter, Gauge, Histogram, start_http_server, REGISTRY
import time
from typing import Dict, Optional

# Проверяем, есть ли уже метрики в реестре
def setup_metrics():
    """Инициализация метрик только один раз"""
    # Проверяем, есть ли уже метрики в реестре
    existing_metrics = [m.name for m in REGISTRY.collect()]
    if 'task_execution_seconds' in existing_metrics:
        return  # уже инициализировано
    
    # Метрики для задач
    global TASK_EXECUTION_TIME, TASK_SUCCESS, TASK_FAILURE
    global CPU_USAGE, MEMORY_USAGE
    global LLM_REQUESTS, LLM_TOKENS, LLM_LATENCY
    
    TASK_EXECUTION_TIME = Histogram(
        'task_execution_seconds',
        'Time spent executing tasks',
        ['task_type']
    )

    TASK_SUCCESS = Counter(
        'task_success_total',
        'Number of successfully completed tasks',
        ['task_type']
    )

    TASK_FAILURE = Counter(
        'task_failure_total',
        'Number of failed tasks',
        ['task_type', 'error_type']
    )

    # Метрики ресурсов
    CPU_USAGE = Gauge(
        'cpu_usage_percent',
        'CPU usage percentage',
        ['task_id']
    )

    MEMORY_USAGE = Gauge(
        'memory_usage_percent',
        'Memory usage percentage',
        ['task_id']
    )

    # Метрики для LLM
    LLM_REQUESTS = Counter(
        'llm_requests_total',
        'Number of LLM requests',
        ['model', 'operation']
    )

    LLM_TOKENS = Counter(
        'llm_tokens_total',
        'Number of tokens processed',
        ['model', 'operation']
    )

    LLM_LATENCY = Histogram(
        'llm_request_seconds',
        'Time spent waiting for LLM responses',
        ['model', 'operation']
    )

# Инициализируем метрики
setup_metrics()

class MetricsManager:
    def __init__(self, port: int = 8000):
        """Инициализация менеджера метрик"""
        self.port = port
        start_http_server(port)
        
    def record_task_execution(self, task_type: str, execution_time: float):
        """Запись времени выполнения задачи"""
        TASK_EXECUTION_TIME.labels(task_type=task_type).observe(execution_time)
        
    def record_task_success(self, task_type: str):
        """Запись успешного выполнения задачи"""
        TASK_SUCCESS.labels(task_type=task_type).inc()
        
    def record_task_failure(self, task_type: str, error_type: str):
        """Запись неудачного выполнения задачи"""
        TASK_FAILURE.labels(task_type=task_type, error_type=error_type).inc()
        
    def update_resource_metrics(self, task_id: str, cpu_usage: float, memory_usage: float):
        """Обновление метрик использования ресурсов"""
        CPU_USAGE.labels(task_id=task_id).set(cpu_usage)
        MEMORY_USAGE.labels(task_id=task_id).set(memory_usage)
        
    def record_llm_request(self, model: str, operation: str, tokens: int, latency: float):
        """Запись метрик LLM запроса"""
        LLM_REQUESTS.labels(model=model, operation=operation).inc()
        LLM_TOKENS.labels(model=model, operation=operation).inc(tokens)
        LLM_LATENCY.labels(model=model, operation=operation).observe(latency)

# Создаем глобальный экземпляр менеджера метрик
metrics_manager = MetricsManager() 