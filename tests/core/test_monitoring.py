import pytest
import time
from core.monitoring import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    MEMORY_USAGE,
    ERROR_COUNT,
    track_request,
    update_memory_usage
)
from prometheus_client import generate_latest

@pytest.mark.asyncio
async def test_track_request_success():
    """Тест успешного отслеживания запроса"""
    @track_request('test_endpoint')
    async def test_func():
        return "success"
    
    result = await test_func()
    assert result == "success"
    
    # Проверяем метрики
    metrics = generate_latest().decode('utf-8')
    assert 'langchain_api_requests_total{endpoint="test_endpoint",method="success"} 1.0' in metrics

@pytest.mark.asyncio
async def test_track_request_error():
    """Тест отслеживания ошибки"""
    @track_request('test_endpoint')
    async def test_func():
        raise ValueError("test error")
    
    with pytest.raises(ValueError):
        await test_func()
    
    # Проверяем метрики ошибок
    metrics = generate_latest().decode('utf-8')
    assert 'langchain_api_errors_total{endpoint="test_endpoint",error_type="ValueError"} 1.0' in metrics

def test_memory_usage():
    """Тест обновления метрики использования памяти"""
    update_memory_usage()
    metrics = generate_latest().decode('utf-8')
    assert 'langchain_api_memory_usage_bytes' in metrics

@pytest.mark.asyncio
async def test_request_latency():
    """Тест измерения времени выполнения запроса"""
    @track_request('test_endpoint')
    async def test_func():
        time.sleep(0.1)
        return "success"
    
    await test_func()
    
    # Проверяем, что время выполнения запроса было измерено
    metrics = generate_latest().decode('utf-8')
    # Проверяем, что строка с нужным endpoint есть
    assert 'langchain_api_request_latency_seconds_count{endpoint="test_endpoint"}' in metrics
    assert 'langchain_api_request_latency_seconds_sum{endpoint="test_endpoint"}' in metrics 