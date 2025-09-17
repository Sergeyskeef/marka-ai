#!/usr/bin/env python3
"""
Тесты для системы трассировки агентов
"""
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

from middlewares.agents_trace import (
    TraceSpan,
    TraceCollector,
    trace_span,
    trace_llm_call,
    trace_tool_call
)


class TestTraceSpan:
    """Тесты для TraceSpan"""
    
    def test_span_creation(self):
        """Тест создания span"""
        span = TraceSpan("test-id", "Test Span", "test_type")
        assert span.span_id == "test-id"
        assert span.name == "Test Span"
        assert span.span_type == "test_type"
        assert span.status == "started"
        assert span.start_time > 0
        assert span.end_time is None
        assert span.duration_ms is None
    
    def test_span_finish_success(self):
        """Тест завершения span успешно"""
        span = TraceSpan("test-id", "Test Span", "test_type")
        output_data = {"result": "success"}
        
        span.finish(output_data)
        
        assert span.status == "completed"
        assert span.end_time > span.start_time
        assert span.duration_ms > 0
        assert span.output_data == output_data
        assert span.error is None
    
    def test_span_finish_error(self):
        """Тест завершения span с ошибкой"""
        span = TraceSpan("test-id", "Test Span", "test_type")
        error = "Something went wrong"
        
        span.finish(error=error)
        
        assert span.status == "error"
        assert span.end_time > span.start_time
        assert span.duration_ms > 0
        assert span.error == error
        assert span.output_data is None
    
    def test_span_to_dict(self):
        """Тест преобразования span в словарь"""
        span = TraceSpan("test-id", "Test Span", "test_type", "parent-id")
        span.input_data = {"input": "test"}
        span.metadata = {"key": "value"}
        
        span.finish({"result": "success"})
        
        span_dict = span.to_dict()
        
        assert span_dict["span_id"] == "test-id"
        assert span_dict["name"] == "Test Span"
        assert span_dict["span_type"] == "test_type"
        assert span_dict["parent_id"] == "parent-id"
        assert span_dict["status"] == "completed"
        assert "input_data" in span_dict
        assert "output_data" in span_dict
        assert "metadata" in span_dict
        assert "created_at" in span_dict


class TestTraceCollector:
    """Тесты для TraceCollector"""
    
    @contextmanager
    def temp_db(self):
        """Контекстный менеджер для временной базы данных"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            yield db_path
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_collector_init(self):
        """Тест инициализации коллектора"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            assert collector.db_path == db_path
            assert len(collector.current_spans) == 0
    
    def test_start_span(self):
        """Тест начала span"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            span_id = collector.start_span(
                "Test Span",
                "test_type",
                parent_id="parent-id",
                input_data={"input": "test"},
                metadata={"key": "value"}
            )
            
            assert span_id in collector.current_spans
            span = collector.current_spans[span_id]
            assert span.name == "Test Span"
            assert span.span_type == "test_type"
            assert span.parent_id == "parent-id"
            assert span.input_data == {"input": "test"}
            assert span.metadata["key"] == "value"
    
    def test_finish_span(self):
        """Тест завершения span"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            span_id = collector.start_span("Test Span", "test_type")
            output_data = {"result": "success"}
            
            collector.finish_span(span_id, output_data)
            
            # Span должен быть удален из активных
            assert span_id not in collector.current_spans
            
            # Проверим, что span сохранен в базе
            spans = collector.get_recent_spans(10)
            assert len(spans) == 1
            assert spans[0]["span_id"] == span_id
            assert spans[0]["status"] == "completed"
    
    def test_finish_span_error(self):
        """Тест завершения span с ошибкой"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            span_id = collector.start_span("Test Span", "test_type")
            error = "Something went wrong"
            
            collector.finish_span(span_id, error=error)
            
            spans = collector.get_recent_spans(10)
            assert len(spans) == 1
            assert spans[0]["status"] == "error"
            assert spans[0]["error"] == error
    
    def test_finish_nonexistent_span(self):
        """Тест завершения несуществующего span"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            # Не должно вызывать исключение
            collector.finish_span("nonexistent-id", {"result": "test"})
    
    def test_get_recent_spans(self):
        """Тест получения последних spans"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            # Создаем несколько spans
            for i in range(5):
                span_id = collector.start_span(f"Span {i}", "test_type")
                collector.finish_span(span_id, {"result": f"success_{i}"})
            
            # Получаем последние 3 spans
            spans = collector.get_recent_spans(3)
            assert len(spans) == 3
            
            # Проверяем порядок (новые первыми)
            assert spans[0]["name"] == "Span 4"
            assert spans[1]["name"] == "Span 3"
            assert spans[2]["name"] == "Span 2"
    
    def test_get_span_tree(self):
        """Тест получения дерева spans"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            # Создаем родительский span
            parent_id = collector.start_span("Parent Span", "parent_type")
            
            # Создаем дочерние spans
            child1_id = collector.start_span("Child 1", "child_type", parent_id)
            child2_id = collector.start_span("Child 2", "child_type", parent_id)
            
            # Завершаем все spans
            collector.finish_span(child1_id, {"result": "child1"})
            collector.finish_span(child2_id, {"result": "child2"})
            collector.finish_span(parent_id, {"result": "parent"})
            
            # Получаем дерево
            tree = collector.get_span_tree(parent_id)
            
            assert tree["span_id"] == parent_id
            assert tree["name"] == "Parent Span"
            assert len(tree["children"]) == 2
            
            child_names = [child["name"] for child in tree["children"]]
            assert "Child 1" in child_names
            assert "Child 2" in child_names
    
    def test_get_nonexistent_span_tree(self):
        """Тест получения дерева несуществующего span"""
        with self.temp_db() as db_path:
            collector = TraceCollector(db_path)
            
            tree = collector.get_span_tree("nonexistent-id")
            assert tree == {}


