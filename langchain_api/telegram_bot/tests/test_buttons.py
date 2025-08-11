import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from telegram import Update, CallbackQuery, User, Message, Chat
from telegram.ext import ContextTypes

from .telegram_bot.handlers.buttons import (
    PreferenceButtons,
    handle_preference_callback,
    handle_feedback,
    handle_menu,
    show_preferences_stats,
    reset_preferences
)

class TestPreferenceButtons:
    """Тесты для клавиатур предпочтений"""
    
    def test_create_style_keyboard(self):
        """Тест создания клавиатуры стилей"""
        keyboard = PreferenceButtons.create_style_keyboard()
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2
        
        # Проверяем callback_data
        assert keyboard.inline_keyboard[0][0].callback_data == "pref:style:brief"
        assert keyboard.inline_keyboard[0][1].callback_data == "pref:style:detailed"
        assert keyboard.inline_keyboard[1][0].callback_data == "pref:style:creative"
        assert keyboard.inline_keyboard[1][1].callback_data == "pref:style:analytical"
    
    def test_create_detail_level_keyboard(self):
        """Тест создания клавиатуры уровней детализации"""
        keyboard = PreferenceButtons.create_detail_level_keyboard()
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2
        
        # Проверяем callback_data
        assert keyboard.inline_keyboard[0][0].callback_data == "pref:detail_level:quick"
        assert keyboard.inline_keyboard[0][1].callback_data == "pref:detail_level:medium"
        assert keyboard.inline_keyboard[1][0].callback_data == "pref:detail_level:detailed"
        assert keyboard.inline_keyboard[1][1].callback_data == "pref:detail_level:comprehensive"
    
    def test_create_feedback_keyboard(self):
        """Тест создания клавиатуры обратной связи"""
        keyboard = PreferenceButtons.create_feedback_keyboard()
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2
        
        # Проверяем callback_data
        assert keyboard.inline_keyboard[0][0].callback_data == "feedback:positive"
        assert keyboard.inline_keyboard[0][1].callback_data == "feedback:negative"
        assert keyboard.inline_keyboard[1][0].callback_data == "feedback:retry"
        assert keyboard.inline_keyboard[1][1].callback_data == "feedback:clarify"
    
    def test_create_preferences_menu_keyboard(self):
        """Тест создания главного меню предпочтений"""
        keyboard = PreferenceButtons.create_preferences_menu_keyboard()
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 2
        assert len(keyboard.inline_keyboard[0]) == 2
        assert len(keyboard.inline_keyboard[1]) == 2
        
        # Проверяем callback_data
        assert keyboard.inline_keyboard[0][0].callback_data == "menu:style"
        assert keyboard.inline_keyboard[0][1].callback_data == "menu:detail_level"
        assert keyboard.inline_keyboard[1][0].callback_data == "menu:stats"
        assert keyboard.inline_keyboard[1][1].callback_data == "menu:reset"

