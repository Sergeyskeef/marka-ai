"""
Интеграционный тест для проверки работы MemoryManager с Graphiti и Neo4j
"""

import asyncio
import time

import pytest

# Импортируем компоненты для тестирования
from core.memory.memory_manager import memory_manager


@pytest.mark.core
@pytest.mark.asyncio
async def test_graphiti_health_check():
    """Проверяет, что Graphiti доступен и здоров"""
    health = await memory_manager.health_check()

    assert health["status"] == "healthy", f"Graphiti не здоров: {health}"
    assert health.get("neo4j_connected", False), "Graphiti не подключен к Neo4j"

    print(f"✅ Graphiti health: {health}")


@pytest.mark.core
@pytest.mark.asyncio
async def test_create_and_search_episode():
    """Тестирует создание эпизода и его поиск"""
    # Создаем уникальный текст для теста
    test_text = f"Test episode {time.time()}"
    test_metadata = {"source": "test", "timestamp": time.time()}

    # Создаем эпизод
    create_result = await memory_manager.add_episode(test_text, test_metadata)

    assert create_result.get("success", True), f"Ошибка создания эпизода: {create_result}"
    print(f"✅ Эпизод создан: {create_result}")

    # Ждем немного для индексации
    await asyncio.sleep(2)

    # Ищем эпизод
    search_result = await memory_manager.search_episodes("Test episode", limit=5)

    assert "error" not in search_result, f"Ошибка поиска: {search_result}"
    assert search_result["total"] > 0, "Эпизод не найден в поиске"

    # Проверяем, что наш эпизод в результатах
    found_episode = None
    for item in search_result["items"]:
        if test_text in item.get("text", ""):
            found_episode = item
            break

    assert found_episode is not None, "Созданный эпизод не найден в результатах поиска"
    print(f"✅ Эпизод найден в поиске: {found_episode}")


@pytest.mark.core
@pytest.mark.asyncio
async def test_task_completion_memory():
    """Тестирует запись завершения задачи в память"""
    # Создаем тестовую задачу
    task_text = f"Task completion test {time.time()}"
    task_metadata = {
        "task_id": f"test_task_{int(time.time())}",
        "type": "task_completion",
        "success": True,
        "category": "test",
        "priority": "normal"
    }

    # Добавляем в память
    result = await memory_manager.add_episode(task_text, task_metadata)

    assert result.get("success", True), f"Ошибка записи задачи: {result}"
    print(f"✅ Задача записана в память: {result}")

    # Ищем задачу
    search_result = await memory_manager.search_episodes("Task completion test", limit=5)

    assert "error" not in search_result, f"Ошибка поиска задачи: {search_result}"
    assert search_result["total"] > 0, "Задача не найдена в поиске"

    # Проверяем метаданные
    found_task = None
    for item in search_result["items"]:
        if task_text in item.get("text", ""):
            found_task = item
            break

    assert found_task is not None, "Задача не найдена в результатах"
    assert found_task.get("metadata", {}).get("type") == "task_completion", "Неверный тип метаданных"
    print(f"✅ Задача найдена с правильными метаданными: {found_task}")


@pytest.mark.core
@pytest.mark.asyncio
async def test_neo4j_episode_creation():
    """Проверяет, что эпизод действительно создается в Neo4j"""
    # Создаем уникальный эпизод
    unique_text = f"Neo4j test episode {time.time()}"
    unique_metadata = {"test_type": "neo4j_verification", "timestamp": time.time()}

    # Добавляем эпизод
    create_result = await memory_manager.add_episode(unique_text, unique_metadata)

    assert create_result.get("success", True), f"Ошибка создания эпизода: {create_result}"
    episode_id = create_result.get("id")
    print(f"✅ Эпизод создан с ID: {episode_id}")

    # Ждем для индексации
    await asyncio.sleep(3)

    # Ищем эпизод (это проверяет, что эпизод сохранен в Neo4j)
    search_result = await memory_manager.search_episodes(unique_text, limit=5)

    assert "error" not in search_result, f"Ошибка поиска: {search_result}"
    assert search_result["total"] > 0, "Эпизод не найден в поиске"

    # Проверяем, что эпизод в результатах и имеет правильные метаданные
    found = False
    for item in search_result["items"]:
        if unique_text in item.get("text", ""):
            found = True
            assert item.get("metadata", {}).get("test_type") == "neo4j_verification", "Метаданные не совпадают"
            print(f"✅ Эпизод найден в поиске: {item}")
            break

    assert found, "Созданный эпизод не найден в результатах поиска"
    print("✅ Эпизод сохранен в Neo4j и доступен через поиск")


@pytest.mark.core
@pytest.mark.asyncio
async def test_memory_manager_stats():
    """Проверяет статистику MemoryManager"""
    # Получаем начальную статистику
    initial_stats = memory_manager.get_memory_stats()
    initial_entries = initial_stats["total_entries"]

    # Создаем тестовый эпизод
    test_text = f"Stats test {time.time()}"
    result = await memory_manager.add_episode(test_text)

    assert result.get("success", True), f"Ошибка создания эпизода: {result}"

    # Получаем обновленную статистику
    updated_stats = memory_manager.get_memory_stats()
    updated_entries = updated_stats["total_entries"]

    # Проверяем, что счетчик увеличился
    assert updated_entries >= initial_entries, "Счетчик эпизодов не увеличился"
    print(f"✅ Статистика обновлена: {initial_entries} -> {updated_entries}")


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v", "-s"])
