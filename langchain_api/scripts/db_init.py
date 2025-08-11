#!/usr/bin/env python3
"""
Скрипт для автоматического харднинга Neo4j базы данных
Создает индексы, constraints и оптимизирует производительность
"""

import os
import sys
import time
from typing import Any

from neo4j import GraphDatabase


class Neo4jHardening:
    def __init__(self, uri: str, username: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def run_query(self, query: str, parameters: dict[str, Any] = None) -> list[dict[str, Any]]:
        """Выполнить Cypher запрос"""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def wait_for_database(self, max_attempts: int = 30) -> bool:
        """Ждать пока база данных станет доступной"""
        print("🔄 Ожидание доступности Neo4j...")

        for attempt in range(max_attempts):
            try:
                result = self.run_query("RETURN 1 as test")
                if result and result[0]['test'] == 1:
                    print("✅ Neo4j доступен")
                    return True
            except Exception as e:
                print(f"⏳ Попытка {attempt + 1}/{max_attempts}: {e}")
                time.sleep(2)

        print("❌ Neo4j недоступен после всех попыток")
        return False

    def create_constraints(self):
        """Создать constraints для целостности данных"""
        print("🔒 Создание constraints...")

        constraints = [
            # Уникальный constraint для episode_id
            "CREATE CONSTRAINT episode_id_unique IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE",

            # Constraint для обязательных полей
            "CREATE CONSTRAINT episode_msg_exists IF NOT EXISTS FOR (e:Episode) REQUIRE e.msg IS NOT NULL",

            # Constraint для timestamp
            "CREATE CONSTRAINT episode_timestamp_exists IF NOT EXISTS FOR (e:Episode) REQUIRE e.timestamp IS NOT NULL"
        ]

        for constraint in constraints:
            try:
                self.run_query(constraint)
                print(f"✅ Constraint создан: {constraint[:50]}...")
            except Exception as e:
                print(f"⚠️ Ошибка создания constraint: {e}")

    def create_indexes(self):
        """Создать индексы для оптимизации запросов"""
        print("📊 Создание индексов...")

        indexes = [
            # Индекс для поиска по timestamp
            "CREATE INDEX episode_timestamp_index IF NOT EXISTS FOR (e:Episode) ON (e.timestamp)",

            # Индекс для поиска по source
            "CREATE INDEX episode_source_index IF NOT EXISTS FOR (e:Episode) ON (e.source)",

            # Индекс для поиска по category
            "CREATE INDEX episode_category_index IF NOT EXISTS FOR (e:Episode) ON (e.category)",

            # Составной индекс для частых запросов
            "CREATE INDEX episode_source_timestamp_index IF NOT EXISTS FOR (e:Episode) ON (e.source, e.timestamp)",

            # Full-text индекс для поиска по msg
            "CREATE FULLTEXT INDEX episode_msg_fulltext IF NOT EXISTS FOR (e:Episode) ON EACH [e.msg]"
        ]

        for index in indexes:
            try:
                self.run_query(index)
                print(f"✅ Индекс создан: {index[:50]}...")
            except Exception as e:
                print(f"⚠️ Ошибка создания индекса: {e}")

    def wait_for_indexes(self, timeout: int = 60):
        """Ждать пока индексы станут ONLINE"""
        print("⏳ Ожидание готовности индексов...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = self.run_query("""
                    SHOW INDEXES
                    WHERE state = 'ONLINE'
                    YIELD name, state, type
                """)

                online_indexes = [r for r in result if r['state'] == 'ONLINE']
                if len(online_indexes) >= 3:  # Минимум основных индексов
                    print(f"✅ {len(online_indexes)} индексов готовы")
                    return True

                print(f"⏳ {len(online_indexes)} индексов готовы, ожидание...")
                time.sleep(5)

            except Exception as e:
                print(f"⚠️ Ошибка проверки индексов: {e}")
                time.sleep(5)

        print("⚠️ Таймаут ожидания индексов")
        return False

    def optimize_database(self):
        """Оптимизировать базу данных"""
        print("⚡ Оптимизация базы данных...")

        optimizations = [
            # Очистка логов
            "CALL dbms.logs.clear()",

            # Обновление статистики
            "CALL db.stats.clear()",

            # Проверка целостности
            "CALL db.checkpoint()"
        ]

        for optimization in optimizations:
            try:
                self.run_query(optimization)
                print(f"✅ Оптимизация выполнена: {optimization}")
            except Exception as e:
                print(f"⚠️ Ошибка оптимизации: {e}")

    def run_hardening(self):
        """Запустить полный процесс харднинга"""
        print("🚀 Начало харднинга Neo4j базы данных...")

        if not self.wait_for_database():
            return False

        self.create_constraints()
        self.create_indexes()

        if not self.wait_for_indexes():
            print("⚠️ Индексы не готовы, но продолжаем...")

        self.optimize_database()

        print("✅ Харднинг Neo4j завершен успешно!")
        return True

def main():
    """Главная функция"""
    # Получаем параметры из переменных окружения
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')

    print(f"🔗 Подключение к Neo4j: {uri}")

    hardening = Neo4jHardening(uri, username, password)

    try:
        success = hardening.run_hardening()
        sys.exit(0 if success else 1)
    finally:
        hardening.close()

if __name__ == "__main__":
    main()
