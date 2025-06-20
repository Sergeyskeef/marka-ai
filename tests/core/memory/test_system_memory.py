#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для SystemMemory и SystemMemoryWrapper.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime

from langchain_api.core.memory.system_memory import SystemMemory
from langchain_api.core.memory.system_memory_wrapper import SystemMemoryWrapper


class TestSystemMemory:
    """Тесты для SystemMemory."""
    
    @pytest.fixture
    def system_memory(self):
        """Создает экземпляр SystemMemory для тестов."""
        return SystemMemory()
    
    @pytest.fixture
    def mock_weaviate_client(self):
        """Создает мок Weaviate клиента."""
        mock_client = Mock()
        mock_collection = Mock()
        mock_client.collections.get.return_value = mock_collection
        return mock_client
    
    def test_init(self, system_memory):
        """Тест инициализации SystemMemory."""
        assert system_memory.collection_name == "SystemMemory"
        assert system_memory.priority_weights['core_docs'] == 1.0
        assert system_memory.priority_weights['logs'] == 0.3
    
    def test_insert_basic(self, system_memory):
        """Тест базовой вставки данных."""
        data = {
            'type': 'test',
            'content': 'test content',
            'filename': 'test.txt'
        }
        
        system_memory.insert(data)
        
        # Проверяем, что данные добавлены в локальную память
        results = system_memory.search({'type': 'test'})
        assert len(results) == 1
        assert results[0]['content'] == 'test content'
        assert 'timestamp' in results[0]
        assert 'version' in results[0]
        assert 'priority' in results[0]
    
    def test_insert_with_weaviate(self, mock_weaviate_client):
        """Тест вставки данных с Weaviate."""
        system_memory = SystemMemory(mock_weaviate_client)
        
        data = {
            'type': 'test',
            'content': 'test content',
            'filename': 'test.txt'
        }
        
        system_memory.insert(data)
        
        # Проверяем, что данные добавлены в локальную память
        results = system_memory.search({'type': 'test'})
        assert len(results) == 1
        assert results[0]['content'] == 'test content'
    
    def test_search_by_type(self, system_memory):
        """Тест поиска по типу."""
        # Добавляем тестовые данные
        data1 = {'type': 'core_docs', 'content': 'core content', 'filename': 'core.txt'}
        data2 = {'type': 'docs', 'content': 'docs content', 'filename': 'docs.txt'}
        data3 = {'type': 'core_docs', 'content': 'another core', 'filename': 'core2.txt'}
        
        system_memory.insert(data1)
        system_memory.insert(data2)
        system_memory.insert(data3)
        
        # Ищем core_docs
        results = system_memory.search_by_type('core_docs')
        assert len(results) == 2
        assert all(r['type'] == 'core_docs' for r in results)
    
    def test_get_identity_context(self, system_memory):
        """Тест получения контекста идентичности."""
        # Добавляем документы идентичности
        identity_data = [
            {'type': 'core_docs', 'content': 'Основной завет', 'filename': 'Основной завет. Ядро Марка.txt'},
            {'type': 'core_docs', 'content': 'Манифест Марка', 'filename': 'Манифест Марка.txt'},
            {'type': 'core_docs', 'content': 'Кодекс', 'filename': 'Кодекс.txt'},
            {'type': 'core_docs', 'content': 'Архетип', 'filename': 'Архетип Марка.txt'},
            {'type': 'core_docs', 'content': 'Сердце', 'filename': 'Сердце Марка.txt'}
        ]
        
        for data in identity_data:
            system_memory.insert(data)
        
        context = system_memory.get_identity_context()
        
        assert 'identity' in context
        assert 'manifesto' in context
        assert 'principles' in context
        assert 'timestamp' in context
        assert context['identity']['core'] == 'Основной завет'
        assert context['manifesto']['text'] == 'Манифест Марка'
    
    def test_calculate_priority(self, system_memory):
        """Тест расчета приоритетов."""
        # Тест базового приоритета
        data = {'type': 'core_docs', 'content': 'test'}
        priority = system_memory._calculate_priority(data)
        assert priority == 1.0
        
        # Тест с дополнительными флагами
        data = {'type': 'docs', 'content': 'test', 'is_core': True, 'is_critical': True}
        priority = system_memory._calculate_priority(data)
        assert abs(priority - 0.9) < 0.001  # Используем приближенное сравнение
        
        # Тест ограничения приоритета
        data = {'type': 'core_docs', 'content': 'test', 'is_core': True, 'is_critical': True}
        priority = system_memory._calculate_priority(data)
        assert priority == 1.0  # Ограничено максимумом
    
    def test_search_with_priority_sorting(self, system_memory):
        """Тест поиска с сортировкой по приоритету."""
        # Добавляем данные с разными приоритетами
        data1 = {'type': 'logs', 'content': 'log content', 'filename': 'log.txt'}
        data2 = {'type': 'core_docs', 'content': 'core content', 'filename': 'core.txt'}
        data3 = {'type': 'docs', 'content': 'docs content', 'filename': 'docs.txt'}
        
        system_memory.insert(data1)
        system_memory.insert(data2)
        system_memory.insert(data3)
        
        # Ищем все записи
        results = system_memory.search({'content': 'content'}, limit=10)
        
        # Проверяем сортировку по приоритету
        assert len(results) == 3
        assert results[0]['type'] == 'core_docs'  # Высший приоритет
        assert results[1]['type'] == 'docs'       # Средний приоритет
        assert results[2]['type'] == 'logs'       # Низкий приоритет