class TestTraceContextManager:
    """Тесты для контекстного менеджера trace_span"""
    
    def test_trace_span_success(self):
        """Тест успешного выполнения с trace_span"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Используем глобальный экземпляр, но с временной БД
            from middlewares.agents_trace import trace_collector
            original_db_path = trace_collector.db_path
            trace_collector.db_path = db_path
            trace_collector._init_database()  # Инициализируем новую БД
            
            with trace_span("Test Span", "test_type", input_data={"input": "test"}) as span_id:
                assert span_id in trace_collector.current_spans
            
            # Span должен быть завершен
            assert span_id not in trace_collector.current_spans
            
            spans = trace_collector.get_recent_spans(10)
            assert len(spans) == 1
            assert spans[0]["status"] == "completed"
            
            # Восстанавливаем оригинальный путь к БД
            trace_collector.db_path = original_db_path
        
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_trace_span_error(self):
        """Тест выполнения с ошибкой в trace_span"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Используем глобальный экземпляр, но с временной БД
            from middlewares.agents_trace import trace_collector
            original_db_path = trace_collector.db_path
            trace_collector.db_path = db_path
            trace_collector._init_database()  # Инициализируем новую БД
            
            with pytest.raises(ValueError):
                with trace_span("Test Span", "test_type") as span_id:
                    raise ValueError("Test error")
            
            # Span должен быть завершен с ошибкой
            spans = trace_collector.get_recent_spans(10)
            assert len(spans) == 1
            assert spans[0]["status"] == "error"
            assert "Test error" in spans[0]["error"]
            
            # Восстанавливаем оригинальный путь к БД
            trace_collector.db_path = original_db_path
        
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestTraceFunctions:
    """Тесты для функций трассировки"""
    
    def test_trace_llm_call(self):
        """Тест трассировки вызова LLM"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Используем глобальный экземпляр, но с временной БД
            from middlewares.agents_trace import trace_collector
            original_db_path = trace_collector.db_path
            trace_collector.db_path = db_path
            trace_collector._init_database()  # Инициализируем новую БД
            
            trace_llm_call("gpt-4.1-mini", "Hello", "Hi there!", 150.5)
            
            spans = trace_collector.get_recent_spans(10)
            assert len(spans) == 1
            assert spans[0]["span_type"] == "llm"
            assert spans[0]["name"] == "LLM Call: gpt-4.1-mini"
            assert spans[0]["status"] == "completed"
            
            # Восстанавливаем оригинальный путь к БД
            trace_collector.db_path = original_db_path
        
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_trace_tool_call(self):
        """Тест трассировки вызова инструмента"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Используем глобальный экземпляр, но с временной БД
            from middlewares.agents_trace import trace_collector
            original_db_path = trace_collector.db_path
            trace_collector.db_path = db_path
            trace_collector._init_database()  # Инициализируем новую БД
            
            trace_tool_call("test_tool", {"arg1": "value1"}, "result", 50.2)
            
            spans = trace_collector.get_recent_spans(10)
            assert len(spans) == 1
            assert spans[0]["span_type"] == "tool"
            assert spans[0]["name"] == "Tool Call: test_tool"
            assert spans[0]["status"] == "completed"
            
            # Восстанавливаем оригинальный путь к БД
            trace_collector.db_path = original_db_path
        
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 