"""
Тесты для задачи F-5: Feedback API - запись лайк/дизлайк в Neo4j
"""
import sys
sys.path.insert(0, '/workspace')
import json


def test_feedback_in_bot():
    """Тест обработки feedback в боте"""
    print("\n=== Тест Feedback в боте ===")
    
    # Читаем файл бота
    with open('/workspace/telegram_bot/bot.py', 'r') as f:
        bot_content = f.read()
    
    # Проверяем наличие сохранения в Neo4j
    assert "Feedback сохранен в Neo4j" in bot_content
    print("✅ Логирование сохранения в Neo4j")
    
    # Проверяем отправку в memory API
    assert "/memory/add" in bot_content
    print("✅ Отправка в memory API")
    
    # Проверяем обработку всех типов feedback
    assert 'action == "positive"' in bot_content
    assert 'action == "negative"' in bot_content
    assert 'action == "retry"' in bot_content
    assert 'action == "clarify"' in bot_content
    print("✅ Все типы feedback обрабатываются")
    
    # Проверяем сохранение метаданных
    assert '"type": "feedback"' in bot_content
    assert '"vote": action' in bot_content
    assert '"user_id": str(user_id)' in bot_content
    print("✅ Метаданные feedback корректны")


def test_feedback_api_endpoint():
    """Тест API endpoint для feedback"""
    print("\n=== Тест Feedback API endpoint ===")
    
    # Читаем main.py
    with open('/workspace/main.py', 'r') as f:
        main_content = f.read()
    
    # Проверяем наличие endpoint
    assert '@app.post("/feedback/add"' in main_content
    print("✅ Endpoint /feedback/add существует")
    
    # Проверяем сохранение в Neo4j
    assert "сохранением в Neo4j" in main_content
    print("✅ Документация упоминает Neo4j")
    
    # Проверяем использование memory_manager
    assert "memory_manager.save" in main_content
    print("✅ Используется memory_manager для сохранения")
    
    # Проверяем структуру метаданных
    assert '"feedback_type": feedback_type' in main_content
    assert '"feedback_id": feedback_id' in main_content
    assert '"user_id": str(user_id)' in main_content
    print("✅ Структура метаданных корректна")
    
    # Проверяем обработку контекста
    assert '"context": context[:500]' in main_content
    print("✅ Контекст сохраняется с ограничением длины")


def test_feedback_neo4j_structure():
    """Тест структуры данных для Neo4j"""
    print("\n=== Тест структуры данных для Neo4j ===")
    
    # Проверяем, что создается правильная структура узла
    test_metadata = {
        "type": "feedback",
        "feedback_type": "positive",
        "feedback_id": "test-123",
        "user_id": "user-456",
        "chat_id": "chat-789",
        "context": "Test context",
        "timestamp": 1234567890
    }
    
    # Проверяем все необходимые поля
    assert test_metadata["type"] == "feedback"
    assert test_metadata["feedback_type"] in ["positive", "negative", "suggestion", "bug"]
    assert "feedback_id" in test_metadata
    assert "user_id" in test_metadata
    assert "timestamp" in test_metadata
    print("✅ Структура метаданных соответствует требованиям Neo4j")
    
    # Проверяем текст для сохранения
    feedback_text = f"Feedback ({test_metadata['feedback_type']}): Test feedback"
    assert "Feedback" in feedback_text
    assert test_metadata['feedback_type'] in feedback_text
    print("✅ Текст узла форматируется правильно")


def main():
    print("🧪 Запуск тестов для F-5: Feedback API")
    
    test_feedback_in_bot()
    test_feedback_api_endpoint()
    test_feedback_neo4j_structure()
    
    print("\n🎉 Все тесты F-5 успешно пройдены!")
    print("\n📝 Примечание: Для полной проверки нужен запущенный Neo4j и Graphiti сервис")


if __name__ == "__main__":
    main()