class TestSystemMemoryWrapper:
    """Тесты для SystemMemoryWrapper."""
    
    @pytest.fixture
    def wrapper(self):
        """Создает экземпляр SystemMemoryWrapper для тестов."""
        return SystemMemoryWrapper()
    
    def test_init(self, wrapper):
        """Тест инициализации SystemMemoryWrapper."""
        assert wrapper.version == "1.0.0"
        assert hasattr(wrapper, 'system_memory')
    
    def test_insert(self, wrapper):
        """Тест вставки данных через wrapper."""
        data = {
            'type': 'test',
            'content': 'test content',
            'filename': 'test.txt'
        }
        
        wrapper.insert(data)
        
        # Проверяем, что данные добавлены
        results = wrapper.search({'type': 'test'})
        assert len(results) == 1
        assert results[0]['content'] == 'test content'
        assert results[0]['version'] == wrapper.version
        assert 'inserted_at' in results[0]
    
    def test_update(self, wrapper):
        """Тест обновления данных."""
        # Добавляем данные
        data = {'type': 'test', 'content': 'old content', 'filename': 'test.txt'}
        wrapper.insert(data)
        
        # Обновляем данные
        update_success = wrapper.update(
            {'type': 'test'},
            {'content': 'new content'}
        )
        
        assert update_success
        
        # Проверяем обновление
        results = wrapper.search({'type': 'test'})
        assert len(results) == 1
        assert results[0]['content'] == 'new content'
        assert 'updated_at' in results[0]
    
    def test_delete(self, wrapper):
        """Тест удаления данных."""
        # Добавляем данные
        data = {'type': 'test', 'content': 'test content', 'filename': 'test.txt'}
        wrapper.insert(data)
        
        # Удаляем данные
        delete_success = wrapper.delete({'type': 'test'})
        
        assert delete_success
        
        # Проверяем, что данные помечены как удаленные
        results = wrapper.search({'type': 'test'})
        assert len(results) == 1
        assert results[0]['is_deleted'] is True
        assert 'deleted_at' in results[0]
    
    def test_get_priority_search_results(self, wrapper):
        """Тест приоритизированного поиска."""
        # Добавляем данные с разными приоритетами
        data1 = {'type': 'logs', 'content': 'log content', 'filename': 'log.txt'}
        data2 = {'type': 'core_docs', 'content': 'core content', 'filename': 'core.txt'}
        data3 = {'type': 'docs', 'content': 'docs content', 'filename': 'docs.txt'}
        
        wrapper.insert(data1)
        wrapper.insert(data2)
        wrapper.insert(data3)
        
        # Выполняем приоритизированный поиск
        results = wrapper.get_priority_search_results('content', limit=10)
        
        # Проверяем сортировку по приоритету
        assert len(results) == 3
        assert results[0]['type'] == 'core_docs'
        assert results[1]['type'] == 'docs'
        assert results[2]['type'] == 'logs'
    
    def test_get_system_status(self, wrapper):
        """Тест получения статуса системы."""
        status = wrapper.get_system_status()
        
        assert 'version' in status
        assert 'total_records' in status
        assert 'memory_types' in status
        assert 'last_updated' in status
        assert status['version'] == wrapper.version
    
    @patch('pathlib.Path.exists')
    @patch('builtins.open', create=True)
    def test_load_core_documents(self, mock_open, mock_exists, wrapper):
        """Тест загрузки основных документов."""
        # Мокаем существование файлов
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "Test content"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Создаем временную структуру файлов
            core_docs_path = Path(temp_dir) / "core_docs"
            core_docs_path.mkdir()
            
            # Создаем реальные тестовые файлы
            (core_docs_path / "test1.txt").write_text("Test content 1")
            (core_docs_path / "test2.txt").write_text("Test content 2")
            
            # Загружаем документы
            wrapper.load_core_documents(str(temp_dir))
            
            # Проверяем, что документы загружены
            results = wrapper.search_by_type('core_docs')
            assert len(results) == 2


