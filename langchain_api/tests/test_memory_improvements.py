#!/usr/bin/env python3
"""
Тесты для улучшений системы памяти
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Добавляем путь к модулям
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from core.memory.memory_manager import MemoryManager
from core.memory.models import MemoryEntry, MemoryMetadata, MemoryResponse


class TestMemoryImprovements:
    """Тесты для улучшений системы памяти"""
    
    @pytest.fixture
    def memory_manager(self):
        """Создает экземпляр MemoryManager"""
        return MemoryManager()
    
    @pytest.mark.asyncio
    async def test_save_method_exists(self, memory_manager):
        """Проверяет, что метод save существует и работает"""
        # Мокаем graphiti_adapter
        with patch('core.memory.memory_manager.graphiti_adapter') as mock_adapter:
            mock_adapter.create_episode = AsyncMock(return_value={"success": True, "id": "test-123"})
            
            # Вызываем метод save
            result = await memory_manager.save("Test text", {"user_id": "123"})
            
            # Проверяем результат
            assert result["success"] is True
            assert result["id"] == "test-123"
            
            # Проверяем, что был вызван create_episode
            mock_adapter.create_episode.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_metadata_validation(self, memory_manager):
        """Проверяет валидацию метаданных"""
        with patch('core.memory.memory_manager.graphiti_adapter') as mock_adapter:
            mock_adapter.create_episode = AsyncMock(return_value={"success": True})
            
            # Тест с валидными метаданными
            valid_metadata = {
                "user_id": "123",
                "tags": ["test", "validation"],
                "importance": 0.8
            }
            
            result = await memory_manager.add_episode("Test", valid_metadata)
            assert result["success"] is True
            
            # Тест с невалидными метаданными (importance > 1)
            invalid_metadata = {
                "importance": 1.5  # Больше максимума
            }
            
            result = await memory_manager.add_episode("Test", invalid_metadata)
            assert result["success"] is False
            assert "Validation error" in result["error"]
    
    def test_memory_metadata_model(self):
        """Тестирует модель MemoryMetadata"""
        # Тест автоматического timestamp
        metadata = MemoryMetadata(user_id="123")
        assert metadata.timestamp is not None
        assert metadata.timestamp > 0
        
        # Тест преобразования строки в список tags
        metadata = MemoryMetadata(tags="single_tag")
        assert metadata.tags == ["single_tag"]
        
        # Тест ограничения importance
        with pytest.raises(ValueError):
            MemoryMetadata(importance=1.5)
    
    def test_memory_entry_model(self):
        """Тестирует модель MemoryEntry"""
        # Тест очистки текста от пробелов
        entry = MemoryEntry(text="  Test text  ")
        assert entry.text == "Test text"
        
        # Тест минимальной длины
        with pytest.raises(ValueError):
            MemoryEntry(text="")
        
        # Тест максимальной длины
        with pytest.raises(ValueError):
            MemoryEntry(text="x" * 10001)
    
    def test_memory_response_validation(self):
        """Тестирует модель MemoryResponse"""
        # Успешный ответ
        response = MemoryResponse(success=True, message="OK")
        assert response.success is True
        
        # Неуспешный ответ без error должен вызвать ошибку
        with pytest.raises(ValueError):
            MemoryResponse(success=False, message="Failed")
        
        # Неуспешный ответ с error - OK
        response = MemoryResponse(success=False, error="Some error")
        assert response.success is False
        assert response.error == "Some error"


class TestRetryLogic:
    """Тесты для retry логики"""

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """Проверяет retry при ошибке соединения"""
        from core.memory.graphiti_adapter import GraphitiMemoryAdapter
        
        adapter = GraphitiMemoryAdapter()
        
        # Мокаем RetryableHTTPClient
        with patch('core.memory.graphiti_adapter.RetryableHTTPClient') as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            
            # Симулируем успешный ответ после retry
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy"}
            mock_client.get = AsyncMock(return_value=mock_response)
            
            result = await adapter.health_check()
            
            assert result["status"] == "healthy"
            mock_client.get.assert_called_once_with("/health")

    @pytest.mark.asyncio
    async def test_retryable_http_client_supports_patch(self):
        """Убеждаемся, что RetryableHTTPClient проксирует PATCH запросы."""
        from core.error_middleware import RetryableHTTPClient

        mock_http_client = AsyncMock()
        mock_response = MagicMock()
        mock_http_client.patch = AsyncMock(return_value=mock_response)

        with patch('core.error_middleware.httpx.AsyncClient', return_value=mock_http_client):
            client = RetryableHTTPClient(base_url="http://graphiti:7878")
            response = await client.patch("/nodes/123", json={"foo": "bar"})

        mock_http_client.patch.assert_awaited_once_with("/nodes/123", json={"foo": "bar"})
        assert response is mock_response

    @pytest.mark.asyncio
    async def test_update_node_properties_uses_patch_client(self):
        """Проверяет, что GraphitiMemoryAdapter вызывает PATCH на клиенте без AttributeError."""
        from core.memory.graphiti_adapter import GraphitiMemoryAdapter

        adapter = GraphitiMemoryAdapter()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client.patch = AsyncMock(return_value=mock_response)
        adapter._retry_client = mock_client

        result = await adapter.update_node_properties("node-1", {"foo": "bar"})

        mock_client.patch.assert_awaited_once_with(
            "/nodes/node-1",
            json={"properties": {"foo": "bar"}}
        )
        assert result == {"success": True, "id": "node-1"}

    @pytest.mark.asyncio
    async def test_graphiti_adapter_close_is_idempotent(self):
        """Убеждаемся, что закрытие адаптера работает повторно и освобождает клиента."""
        from core.memory.graphiti_adapter import GraphitiMemoryAdapter

        adapter = GraphitiMemoryAdapter()
        adapter_http_client = AsyncMock()
        adapter_http_client.aclose = AsyncMock()
        adapter.client = adapter_http_client

        with patch('core.error_middleware.httpx.AsyncClient') as MockAsyncClient:
            retry_http_client = AsyncMock()
            retry_http_client.aclose = AsyncMock()
            MockAsyncClient.return_value = retry_http_client

            retry_client = await adapter._get_retry_client()
            await retry_client._ensure_client()

            await adapter.close()

            adapter_http_client.aclose.assert_awaited_once()
            retry_http_client.aclose.assert_awaited_once()
            assert retry_client.client is None
            assert adapter.client is None
            assert adapter._retry_client is None

            # Повторное закрытие не должно вызывать ошибок или повторных вызовов aclose
            await adapter.close()

            adapter_http_client.aclose.assert_awaited_once()
            retry_http_client.aclose.assert_awaited_once()


if __name__ == "__main__":
    print("🧪 Запуск тестов улучшений памяти...")
    
    # Запускаем тесты
    pytest.main([__file__, "-v"])
    
    print("\n✅ Тесты завершены!")