"""
Тесты для ExternalIntegrationService.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_api.services.external_integration_service import (
    ExternalIntegrationService, 
    MetricData, 
    AlertData
)

@pytest.fixture
def external_service():
    """Фикстура для создания экземпляра сервиса."""
    return ExternalIntegrationService()

@pytest.fixture
def sample_metric_data():
    """Фикстура для тестовых метрик."""
    return {
        "name": "test_metric",
        "value": 42.0,
        "labels": {"test": "value"},
        "description": "Test metric"
    }

@pytest.fixture
def sample_alert_data():
    """Фикстура для тестовых алертов."""
    return {
        "severity": "warning",
        "message": "Test alert message",
        "source": "test_service",
        "metadata": {"test": "data"}
    }

class TestExternalIntegrationService:
    """Тесты для ExternalIntegrationService."""
    
    @pytest.mark.asyncio
    async def test_service_initialization(self, external_service):
        """Тест инициализации сервиса."""
        assert external_service.metrics is not None
        assert external_service.alerts == []
        assert external_service.alert_handlers == []
        assert external_service.metric_history == []
        assert external_service.max_history_size == 10000
        
        # Проверяем, что Prometheus метрики созданы
        assert 'request_counter' in external_service.metrics
        assert 'error_counter' in external_service.metrics
        assert 'command_counter' in external_service.metrics
        assert 'request_duration' in external_service.metrics
        assert 'llm_response_time' in external_service.metrics
        assert 'active_users' in external_service.metrics
        assert 'memory_usage' in external_service.metrics
        assert 'cpu_usage' in external_service.metrics
        assert 'queue_size' in external_service.metrics
    
    @pytest.mark.asyncio
    async def test_record_metric(self, external_service, sample_metric_data):
        """Тест записи метрики."""
        # Записываем метрику
        await external_service.record_metric(
            name=sample_metric_data["name"],
            value=sample_metric_data["value"],
            labels=sample_metric_data["labels"],
            description=sample_metric_data["description"]
        )
        
        # Проверяем, что метрика добавлена в историю
        assert len(external_service.metric_history) == 1
        metric = external_service.metric_history[0]
        
        assert metric.name == sample_metric_data["name"]
        assert metric.value == sample_metric_data["value"]
        assert metric.labels == sample_metric_data["labels"]
        assert metric.description == sample_metric_data["description"]
        assert isinstance(metric.timestamp, float)
    
    @pytest.mark.asyncio
    async def test_record_multiple_metrics(self, external_service):
        """Тест записи нескольких метрик."""
        # Записываем несколько метрик
        for i in range(5):
            await external_service.record_metric(
                name=f"metric_{i}",
                value=float(i),
                labels={"index": str(i)}
            )
        
        # Проверяем, что все метрики записаны
        assert len(external_service.metric_history) == 5
        
        # Проверяем, что метрики в правильном порядке
        for i, metric in enumerate(external_service.metric_history):
            assert metric.name == f"metric_{i}"
            assert metric.value == float(i)
            assert metric.labels["index"] == str(i)
    
    @pytest.mark.asyncio
    async def test_metric_history_limit(self, external_service):
        """Тест ограничения размера истории метрик."""
        # Устанавливаем небольшой лимит для теста
        external_service.max_history_size = 3
        
        # Записываем больше метрик, чем лимит
        for i in range(5):
            await external_service.record_metric(
                name=f"metric_{i}",
                value=float(i)
            )
        
        # Проверяем, что история ограничена
        assert len(external_service.metric_history) == 3
        
        # Проверяем, что старые метрики удалены
        metric_names = [m.name for m in external_service.metric_history]
        assert "metric_0" not in metric_names
        assert "metric_1" not in metric_names
        assert "metric_2" in metric_names
        assert "metric_3" in metric_names
        assert "metric_4" in metric_names
    
    @pytest.mark.asyncio
    async def test_create_alert(self, external_service, sample_alert_data):
        """Тест создания алерта."""
        # Создаем алерт
        alert = await external_service.create_alert(
            severity=sample_alert_data["severity"],
            message=sample_alert_data["message"],
            source=sample_alert_data["source"],
            metadata=sample_alert_data["metadata"]
        )
        
        # Проверяем, что алерт создан
        assert isinstance(alert, AlertData)
        assert alert.severity == sample_alert_data["severity"]
        assert alert.message == sample_alert_data["message"]
        assert alert.source == sample_alert_data["source"]
        assert alert.metadata == sample_alert_data["metadata"]
        assert not alert.resolved
        assert isinstance(alert.timestamp, float)
        assert alert.id.startswith("alert_")
        
        # Проверяем, что алерт добавлен в список
        assert len(external_service.alerts) == 1
        assert external_service.alerts[0] == alert
    
    @pytest.mark.asyncio
    async def test_create_multiple_alerts(self, external_service):
        """Тест создания нескольких алертов."""
        # Создаем несколько алертов
        alerts = []
        for i in range(3):
            alert = await external_service.create_alert(
                severity="info",
                message=f"Alert {i}",
                source=f"service_{i}"
            )
            alerts.append(alert)
        
        # Проверяем, что все алерты созданы
        assert len(external_service.alerts) == 3
        
        # Проверяем, что ID алертов уникальны
        alert_ids = [alert.id for alert in external_service.alerts]
        assert len(set(alert_ids)) == 3
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self, external_service):
        """Тест разрешения алерта."""
        # Создаем алерт
        alert = await external_service.create_alert(
            severity="warning",
            message="Test alert",
            source="test"
        )
        
        # Проверяем, что алерт не разрешен
        assert not alert.resolved
        
        # Разрешаем алерт
        result = await external_service.resolve_alert(alert.id)
        assert result is True
        
        # Проверяем, что алерт разрешен
        assert alert.resolved
    
    @pytest.mark.asyncio
    async def test_resolve_nonexistent_alert(self, external_service):
        """Тест разрешения несуществующего алерта."""
        result = await external_service.resolve_alert("nonexistent_id")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_alert_handler(self, external_service):
        """Тест обработчика алертов."""
        handler_called = False
        handler_alert = None
        
        async def test_handler(alert):
            nonlocal handler_called, handler_alert
            handler_called = True
            handler_alert = alert
        
        # Добавляем обработчик
        await external_service.add_alert_handler(test_handler)
        assert len(external_service.alert_handlers) == 1
        
        # Создаем алерт
        alert = await external_service.create_alert(
            severity="info",
            message="Test alert",
            source="test"
        )
        
        # Проверяем, что обработчик вызван
        assert handler_called
        assert handler_alert == alert
    
    @pytest.mark.asyncio
    async def test_get_metrics_summary(self, external_service):
        """Тест получения сводки метрик."""
        # Записываем несколько метрик
        for i in range(3):
            await external_service.record_metric(
                name="test_metric",
                value=float(i + 1),
                labels={"index": str(i)}
            )
        
        # Получаем сводку
        summary = await external_service.get_metrics_summary()
        
        # Проверяем структуру сводки
        assert "timestamp" in summary
        assert "metrics" in summary
        assert "total_metrics" in summary
        assert "recent_metrics" in summary
        
        # Проверяем данные
        assert summary["total_metrics"] == 3
        assert summary["recent_metrics"] == 3
        
        # Проверяем метрики
        assert "test_metric" in summary["metrics"]
        metric_data = summary["metrics"]["test_metric"]
        assert metric_data["count"] == 3
        assert metric_data["min"] == 1.0
        assert metric_data["max"] == 3.0
        assert metric_data["avg"] == 2.0
        assert metric_data["last_value"] == 3.0
    
    @pytest.mark.asyncio
    async def test_get_alerts_summary(self, external_service):
        """Тест получения сводки алертов."""
        # Создаем несколько алертов
        for i in range(3):
            await external_service.create_alert(
                severity="info",
                message=f"Alert {i}",
                source=f"service_{i}"
            )
        
        # Разрешаем один алерт
        await external_service.resolve_alert(external_service.alerts[0].id)
        
        # Получаем сводку
        summary = await external_service.get_alerts_summary()
        
        # Проверяем структуру сводки
        assert "timestamp" in summary
        assert "total_alerts" in summary
        assert "recent_alerts" in summary
        assert "alerts_by_severity" in summary
        assert "unresolved_alerts" in summary
        assert "recent_alerts_list" in summary
        
        # Проверяем данные
        assert summary["total_alerts"] == 3
        assert summary["recent_alerts"] == 3
        assert summary["unresolved_alerts"] == 2
        assert len(summary["recent_alerts_list"]) <= 10
    
    @pytest.mark.asyncio
    async def test_export_prometheus_metrics(self, external_service):
        """Тест экспорта Prometheus метрик."""
        # Записываем метрику
        await external_service.record_metric(
            name="test_metric",
            value=42.0,
            labels={"test": "value"}
        )
        
        # Экспортируем метрики
        metrics_export = await external_service.export_prometheus_metrics()
        
        # Проверяем, что экспорт не пустой
        assert isinstance(metrics_export, str)
        assert len(metrics_export) > 0
        
        # Проверяем, что экспорт содержит метрики
        assert "# HELP" in metrics_export
        assert "# TYPE" in metrics_export
    
    @pytest.mark.asyncio
    async def test_cleanup_old_data(self, external_service):
        """Тест очистки старых данных."""
        # Записываем метрики
        for i in range(5):
            await external_service.record_metric(
                name=f"metric_{i}",
                value=float(i)
            )
        
        # Создаем алерты
        for i in range(3):
            await external_service.create_alert(
                severity="info",
                message=f"Alert {i}",
                source=f"service_{i}"
            )
        
        # Разрешаем один алерт
        await external_service.resolve_alert(external_service.alerts[0].id)
        
        # Проверяем начальное состояние
        assert len(external_service.metric_history) == 5
        assert len(external_service.alerts) == 3
        
        # Очищаем старые данные (все данные новые, поэтому ничего не должно удалиться)
        await external_service.cleanup_old_data(max_age_hours=1)
        
        # Проверяем, что данные остались
        assert len(external_service.metric_history) == 5
        assert len(external_service.alerts) == 3
    
    @pytest.mark.asyncio
    async def test_get_system_health(self, external_service):
        """Тест получения состояния здоровья системы."""
        health = await external_service.get_system_health()
        
        # Проверяем структуру
        assert "status" in health
        assert "timestamp" in health
        assert "metrics_count" in health
        assert "alerts_count" in health
        assert "unresolved_alerts" in health
        assert "prometheus_enabled" in health
        assert "grafana_enabled" in health
        assert "alerting_enabled" in health
        
        # Проверяем значения
        assert health["status"] == "healthy"
        assert health["metrics_count"] == 0
        assert health["alerts_count"] == 0
        assert health["unresolved_alerts"] == 0
        assert isinstance(health["prometheus_enabled"], bool)
        assert isinstance(health["grafana_enabled"], bool)
        assert isinstance(health["alerting_enabled"], bool)
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_send_alert_to_prometheus_alertmanager(self, mock_client, external_service):
        """Тест отправки алерта в Prometheus AlertManager."""
        # Настраиваем mock
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        # Создаем алерт
        alert = await external_service.create_alert(
            severity="warning",
            message="Test alert",
            source="test_service"
        )
        
        # Проверяем, что алерт создан
        assert len(external_service.alerts) == 1
        assert external_service.alerts[0] == alert
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_send_alert_to_grafana(self, mock_client, external_service):
        """Тест отправки алерта в Grafana."""
        # Настраиваем mock
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        # Создаем алерт
        alert = await external_service.create_alert(
            severity="info",
            message="Test alert",
            source="test_service"
        )
        
        # Проверяем, что алерт создан
        assert len(external_service.alerts) == 1
        assert external_service.alerts[0] == alert
    
    @pytest.mark.asyncio
    async def test_metric_data_structure(self):
        """Тест структуры MetricData."""
        metric = MetricData(
            name="test",
            value=42.0,
            labels={"test": "value"},
            timestamp=time.time(),
            description="Test metric"
        )
        
        assert metric.name == "test"
        assert metric.value == 42.0
        assert metric.labels == {"test": "value"}
        assert isinstance(metric.timestamp, float)
        assert metric.description == "Test metric"
    
    @pytest.mark.asyncio
    async def test_alert_data_structure(self):
        """Тест структуры AlertData."""
        alert = AlertData(
            id="test_id",
            severity="warning",
            message="Test message",
            source="test_source",
            timestamp=time.time(),
            resolved=False,
            metadata={"test": "data"}
        )
        
        assert alert.id == "test_id"
        assert alert.severity == "warning"
        assert alert.message == "Test message"
        assert alert.source == "test_source"
        assert isinstance(alert.timestamp, float)
        assert not alert.resolved
        assert alert.metadata == {"test": "data"} 