class TestPreferenceCallbacks:
    """Тесты для обработчиков callback-запросов"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.user_id = 12345
        self.user = User(id=self.user_id, first_name="Test", is_bot=False)
        self.chat = Chat(id=12345, type="private")
        self.message = Message(message_id=1, date=None, chat=self.chat)
        
    def create_mock_query(self, callback_data: str):
        """Создает мок для CallbackQuery"""
        query = MagicMock(spec=CallbackQuery)
        query.data = callback_data
        query.from_user = self.user
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        return query
    
    @patch('langchain_api.telegram_bot.handlers.buttons.upsert_user_pref')
    @pytest.mark.asyncio
    async def test_handle_preference_callback_success(self, mock_upsert):
        """Тест успешной обработки предпочтения"""
        mock_upsert.return_value = True
        
        query = self.create_mock_query("pref:style:brief")
        update = MagicMock(spec=Update)
        update.callback_query = query
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        await handle_preference_callback(update, context)
        
        # Проверяем, что функция была вызвана
        mock_upsert.assert_called_once_with(str(self.user_id), "style", "brief")
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        
        # Проверяем текст ответа
        call_args = query.edit_message_text.call_args
        assert "✅ Предпочтение сохранено!" in call_args[0][0]
        assert "**style**: brief" in call_args[0][0]
    
    @patch('langchain_api.telegram_bot.handlers.buttons.upsert_user_pref')
    @pytest.mark.asyncio
    async def test_handle_preference_callback_failure(self, mock_upsert):
        """Тест неудачной обработки предпочтения"""
        mock_upsert.return_value = False
        
        query = self.create_mock_query("pref:style:brief")
        update = MagicMock(spec=Update)
        update.callback_query = query
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        
        await handle_preference_callback(update, context)
        
        # Проверяем, что функция была вызвана
        mock_upsert.assert_called_once_with(str(self.user_id), "style", "brief")
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        
        # Проверяем текст ответа
        call_args = query.edit_message_text.call_args
        assert "❌ Ошибка сохранения предпочтения" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_handle_feedback_positive(self):
        """Тест обработки положительной обратной связи"""
        query = self.create_mock_query("feedback:positive")
        
        with patch('langchain_api.telegram_bot.handlers.buttons.upsert_user_pref') as mock_upsert:
            await handle_feedback(query, str(self.user_id), "positive")
            
            # Проверяем, что обратная связь была сохранена
            mock_upsert.assert_called_once_with(str(self.user_id), "last_feedback", "positive")
            query.edit_message_text.assert_called_once()
            
            # Проверяем текст ответа
            call_args = query.edit_message_text.call_args
            assert "👍 Спасибо за положительную оценку!" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_handle_feedback_negative(self):
        """Тест обработки отрицательной обратной связи"""
        query = self.create_mock_query("feedback:negative")
        
        with patch('langchain_api.telegram_bot.handlers.buttons.upsert_user_pref') as mock_upsert:
            await handle_feedback(query, str(self.user_id), "negative")
            
            # Проверяем, что обратная связь была сохранена
            mock_upsert.assert_called_once_with(str(self.user_id), "last_feedback", "negative")
            query.edit_message_text.assert_called_once()
            
            # Проверяем текст ответа
            call_args = query.edit_message_text.call_args
            assert "👎 Спасибо за обратную связь" in call_args[0][0]
    
    @patch('langchain_api.telegram_bot.handlers.buttons.PreferenceButtons.create_style_keyboard')
    @pytest.mark.asyncio
    async def test_handle_menu_style(self, mock_keyboard):
        """Тест обработки меню стилей"""
        mock_keyboard.return_value = MagicMock()
        query = self.create_mock_query("menu:style")
        
        await handle_menu(query, str(self.user_id), "style")
        
        # Проверяем, что была создана клавиатура стилей
        mock_keyboard.assert_called_once()
        query.edit_message_text.assert_called_once()
        
        # Проверяем текст
        call_args = query.edit_message_text.call_args
        assert "🎨 Выберите стиль ответа:" in call_args[0][0]
    
    @patch('langchain_api.telegram_bot.handlers.buttons.PreferenceButtons.create_detail_level_keyboard')
    @pytest.mark.asyncio
    async def test_handle_menu_detail_level(self, mock_keyboard):
        """Тест обработки меню уровней детализации"""
        mock_keyboard.return_value = MagicMock()
        query = self.create_mock_query("menu:detail_level")
        
        await handle_menu(query, str(self.user_id), "detail_level")
        
        # Проверяем, что была создана клавиатура уровней детализации
        mock_keyboard.assert_called_once()
        query.edit_message_text.assert_called_once()
        
        # Проверяем текст
        call_args = query.edit_message_text.call_args
        assert "📊 Выберите уровень детализации:" in call_args[0][0]
    
    @patch('langchain_api.telegram_bot.handlers.buttons.show_preferences_stats')
    @pytest.mark.asyncio
    async def test_handle_menu_stats(self, mock_show_stats):
        """Тест обработки меню статистики"""
        query = self.create_mock_query("menu:stats")
        
        await handle_menu(query, str(self.user_id), "stats")
        
        # Проверяем, что была вызвана функция показа статистики
        mock_show_stats.assert_called_once_with(query, str(self.user_id))
    
    @patch('langchain_api.telegram_bot.handlers.buttons.reset_preferences')
    @pytest.mark.asyncio
    async def test_handle_menu_reset(self, mock_reset):
        """Тест обработки меню сброса"""
        query = self.create_mock_query("menu:reset")
        
        await handle_menu(query, str(self.user_id), "reset")
        
        # Проверяем, что была вызвана функция сброса
        mock_reset.assert_called_once_with(query, str(self.user_id))

class TestPreferenceStats:
    """Тесты для статистики предпочтений"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.user_id = "12345"
        self.query = MagicMock()
        self.query.edit_message_text = AsyncMock()
    
    @patch('langchain_api.core.memory.prefs.get_all_user_prefs')
    @patch('langchain_api.telegram_bot.handlers.buttons.PreferenceButtons.create_preferences_menu_keyboard')
    @pytest.mark.asyncio
    async def test_show_preferences_stats_with_prefs(self, mock_keyboard, mock_get_prefs):
        """Тест показа статистики с предпочтениями"""
        mock_get_prefs.return_value = {
            "style": "brief",
            "detail_level": "medium",
            "last_feedback": "positive"  # Технические данные
        }
        mock_keyboard.return_value = MagicMock()
        
        await show_preferences_stats(self.query, self.user_id)
        
        # Проверяем, что функция получения предпочтений была вызвана
        mock_get_prefs.assert_called_once_with(self.user_id)
        self.query.edit_message_text.assert_called_once()
        
        # Проверяем текст
        call_args = self.query.edit_message_text.call_args
        text = call_args[0][0]
        assert "📈 **Ваши предпочтения:**" in text
        assert "• **style**: brief" in text
        assert "• **detail_level**: medium" in text
        assert "last_feedback" not in text  # Технические данные не показываются
    
    @patch('langchain_api.core.memory.prefs.get_all_user_prefs')
    @pytest.mark.asyncio
    async def test_show_preferences_stats_empty(self, mock_get_prefs):
        """Тест показа статистики без предпочтений"""
        mock_get_prefs.return_value = {}
        
        await show_preferences_stats(self.query, self.user_id)
        
        # Проверяем, что функция получения предпочтений была вызвана
        mock_get_prefs.assert_called_once_with(self.user_id)
        self.query.edit_message_text.assert_called_once()
        
        # Проверяем текст
        call_args = self.query.edit_message_text.call_args
        text = call_args[0][0]
        assert "📈 У вас пока нет сохраненных предпочтений" in text

