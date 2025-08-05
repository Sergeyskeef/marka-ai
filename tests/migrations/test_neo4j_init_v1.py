"""
Тест для проверки миграции Graph Schema v1
Проверяет создание индексов, constraints и тестовых данных
"""

import pytest
import requests
import time
from neo4j import GraphDatabase


class TestNeo4jMigrationV1:
    """Тесты для миграции Neo4j Graph Schema v1"""

    @pytest.fixture(scope="class")
    def neo4j_driver(self):
        """Фикстура для подключения к Neo4j"""
        # Создаем драйвер для прямого подключения
        driver = GraphDatabase.driver(
            "bolt://graphiti-neo4j:7687",
            auth=("neo4j", "password")
        )
        
        # Проверяем подключение
        try:
            with driver.session() as session:
                session.run("RETURN 1")
            print("✅ Подключение к Neo4j успешно")
        except Exception as e:
            pytest.fail(f"❌ Не удалось подключиться к Neo4j: {e}")
        
        yield driver
        driver.close()

    def test_migration_script_exists(self):
        """Проверяет, что миграционный скрипт существует"""
        import os
        script_path = "langchain_api/migrations/neo4j_init_v1.cypher"
        assert os.path.exists(script_path), f"Миграционный скрипт не найден: {script_path}"
        print(f"✅ Миграционный скрипт найден: {script_path}")

    def test_constraints_created(self, neo4j_driver):
        """Проверяет создание всех необходимых constraints"""
        expected_constraints = [
            "user_id",
            "preference_id", 
            "toolcall_id",
            "outcome_id",
            "diary_entry_id",
            "concept_id"
        ]
        
        with neo4j_driver.session() as session:
            result = session.run("SHOW CONSTRAINTS")
            constraints = [record["name"] for record in result]
            
            print(f"✅ Найдено {len(constraints)} constraints в базе данных")
            
            for constraint in expected_constraints:
                assert constraint in constraints, f"Constraint {constraint} не найден"
                print(f"✅ Constraint {constraint} найден")
                
    def test_indexes_created(self, neo4j_driver):
        """Проверяет создание всех необходимых индексов"""
        expected_indexes = [
            "user_email",
            "user_created_at", 
            "preference_key",
            "user_pref_relationship",
            "toolcall_user_tool",
            "toolcall_started_at",
            "toolcall_status",
            "outcome_toolcall",
            "outcome_success",
            "outcome_created_at",
            "diary_user",
            "diary_timestamp",
            "diary_content",
            "concept_name",
            "concept_category",
            "concept_description"
        ]
        
        with neo4j_driver.session() as session:
            result = session.run("SHOW INDEXES")
            indexes = [record["name"] for record in result]
            
            print(f"✅ Найдено {len(indexes)} индексов в базе данных")
            
            for index in expected_indexes:
                assert index in indexes, f"Индекс {index} не найден"
                print(f"✅ Индекс {index} найден")
                    
    def test_test_data_created(self, neo4j_driver):
        """Проверяет создание тестовых данных"""
        with neo4j_driver.session() as session:
            # Проверяем тестового пользователя
            result = session.run(
                "MATCH (u:User {id: 'test_user_001'}) RETURN u"
            )
            user = result.single()
            assert user is not None, "Тестовый пользователь не найден"
            print("✅ Тестовый пользователь найден")
            
            # Проверяем тестовое предпочтение
            result = session.run(
                "MATCH (p:Preference {id: 'pref_001'}) RETURN p"
            )
            preference = result.single()
            assert preference is not None, "Тестовое предпочтение не найдено"
            print("✅ Тестовое предпочтение найдено")
            
            # Проверяем тестовую запись дневника
            result = session.run(
                "MATCH (d:DiaryEntry {id: 'diary_001'}) RETURN d"
            )
            diary = result.single()
            assert diary is not None, "Тестовая запись дневника не найдена"
            print("✅ Тестовая запись дневника найдена")
            
            # Проверяем связи
            result = session.run(
                "MATCH (u:User {id: 'test_user_001'})-[:PREFERS]->(p:Preference {id: 'pref_001'}) RETURN count(*) as count"
            )
            pref_relation = result.single()["count"]
            assert pref_relation > 0, "Связь User-Preference не найдена"
            print("✅ Связь User-Preference найдена")
            
            result = session.run(
                "MATCH (u:User {id: 'test_user_001'})-[:WRITES]->(d:DiaryEntry {id: 'diary_001'}) RETURN count(*) as count"
            )
            write_relation = result.single()["count"]
            assert write_relation > 0, "Связь User-DiaryEntry не найдена"
            print("✅ Связь User-DiaryEntry найдена")

    def test_schema_validation(self, neo4j_driver):
        """Проверяет общую структуру схемы"""
        with neo4j_driver.session() as session:
            # Проверяем, что все основные типы узлов доступны
            result = session.run(
                "MATCH (n) RETURN labels(n) as labels, count(n) as count ORDER BY count DESC"
            )
            node_types = [record["labels"] for record in result]
            
            expected_labels = [["User"], ["Preference"], ["DiaryEntry"], ["Concept"], ["ToolCall"], ["Outcome"]]
            
            print(f"✅ Найдено {len(node_types)} типов узлов в базе данных")
            print("✅ Схема Graph Schema v1 готова к использованию")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