class TestSystemMemoryIntegration:
    """Интеграционные тесты для SystemMemory."""
    
    @pytest.fixture
    def temp_docs_dir(self):
        """Создает временную директорию с тестовыми документами."""
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_path = Path(temp_dir) / "core_docs"
            docs_path.mkdir()
            
            # Создаем тестовые документы с английскими именами
            (docs_path / "core_manifesto.txt").write_text("Основной завет Марка")
            (docs_path / "manifesto.txt").write_text("Манифест системы")
            (docs_path / "codex.txt").write_text("Кодекс поведения")
            
            yield str(docs_path)
    
    def test_load_core_documents_integration(self, temp_docs_dir):
        """Интеграционный тест загрузки основных документов."""
        system_memory = SystemMemory()
        
        # Загружаем документы
        system_memory.load_core_documents(temp_docs_dir)
        
        # Проверяем загрузку
        results = system_memory.search_by_type('core_docs')
        assert len(results) == 3
        
        # Проверяем контекст идентичности
        context = system_memory.get_identity_context()
        # Ищем по содержимому, а не по имени файла
        core_content = None
        manifesto_content = None
        codex_content = None
        
        for doc in results:
            content = doc.get('content', '')
            if 'Основной завет Марка' in content:
                core_content = content
            elif 'Манифест системы' in content:
                manifesto_content = content
            elif 'Кодекс поведения' in content:
                codex_content = content
        
        assert core_content is not None
        assert manifesto_content is not None
        assert codex_content is not None
    
    def test_priority_search_integration(self, temp_docs_dir):
        """Интеграционный тест приоритизированного поиска."""
        wrapper = SystemMemoryWrapper()
        
        # Загружаем документы
        wrapper.load_core_documents(temp_docs_dir)
        
        # Добавляем документы с разными приоритетами
        wrapper.insert({'type': 'logs', 'content': 'log entry', 'filename': 'log.txt'})
        wrapper.insert({'type': 'docs', 'content': 'documentation', 'filename': 'doc.txt'})
        
        # Выполняем приоритизированный поиск
        results = wrapper.get_priority_search_results('Марка', limit=5)
        
        # Проверяем, что core_docs имеют высший приоритет
        assert len(results) > 0
        core_docs_results = [r for r in results if r['type'] == 'core_docs']
        assert len(core_docs_results) > 0
        
        # Проверяем сортировку
        priorities = [r.get('priority', 0) for r in results]
        assert priorities == sorted(priorities, reverse=True) 