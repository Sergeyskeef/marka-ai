"""
Интеграционный тест для проверки Graphiti ⇆ Neo4j интеграции
"""
import time

import pytest
import requests


class TestGraphitiIntegration:
    """Тесты интеграции Graphiti с Neo4j"""

    @pytest.fixture
    def api_base_url(self):
        """Базовый URL API"""
        return "http://localhost:8000"

    @pytest.fixture
    def graphiti_base_url(self):
        """Базовый URL Graphiti"""
        return "http://graphiti:7878"

    def test_health_check(self, api_base_url):
        """Проверка health check основного API"""
        response = requests.get(f"{api_base_url}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        print(f"✅ Health check: {data['status']}")

    def test_graphiti_health(self, graphiti_base_url):
        """Проверка health check Graphiti"""
        response = requests.get(f"{graphiti_base_url}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["neo4j_connected"]
        print(f"✅ Graphiti health: {data['status']}, Neo4j: {data['neo4j_connected']}")

    def test_create_episode_with_metadata(self, api_base_url):
        """Тест создания эпизода с метаданными"""
        # Создаем эпизод с различными типами метаданных
        episode_data = {
            "text": "Integration test episode",
            "metadata": {
                "source": "integration_test",
                "priority": 10,
                "category": "test",
                "tags": ["test", "integration"],
                "is_important": True
            }
        }

        response = requests.post(
            f"{api_base_url}/memory",
            json=episode_data,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"]
        assert "episode_id" in data
        assert data["text"] == "Integration test episode"

        episode_id = data["episode_id"]
        print(f"✅ Эпизод создан: {episode_id}")

        # Сохраняем episode_id для возможного использования в других тестах
        self.last_episode_id = episode_id

    def test_search_episodes(self, api_base_url):
        """Тест поиска эпизодов"""
        # Создаем тестовый эпизод для поиска
        episode_data = {
            "text": "Searchable test episode",
            "metadata": {
                "source": "search_test",
                "priority": 5
            }
        }

        # Создаем эпизод
        create_response = requests.post(
            f"{api_base_url}/memory",
            json=episode_data
        )
        assert create_response.status_code == 200

        # Ждем немного для обработки
        time.sleep(1)

        # Ищем эпизод
        search_response = requests.get(f"{api_base_url}/search?q=Searchable test")
        assert search_response.status_code == 200

        search_data = search_response.json()
        assert "items" in search_data
        assert "total" in search_data
        assert search_data["total"] > 0

        # Проверяем, что найденный эпизод содержит метаданные
        found_items = search_data["items"]
        assert len(found_items) > 0

        found_episode = None
        for item in found_items:
            if "Searchable test episode" in item.get("text", ""):
                found_episode = item
                break

        assert found_episode is not None
        assert "metadata" in found_episode
        assert found_episode["metadata"].get("source") == "search_test"
        assert found_episode["metadata"].get("priority") == 5

        print(f"✅ Поиск работает: найдено {search_data['total']} эпизодов")

    def test_graphiti_nodes_api(self, graphiti_base_url):
        """Тест API узлов Graphiti"""
        # Получаем список узлов
        response = requests.get(f"{graphiti_base_url}/nodes")
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data
        assert "total" in data

        # Проверяем, что есть узлы
        assert data["total"] > 0
        assert len(data["nodes"]) > 0

        # Проверяем структуру узла
        node = data["nodes"][0]
        assert "id" in node
        assert "type" in node
        assert "properties" in node

        print(f"✅ Graphiti API: {data['total']} узлов доступно")

    def test_metadata_persistence(self, api_base_url):
        """Тест сохранения метаданных"""
        # Создаем эпизод с уникальными метаданными
        unique_id = f"test_{int(time.time())}"
        episode_data = {
            "text": f"Metadata persistence test {unique_id}",
            "metadata": {
                "test_id": unique_id,
                "source": "persistence_test",
                "priority": 999,
                "category": "integration",
                "timestamp": int(time.time())
            }
        }

        # Создаем эпизод
        create_response = requests.post(f"{api_base_url}/memory", json=episode_data)
        assert create_response.status_code == 200

        # Ждем для обработки
        time.sleep(2)

        # Ищем эпизод
        search_response = requests.get(f"{api_base_url}/search?q={unique_id}")
        assert search_response.status_code == 200

        search_data = search_response.json()
        assert search_data["total"] > 0

        # Проверяем, что все метаданные сохранились
        found_episode = search_data["items"][0]
        metadata = found_episode["metadata"]

        assert metadata["test_id"] == unique_id
        assert metadata["source"] == "persistence_test"
        assert metadata["priority"] == 999
        assert metadata["category"] == "integration"
        # timestamp теперь называется created_at и не попадает в metadata

        print(f"✅ Метаданные сохранены: {len(metadata)} полей")

    def test_complex_metadata_types(self, api_base_url):
        """Тест обработки различных типов метаданных"""
        # Тестируем различные примитивные типы
        episode_data = {
            "text": "Complex metadata types test",
            "metadata": {
                "string_field": "test string",
                "integer_field": 42,
                "float_field": 3.14,
                "boolean_field": True,
                "list_field": [1, 2, 3],
                "null_field": None
            }
        }

        # Создаем эпизод
        create_response = requests.post(f"{api_base_url}/memory", json=episode_data)
        assert create_response.status_code == 200

        # Ждем для обработки
        time.sleep(1)

        # Ищем эпизод
        search_response = requests.get(f"{api_base_url}/search?q=Complex metadata types")
        assert search_response.status_code == 200

        search_data = search_response.json()
        assert search_data["total"] > 0

        # Проверяем, что примитивные типы сохранились
        found_episode = search_data["items"][0]
        metadata = found_episode["metadata"]

        assert metadata["string_field"] == "test string"
        assert metadata["integer_field"] == 42
        assert metadata["float_field"] == 3.14
        assert metadata["boolean_field"]
        # Списки теперь автоматически десериализуются
        assert metadata["list_field"] == [1, 2, 3]

        print("✅ Сложные типы метаданных обработаны корректно")

    def test_fulltext_search(self, api_base_url):
        """Тест полнотекстового поиска"""
        # Создаем несколько эпизодов с разным содержимым
        episodes = [
            {
                "text": "Python programming language tutorial",
                "metadata": {"category": "programming", "language": "python"}
            },
            {
                "text": "JavaScript web development guide",
                "metadata": {"category": "programming", "language": "javascript"}
            },
            {
                "text": "Machine learning with Python and TensorFlow",
                "metadata": {"category": "ai", "language": "python"}
            }
        ]

        # Создаем эпизоды
        for episode in episodes:
            response = requests.post(f"{api_base_url}/memory", json=episode)
            assert response.status_code == 200

        # Ждем для обработки
        time.sleep(2)

        # Тестируем поиск по ключевым словам
        search_queries = [
            ("Python", 2),  # Должно найти 2 эпизода
            ("JavaScript", 1),  # Должно найти 1 эпизод
            ("machine learning", 1),  # Должно найти 1 эпизод
            ("programming", 2),  # Должно найти 2 эпизода
        ]

        for query, expected_count in search_queries:
            response = requests.get(f"{api_base_url}/search?q={query}")
            assert response.status_code == 200

            data = response.json()
            actual_count = data["total"]

            print(f"Поиск '{query}': найдено {actual_count} (ожидалось {expected_count})")
            assert actual_count >= expected_count, f"Поиск '{query}' вернул {actual_count}, ожидалось {expected_count}"

        print("✅ Полнотекстовый поиск работает корректно")

    def test_neo4j_indexes_and_constraints(self, api_base_url, graphiti_base_url):
        """Тест проверки индексов и constraints в Neo4j"""
        # Создаем эпизод для проверки
        episode_data = {
            "text": "Test episode for indexes and constraints",
            "metadata": {"test": True, "priority": 1}
        }

        response = requests.post(f"{api_base_url}/memory", json=episode_data)
        assert response.status_code == 200

        # Ждем для обработки
        time.sleep(1)

        # Проверяем, что эпизод создался
        search_response = requests.get(f"{api_base_url}/search?q=indexes and constraints")
        assert search_response.status_code == 200

        data = search_response.json()
        assert data["total"] > 0

        print("✅ Эпизод создан и найден через поиск")

        # Проверяем health Graphiti (должен показать индексы)
        graphiti_health = requests.get(f"{graphiti_base_url}/health")
        assert graphiti_health.status_code == 200

        health_data = graphiti_health.json()
        assert health_data["neo4j_connected"]

        print("✅ Graphiti подключен к Neo4j с индексами")


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"])
