import time
from functools import wraps

from fastapi import FastAPI
from prometheus_client import REGISTRY, Counter, Gauge, Histogram


# Функция для безопасного создания метрик
def get_or_create_metric(metric_type, name, description, labelnames=None):
    """Получить существующую метрику или создать новую"""
    try:
        # Пытаемся найти существующую метрику
        for metric in REGISTRY.collect():
            if metric.name == name:
                return metric
    except Exception:
        pass

    # Создаем новую метрику
    if metric_type == Counter:
        return Counter(name, description, labelnames or [])
    elif metric_type == Histogram:
        return Histogram(name, description, labelnames or [])
    elif metric_type == Gauge:
        return Gauge(name, description, labelnames or [])
    return None

# Метрики для отслеживания запросов
REQUEST_COUNT = get_or_create_metric(
    Counter, 'langchain_api_requests_total', 'Total number of requests', ['endpoint', 'method']
)

REQUEST_LATENCY = get_or_create_metric(
    Histogram, 'langchain_api_request_latency_seconds', 'Request latency in seconds', ['endpoint']
)

# Метрики для отслеживания памяти
MEMORY_USAGE = get_or_create_metric(
    Gauge, 'langchain_api_memory_usage_bytes', 'Memory usage in bytes'
)

# Метрики для отслеживания ошибок
ERROR_COUNT = get_or_create_metric(
    Counter, 'langchain_api_errors_total', 'Total number of errors', ['endpoint', 'error_type']
)

CPU_USAGE = get_or_create_metric(
    Gauge, 'langchain_api_cpu_usage_percent', 'Process CPU usage percent'
)

class MetricsManager:
    """Менеджер метрик для FastAPI приложения"""

    def setup_metrics(self, app: FastAPI):
        """Настройка метрик для FastAPI приложения"""
        from prometheus_client import make_asgi_app

        # Добавляем эндпоинт для метрик
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

        # Добавляем middleware для автоматического отслеживания запросов
        @app.middleware("http")
        async def metrics_middleware(request, call_next):
            start_time = time.time()
            response = await call_next(request)
            duration = time.time() - start_time

            REQUEST_COUNT.labels(
                endpoint=request.url.path,
                method=request.method
            ).inc()
            REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)

            return response

# Создаем глобальный объект metrics для совместимости
metrics = MetricsManager()

def track_request(endpoint):
    """Декоратор для отслеживания запросов"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                REQUEST_COUNT.labels(endpoint=endpoint, method='success').inc()
                return result
            except Exception as e:
                ERROR_COUNT.labels(endpoint=endpoint, error_type=type(e).__name__).inc()
                raise
            finally:
                REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)
        return wrapper
    return decorator

def update_memory_usage():
    """Обновление метрики использования памяти (и CPU)"""
    import psutil
    process = psutil.Process()
    MEMORY_USAGE.set(process.memory_info().rss)
    try:
        CPU_USAGE.set(process.cpu_percent(interval=None))
    except Exception:
        pass
