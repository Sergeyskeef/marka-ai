#!/usr/bin/env python3
"""
E2E тест для системы сессий
Проверяет автоматическое удаление старых сообщений при превышении лимита
"""
import pytest
import time
from unittest.mock import patch, MagicMock
from core.memory.sessions import SessionBuffer, add_message_to_session, get_user_session


class TestSessionEviction:
    """Тесты для проверки автоматического удаления сообщений в сессиях"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        # Мокаем Redis клиент
        self.mock_redis = MagicMock()
        self.session_buffer = SessionBuffer()
        self.session_buffer.redis_client = self.mock_redis
        self.session_buffer.max_len = 3  # Уменьшаем для тестов
        
        # Патчим глобальные функции для использования нашего мока
        from core.memory.sessions import session_buffer
        session_buffer.redis_client = self.mock_redis
        session_buffer.max_len = 3
    
    def test_add_message_within_limit(self):
        """Тест добавления сообщений в пределах лимита"""
        user_id = "test_user_001"
        
        # Добавляем 3 сообщения
        for i in range(3):
            add_message_to_session(user_id, "user", f"Сообщение {i}")
        
        # Проверяем, что все сообщения добавлены
        assert self.mock_redis.lpush.call_count == 3
        assert self.mock_redis.ltrim.call_count == 3
        
        # Проверяем, что ltrim вызывается с правильными параметрами
        self.mock_redis.ltrim.assert_called_with(f"sess:{user_id}", 0, 2)
    
    def test_add_message_exceeds_limit(self):
        """Тест добавления сообщений сверх лимита (проверка eviction)"""
        user_id = "test_user_002"
        
        # Добавляем 5 сообщений при лимите 3
        for i in range(5):
            add_message_to_session(user_id, "user", f"Сообщение {i}")
        
        # Проверяем, что все сообщения добавлены
        assert self.mock_redis.lpush.call_count == 5
        assert self.mock_redis.ltrim.call_count == 5
        
        # Проверяем, что ltrim вызывается с правильными параметрами для ограничения длины
        self.mock_redis.ltrim.assert_called_with(f"sess:{user_id}", 0, 2)
    
    def test_session_retrieval_order(self):
        """Тест правильного порядка сообщений при получении сессии"""
        user_id = "test_user_003"
        
        # Мокаем lrange для возврата сообщений
        messages_json = [
            '{"role": "user", "content": "Сообщение 1", "timestamp": 1}',
            '{"role": "assistant", "content": "Ответ 1", "timestamp": 2}',
            '{"role": "user", "content": "Сообщение 2", "timestamp": 3}'
        ]
        self.mock_redis.lrange.return_value = messages_json
        
        # Получаем сессию
        session = get_user_session(user_id)
        
        # Проверяем, что lrange вызван с правильными параметрами
        self.mock_redis.lrange.assert_called_with(f"sess:{user_id}", 0, -1)
        
        # Проверяем, что сообщения в правильном порядке (новые в конце)
        assert len(session) == 3
        assert session[0]["content"] == "Сообщение 2"
        assert session[1]["content"] == "Ответ 1"
        assert session[2]["content"] == "Сообщение 1"
    
    def test_session_length_tracking(self):
        """Тест отслеживания длины сессии"""
        user_id = "test_user_004"
        
        # Мокаем llen для возврата длины
        self.mock_redis.llen.return_value = 2
        
        # Проверяем длину сессии
        length = self.session_buffer.get_session_length(user_id)
        
        # Проверяем, что llen вызван с правильными параметрами
        self.mock_redis.llen.assert_called_with(f"sess:{user_id}")
        assert length == 2
    
    def test_session_clear(self):
        """Тест очистки сессии"""
        user_id = "test_user_005"
        
        # Очищаем сессию
        result = self.session_buffer.clear_session(user_id)
        
        # Проверяем, что delete вызван с правильными параметрами
        self.mock_redis.delete.assert_called_with(f"sess:{user_id}")
        assert result is True
    
    def test_redis_connection_failure(self):
        """Тест поведения при недоступности Redis"""
        user_id = "test_user_006"
        
        # Устанавливаем redis_client в None (симуляция недоступности)
        from core.memory.sessions import session_buffer
        session_buffer.redis_client = None
        
        # Пытаемся добавить сообщение
        result = add_message_to_session(user_id, "user", "Тестовое сообщение")
        
        # Проверяем, что функция возвращает False при недоступности Redis
        assert result is False
    
    def test_message_format(self):
        """Тест формата сообщений"""
        user_id = "test_user_007"
        
        # Добавляем сообщение с дополнительными полями
        add_message_to_session(user_id, "user", "Тестовое сообщение", metadata={"source": "test"})
        
        # Проверяем, что lpush вызван
        assert self.mock_redis.lpush.call_count == 1
        
        # Получаем аргументы вызова lpush
        call_args = self.mock_redis.lpush.call_args
        key = call_args[0][0]
        message_json = call_args[0][1]
        
        # Проверяем ключ
        assert key == f"sess:{user_id}"
        
        # Проверяем формат сообщения
        import json
        message = json.loads(message_json)
        assert message["role"] == "user"
        assert message["content"] == "Тестовое сообщение"
        assert "timestamp" in message
        assert message["metadata"]["source"] == "test"


class TestSessionIntegration:
    """Интеграционные тесты для системы сессий"""
    
    @pytest.mark.integration
    def test_real_redis_session_eviction(self):
        """Интеграционный тест с реальным Redis"""
        # Этот тест требует запущенного Redis
        # Запускается только с маркером integration
        user_id = "integration_test_user"
        
        # Создаем буфер с реальным Redis
        session_buffer = SessionBuffer("redis://localhost:6379")
        
        if not session_buffer.is_connected():
            pytest.skip("Redis недоступен для интеграционного теста")
        
        # Очищаем сессию перед тестом
        session_buffer.clear_session(user_id)
        
        # Добавляем сообщения до превышения лимита
        max_len = session_buffer.max_len
        
        # Добавляем max_len + 2 сообщения
        for i in range(max_len + 2):
            add_message_to_session(user_id, "user", f"Сообщение {i}")
        
        # Получаем сессию
        session = get_user_session(user_id)
        
        # Проверяем, что количество сообщений не превышает лимит
        assert len(session) <= max_len
        
        # Проверяем, что самые старые сообщения удалены
        # (новые сообщения должны быть в конце)
        if len(session) > 0:
            assert "Сообщение 0" not in [msg["content"] for msg in session]
            assert f"Сообщение {max_len + 1}" in [msg["content"] for msg in session]
        
        # Очищаем сессию после теста
        session_buffer.clear_session(user_id) 