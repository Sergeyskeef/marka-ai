#!/usr/bin/env python3
"""
Тесты для Neo4j backend векторного поиска DiaryEntry
"""

import pytest
import time
import asyncio
import unittest.mock as mock
from unittest.mock import MagicMock, patch, AsyncMock
import json

from core.graphiti.backend_neo4j import (
    Neo4jDiaryBackend,
    neo4j_diary_backend
)


class TestNeo4jDiaryBackend:
    """Тесты для Neo4jDiaryBackend"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        self.backend = Neo4jDiaryBackend()
    
    def test_is_success_entry_positive(self):
        """Тест определения успешной записи - позитивные случаи"""
        # Тест с ключевыми словами успеха
        assert self.backend._is_success_entry("Проблема решена успешно", {}) is True
        assert self.backend._is_success_entry("Удалось исправить ошибку", {}) is True
        assert self.backend._is_success_entry("Код working properly now", {}) is True
        
        # Тест с тегами
        assert self.backend._is_success_entry("Test entry", {"tags": ["success", "resolved"]}) is True
        
        # Тест с источником
        assert self.backend._is_success_entry("Detailed solution explanation here", {"source": "user"}) is True
    
    def test_is_success_entry_negative(self):
        """Тест определения успешной записи - негативные случаи"""
        # Тест с ключевыми словами неудач
        assert self.backend._is_success_entry("Ошибка не исправлена", {}) is False
        assert self.backend._is_success_entry("Code not working still", {}) is False
        assert self.backend._is_success_entry("Проблема не решена", {}) is False
        
        # Тест с источником рефлексии
        assert self.backend._is_success_entry("Analysis text", {"source": "self"}) is False
        
        # Тест с коротким текстом
        assert self.backend._is_success_entry("Short", {"source": "user"}) is False
    
    def test_extract_success_insights(self):
        """Тест извлечения инсайтов из успешной записи"""
        content = "Использовал инструмент поиска для получения данных из памяти"
        context = {"tools_used": ["search", "memory"], "strategy": "multi_step"}
        
        insights = self.backend._extract_success_insights(content, context)
        
        assert "tool_usage" in insights
        assert "search_strategy" in insights
        assert "memory_usage" in insights
        assert "data_access" in insights
        assert "tool_combination" in insights
        assert "strategic_approach" in insights
    
    def test_calculate_success_score(self):
        """Тест расчета оценки успешности"""
        # Базовая оценка
        score1 = self.backend._calculate_success_score("Test", {})
        assert score1 == 0.5
        
        # С ключевыми словами и длинным текстом
        long_content = "Проблема успешно решена. " + "A" * 200
        score2 = self.backend._calculate_success_score(long_content, {})
        assert score2 > 0.5
        
        # С контекстом
        context = {"tools_used": ["tool1"], "strategy": "approach", "result": "success"}
        score3 = self.backend._calculate_success_score("Получилось", context)
        assert score3 > 0.8
    
    @pytest.mark.asyncio
    async def test_fetch_similar_successes_empty_response(self):
        """Тест поиска при пустом ответе от API"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value.decode.return_value = json.dumps({"nodes": []})
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            results = await self.backend.fetch_similar_successes("test query")
            
            assert results == []
    
    @pytest.mark.asyncio
    async def test_fetch_similar_successes_with_results(self):
        """Тест поиска с результатами"""
        # Мокаем ответ от API
        mock_nodes = [
            {
                "id": "diary_123",
                "type": "DiaryEntry",
                "score": 0.9,
                "properties": {
                    "content": "Проблема успешно решена через поиск",
                    "user_id": "user_1",
                    "source": "user",
                    "timestamp": 1640995200.0,
                    "context": '{"tools_used": ["search"]}',
                    "tags": ["success"]
                }
            },
            {
                "id": "diary_456",
                "type": "DiaryEntry", 
                "score": 0.7,
                "properties": {
                    "content": "Тест рефлексии",
                    "user_id": "user_1",
                    "source": "self",  # Это рефлексия - должна быть отфильтрована
                    "timestamp": 1640995100.0
                }
            },
            {
                "id": "episode_789",
                "type": "Episode",  # Не DiaryEntry - должен быть отфильтрован
                "score": 0.8,
                "properties": {
                    "content": "Some episode content"
                }
            }
        ]
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value.decode.return_value = json.dumps({"nodes": mock_nodes})
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            results = await self.backend.fetch_similar_successes("test query", limit=5)
            
            # Должен вернуть только одну запись (diary_123), отфильтровав рефлексию и Episode
            assert len(results) == 1
            assert results[0]["id"] == "diary_123"
            assert results[0]["content"] == "Проблема успешно решена через поиск"
            assert results[0]["similarity"] == 0.9
            assert "tool_usage" in results[0]["insights"]
            assert "search_strategy" in results[0]["insights"]
    
    @pytest.mark.asyncio
    async def test_fetch_similar_successes_user_filter(self):
        """Тест фильтрации по пользователю"""
        mock_nodes = [
            {
                "id": "diary_123",
                "type": "DiaryEntry",
                "score": 0.9,
                "properties": {
                    "content": "Решение пользователя 1",
                    "user_id": "user_1",
                    "source": "user"
                }
            },
            {
                "id": "diary_456",
                "type": "DiaryEntry",
                "score": 0.8,
                "properties": {
                    "content": "Решение пользователя 2", 
                    "user_id": "user_2",
                    "source": "user"
                }
            }
        ]
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value.decode.return_value = json.dumps({"nodes": mock_nodes})
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            # Фильтруем по user_1
            results = await self.backend.fetch_similar_successes("test", user_id="user_1")
            
            assert len(results) == 1
            assert results[0]["user_id"] == "user_1"
    
    @pytest.mark.asyncio
    async def test_fetch_similar_successes_time_limit(self):
        """Тест ограничения по времени выполнения"""
        # Мокаем медленный ответ
        def slow_urlopen(*args, **kwargs):
            time.sleep(0.2)  # 200ms задержка
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value.decode.return_value = json.dumps({"nodes": []})
            return mock_response
        
        with patch('urllib.request.urlopen', side_effect=slow_urlopen):
            start_time = time.time()
            results = await self.backend.fetch_similar_successes("test", max_duration_ms=100)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Должен завершиться быстро из-за ограничения по времени
            assert elapsed_ms < 300  # Учитываем накладные расходы
    
    @pytest.mark.asyncio
    async def test_fetch_similar_successes_api_error(self):
        """Тест обработки ошибки API"""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.read.return_value.decode.return_value = "Internal Server Error"
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            results = await self.backend.fetch_similar_successes("test query")
            
            assert results == []
    
    @pytest.mark.asyncio
    async def test_fetch_similar_successes_exception(self):
        """Тест обработки исключения"""
        with patch('urllib.request.urlopen', side_effect=Exception("Network error")):
            results = await self.backend.fetch_similar_successes("test query")
            
            assert results == []
    
    @pytest.mark.asyncio
    async def test_fetch_user_success_patterns(self):
        """Тест получения паттернов успеха пользователя"""
        mock_nodes = [
            {
                "id": "diary_123",
                "type": "DiaryEntry",
                "properties": {
                    "content": "Успешное решение с множеством деталей. Использовал поиск и память для получения контекста.",
                    "user_id": "user_1",
                    "source": "user",
                    "timestamp": 1640995200.0,
                    "context": '{"tools_used": ["search", "memory"], "result": "success"}'
                }
            }
        ]
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value.decode.return_value = json.dumps({"nodes": mock_nodes})
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            patterns = await self.backend.fetch_user_success_patterns("user_1")
            
            assert len(patterns) == 1
            assert patterns[0]["id"] == "diary_123"
            assert patterns[0]["success_score"] > 0.5
            assert "tool_usage" in patterns[0]["insights"]
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Тест успешной проверки здоровья"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value.decode.return_value = json.dumps({"status": "ok"})
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            result = await self.backend.health_check()
            
            assert result["status"] == "healthy"
            assert result["backend"] == "neo4j"
            assert result["data"]["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Тест неудачной проверки здоровья"""
        mock_response = MagicMock()
        mock_response.status = 500
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            result = await self.backend.health_check()
            
            assert result["status"] == "unhealthy"
            assert "HTTP 500" in result["error"]


class TestGlobalBackend:
    """Тесты для глобального экземпляра"""
    
    def test_global_instance_exists(self):
        """Тест что глобальный экземпляр существует"""
        assert neo4j_diary_backend is not None
        assert isinstance(neo4j_diary_backend, Neo4jDiaryBackend)
    
    def test_global_instance_is_singleton(self):
        """Тест что глобальный экземпляр - синглтон"""
        from core.graphiti.backend_neo4j import neo4j_diary_backend as backend2
        assert neo4j_diary_backend is backend2


@pytest.mark.integration
class TestNeo4jDiaryBackendIntegration:
    """Интеграционные тесты с реальным Graphiti API"""
    
    @pytest.mark.asyncio
    async def test_real_fetch_similar_successes(self):
        """Тест реального поиска успешных записей"""
        backend = Neo4jDiaryBackend()
        
        # Тестируем с общим запросом
        results = await backend.fetch_similar_successes(
            query="поиск решение проблема",
            limit=3,
            max_duration_ms=1000
        )
        
        # Проверяем что запрос выполнился корректно (результаты могут быть пустыми)
        assert isinstance(results, list)
        assert len(results) <= 3
        
        # Если есть результаты, проверяем их структуру
        for result in results:
            assert "id" in result
            assert "content" in result
            assert "similarity" in result
            assert "insights" in result
            assert isinstance(result["insights"], list)
    
    @pytest.mark.asyncio
    async def test_real_health_check(self):
        """Тест реальной проверки здоровья"""
        backend = Neo4jDiaryBackend()
        
        result = await backend.health_check()
        
        # Проверяем что запрос выполнился
        assert "status" in result
        assert result["backend"] == "neo4j"
        
        # Статус может быть healthy, unhealthy или error в зависимости от состояния Graphiti
        assert result["status"] in ["healthy", "unhealthy", "error"]
    
    @pytest.mark.asyncio 
    async def test_performance_under_150ms(self):
        """Тест что поиск выполняется быстрее 150ms"""
        backend = Neo4jDiaryBackend()
        
        start_time = time.time()
        results = await backend.fetch_similar_successes(
            query="быстрый тест",
            limit=1,
            max_duration_ms=150
        )
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Должен выполниться быстрее 150ms (с небольшим допуском на накладные расходы)
        assert elapsed_ms < 200, f"Поиск занял {elapsed_ms:.1f}ms, ожидалось < 200ms"
        assert isinstance(results, list)