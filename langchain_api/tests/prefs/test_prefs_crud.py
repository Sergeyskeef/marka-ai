import pytest
from unittest.mock import patch, MagicMock
from core.memory.prefs import (
    get_user_pref, upsert_user_pref, get_all_user_prefs, delete_user_pref
)

class TestPreferencesCRUD:
    """Тесты для CRUD операций с предпочтениями пользователей"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.user_id = "test_user_001"
        self.pref_key = "style"
        self.pref_value = "detailed"
    
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_get_user_pref_success(self, mock_graph_db):
        """Тест успешного получения предпочтения"""
        # Мокаем результат запроса
        mock_record = MagicMock()
        mock_record.__getitem__.return_value = "detailed"
        
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        # Выполняем тест
        result = get_user_pref(self.user_id, self.pref_key)
        
        # Проверяем результат
        assert result == "detailed"
        mock_session.run.assert_called_once()
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_get_user_pref_not_found(self, mock_graph_db):
        """Тест получения несуществующего предпочтения"""
        mock_result = MagicMock()
        mock_result.single.return_value = None
        
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = get_user_pref(self.user_id, self.pref_key)
        
        assert result is None
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_upsert_user_pref_success(self, mock_graph_db):
        """Тест успешного создания/обновления предпочтения"""
        mock_session = MagicMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = upsert_user_pref(self.user_id, self.pref_key, self.pref_value)
        
        assert result is True
        # Проверяем, что вызвалось 3 запроса: создание пользователя, предпочтения и связи
        assert mock_session.run.call_count == 3
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_upsert_user_pref_error(self, mock_graph_db):
        """Тест ошибки при создании предпочтения"""
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = upsert_user_pref(self.user_id, self.pref_key, self.pref_value)
        
        assert result is False
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_get_all_user_prefs_success(self, mock_graph_db):
        """Тест получения всех предпочтений пользователя"""
        # Мокаем несколько записей
        mock_records = [
            MagicMock(__getitem__=lambda self, key: {"key": "style", "value": "detailed"}[key]),
            MagicMock(__getitem__=lambda self, key: {"key": "detail_level", "value": "high"}[key])
        ]
        
        mock_result = MagicMock()
        mock_result.__iter__.return_value = mock_records
        
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = get_all_user_prefs(self.user_id)
        
        expected = {"style": "detailed", "detail_level": "high"}
        assert result == expected
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_get_all_user_prefs_empty(self, mock_graph_db):
        """Тест получения предпочтений для пользователя без предпочтений"""
        mock_result = MagicMock()
        mock_result.__iter__.return_value = []
        
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = get_all_user_prefs(self.user_id)
        
        assert result == {}
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_delete_user_pref_success(self, mock_graph_db):
        """Тест успешного удаления предпочтения"""
        mock_record = MagicMock()
        mock_record.__getitem__.return_value = 1  # Удалена 1 связь
        
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = delete_user_pref(self.user_id, self.pref_key)
        
        assert result is True
        
    @patch('langchain_api.core.memory.prefs.GraphDatabase')
    def test_delete_user_pref_not_found(self, mock_graph_db):
        """Тест удаления несуществующего предпочтения"""
        mock_record = MagicMock()
        mock_record.__getitem__.return_value = 0  # Удалено 0 связей
        
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        
        mock_session = MagicMock()
        mock_session.run.return_value = mock_result
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None
        
        mock_graph_db.driver.return_value = mock_driver
        
        result = delete_user_pref(self.user_id, self.pref_key)
        
        assert result is False

class TestPreferencesIntegration:
    """Интеграционные тесты с реальной базой данных"""
    
    def test_prefs_workflow_with_real_db(self):
        """Тест полного цикла работы с предпочтениями в реальной БД"""
        import time
        user_id = f"test_user_prefs_{int(time.time())}"  # Уникальный ID с временной меткой
        pref_key = f"test_style_{int(time.time())}"  # Уникальный ключ предпочтения
        
        # 1. Проверяем, что предпочтения изначально нет
        initial_pref = get_user_pref(user_id, pref_key)
        assert initial_pref is None
        
        # 2. Создаем предпочтение
        success = upsert_user_pref(user_id, pref_key, "detailed")
        assert success is True
        
        # 3. Получаем созданное предпочтение
        saved_pref = get_user_pref(user_id, pref_key)
        assert saved_pref == "detailed"
        
        # 4. Обновляем предпочтение
        success = upsert_user_pref(user_id, pref_key, "brief")
        assert success is True
        
        # 5. Проверяем обновление
        updated_pref = get_user_pref(user_id, pref_key)
        assert updated_pref == "brief"
        
        # 6. Получаем все предпочтения
        all_prefs = get_all_user_prefs(user_id)
        assert pref_key in all_prefs
        assert all_prefs[pref_key] == "brief"
        
        # 7. Удаляем предпочтение
        success = delete_user_pref(user_id, pref_key)
        assert success is True
        
        # 8. Проверяем удаление
        deleted_pref = get_user_pref(user_id, pref_key)
        assert deleted_pref is None 