class TestPreferenceReset:
    """Тесты для сброса предпочтений"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.user_id = "12345"
        self.query = MagicMock()
        self.query.edit_message_text = AsyncMock()
    
    @patch('langchain_api.core.memory.prefs.get_all_user_prefs')
    @patch('langchain_api.core.memory.prefs.delete_user_pref')
    @pytest.mark.asyncio
    async def test_reset_preferences_success(self, mock_delete, mock_get_prefs):
        """Тест успешного сброса предпочтений"""
        mock_get_prefs.return_value = {
            "style": "brief",
            "detail_level": "medium"
        }
        mock_delete.return_value = True
        
        await reset_preferences(self.query, self.user_id)
        
        # Проверяем, что функции были вызваны
        mock_get_prefs.assert_called_once_with(self.user_id)
        assert mock_delete.call_count == 2  # Для каждого предпочтения
        
        self.query.edit_message_text.assert_called_once()
        
        # Проверяем текст
        call_args = self.query.edit_message_text.call_args
        text = call_args[0][0]
        assert "🔄 Сброшено 2 предпочтений" in text
        assert "Все настройки вернулись к значениям по умолчанию" in text
    
    @patch('langchain_api.core.memory.prefs.get_all_user_prefs')
    @patch('langchain_api.core.memory.prefs.delete_user_pref')
    @pytest.mark.asyncio
    async def test_reset_preferences_empty(self, mock_delete, mock_get_prefs):
        """Тест сброса предпочтений без предпочтений"""
        mock_get_prefs.return_value = {}
        
        await reset_preferences(self.query, self.user_id)
        
        # Проверяем, что функции были вызваны
        mock_get_prefs.assert_called_once_with(self.user_id)
        mock_delete.assert_not_called()  # Не должно вызываться
        
        self.query.edit_message_text.assert_called_once()
        
        # Проверяем текст
        call_args = self.query.edit_message_text.call_args
        text = call_args[0][0]
        assert "🔄 Сброшено 0 предпочтений" in text 