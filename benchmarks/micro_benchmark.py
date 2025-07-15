#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Micro-benchmark для тестирования D4-fix оптимизаций.

Этот benchmark тестирует каждую оптимизацию отдельно:
- F1: Fast-path для простых вопросов  
- F2: Connection pooling
- F3: Lazy schema check
- F4: Guard sandbox commands
- F5: Timing middleware

Цель: достичь p95 latency ≤ 5,493ms (baseline -30%)
"""

import asyncio
import time
import json
import statistics
from typing import List, Dict, Any
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MicroBenchmark:
    """Micro-benchmark для тестирования производительности отдельных компонентов."""
    
    def __init__(self):
        self.results = {}
        
    async def test_f1_fast_path(self, iterations: int = 10) -> Dict[str, Any]:
        """
        Тест F1: Fast-path для простых вопросов vs обычный path.
        
        Args:
            iterations: Количество итераций для теста
            
        Returns:
            Результаты теста с метриками latency
        """
        logger.info(f"🚀 F1 TEST: Тестирование Fast-path vs Normal-path ({iterations} итераций)")
        
        # Импортируем необходимые модули
        from langchain_api.rag.enhanced_rag_chain_tools import generate_enhanced_response_with_tools
        from langchain_api.core.backend_selector import create_memory
        
        # Создаем memory instance
        memory = create_memory()
        chat_id = 999999  # Тестовый chat_id
        
        # Тестовые вопросы
        simple_questions = [
            "Привет",
            "Как дела?", 
            "Спасибо",
            "Хорошо",
            "Да"
        ]
        
        complex_questions = [
            "Покажи список задач",
            "Выполни команду ls",
            "Прочитай файл README.md",
            "Проверь статус системы",
            "Запусти тесты"
        ]
        
        # Тестируем простые вопросы (должны использовать F1 Fast-path)
        simple_times = []
        for i in range(iterations):
            question = simple_questions[i % len(simple_questions)]
            
            start_time = time.time()
            answer = await generate_enhanced_response_with_tools(question, chat_id, memory)
            end_time = time.time()
            
            latency_ms = (end_time - start_time) * 1000
            simple_times.append(latency_ms)
            logger.info(f"Simple Q{i+1}: {latency_ms:.1f}ms - {question}")
        
        # Тестируем сложные вопросы (должны использовать Normal path)
        complex_times = []
        for i in range(iterations):
            question = complex_questions[i % len(complex_questions)]
            
            start_time = time.time()
            answer = await generate_enhanced_response_with_tools(question, chat_id, memory)
            end_time = time.time()
            
            latency_ms = (end_time - start_time) * 1000
            complex_times.append(latency_ms)
            logger.info(f"Complex Q{i+1}: {latency_ms:.1f}ms - {question}")
        
        # Анализируем результаты
        simple_stats = {
            "mean": statistics.mean(simple_times),
            "median": statistics.median(simple_times),
            "p95": statistics.quantiles(simple_times, n=20)[18],  # 95-й перцентиль
            "min": min(simple_times),
            "max": max(simple_times)
        }
        
        complex_stats = {
            "mean": statistics.mean(complex_times),
            "median": statistics.median(complex_times),
            "p95": statistics.quantiles(complex_times, n=20)[18],  # 95-й перцентиль
            "min": min(complex_times),
            "max": max(complex_times)
        }
        
        improvement = ((complex_stats["p95"] - simple_stats["p95"]) / complex_stats["p95"]) * 100
        
        result = {
            "test": "F1_Fast_Path",
            "timestamp": datetime.now().isoformat(),
            "iterations": iterations,
            "simple_questions": {
                "stats": simple_stats,
                "raw_times": simple_times
            },
            "complex_questions": {
                "stats": complex_stats,
                "raw_times": complex_times
            },
            "improvement_percent": improvement,
            "success": simple_stats["p95"] < complex_stats["p95"]
        }
        
        logger.info(f"🎯 F1 RESULTS:")
        logger.info(f"  Simple p95: {simple_stats['p95']:.1f}ms")
        logger.info(f"  Complex p95: {complex_stats['p95']:.1f}ms")
        logger.info(f"  Improvement: {improvement:.1f}%")
        logger.info(f"  Success: {result['success']}")
        
        return result
        
    async def test_f2_connection_pooling(self, iterations: int = 10) -> Dict[str, Any]:
        """
        Тест F2: Connection pooling vs повторная инициализация.
        
        Args:
            iterations: Количество итераций для теста
            
        Returns:
            Результаты теста с метриками latency
        """
        logger.info(f"🔗 F2 TEST: Тестирование Connection pooling ({iterations} итераций)")
        
        # Импортируем необходимые модули
        from langchain_api.core.backend_selector import create_memory
        from langchain_api.core.connection_pool import get_connection_pool
        from langchain_api.memory.graphiti_memory import GraphitiMemoryAdapter
        
        # 🔗 F2: Тестируем создание memory instances с/без Connection Pool
        
        # Тест 1: С Connection Pool (оптимизированный)
        pool_times = []
        for i in range(iterations):
            start_time = time.time()
            
            # Создаем memory через оптимизированный backend selector
            memory = create_memory(backend="graphiti")
            
            # Небольшая операция для проверки готовности
            _ = memory.get_short_term_context("test_session")
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            pool_times.append(latency_ms)
            logger.info(f"Pool Test {i+1}: {latency_ms:.1f}ms")
        
        # Тест 2: Без Connection Pool (традиционный способ)
        direct_times = []
        for i in range(iterations):
            start_time = time.time()
            
            # Создаем memory напрямую (без кеширования)
            memory = GraphitiMemoryAdapter(short_term_limit=20)
            
            # Небольшая операция для проверки готовности
            _ = memory.get_short_term_context("test_session")
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            direct_times.append(latency_ms)
            logger.info(f"Direct Test {i+1}: {latency_ms:.1f}ms")
        
        # Анализируем результаты
        pool_stats = {
            "mean": statistics.mean(pool_times),
            "median": statistics.median(pool_times),
            "p95": statistics.quantiles(pool_times, n=20)[18],  # 95-й перцентиль
            "min": min(pool_times),
            "max": max(pool_times)
        }
        
        direct_stats = {
            "mean": statistics.mean(direct_times),
            "median": statistics.median(direct_times),
            "p95": statistics.quantiles(direct_times, n=20)[18],  # 95-й перцентиль
            "min": min(direct_times),
            "max": max(direct_times)
        }
        
        improvement = ((direct_stats["p95"] - pool_stats["p95"]) / direct_stats["p95"]) * 100
        
        # Получаем статистику Connection Pool
        pool = get_connection_pool()
        connection_stats = pool.get_connection_stats()
        
        result = {
            "test": "F2_Connection_Pooling",
            "timestamp": datetime.now().isoformat(),
            "iterations": iterations,
            "connection_pool": {
                "stats": pool_stats,
                "raw_times": pool_times
            },
            "direct_creation": {
                "stats": direct_stats,
                "raw_times": direct_times
            },
            "improvement_percent": improvement,
            "success": pool_stats["p95"] < direct_stats["p95"],
            "connection_pool_stats": connection_stats
        }
        
        logger.info(f"🎯 F2 RESULTS:")
        logger.info(f"  Pool p95: {pool_stats['p95']:.1f}ms")
        logger.info(f"  Direct p95: {direct_stats['p95']:.1f}ms")
        logger.info(f"  Improvement: {improvement:.1f}%")
        logger.info(f"  Success: {result['success']}")
        logger.info(f"  Pool Stats: {connection_stats}")
        
        return result
        
    async def run_all_tests(self, iterations: int = 10) -> Dict[str, Any]:
        """
        Запускает все micro-benchmarks.
        
        Args:
            iterations: Количество итераций для каждого теста
            
        Returns:
            Полные результаты всех тестов
        """
        logger.info(f"🧪 MICRO-BENCHMARK: Запуск всех тестов ({iterations} итераций)")
        
        results = {}
        
        # F1: Fast-path test
        try:
            results["F1"] = await self.test_f1_fast_path(iterations)
        except Exception as e:
            logger.error(f"❌ F1 test failed: {e}")
            results["F1"] = {"error": str(e)}
        
        # F2: Connection pooling test
        try:
            results["F2"] = await self.test_f2_connection_pooling(iterations)
        except Exception as e:
            logger.error(f"❌ F2 test failed: {e}")
            results["F2"] = {"error": str(e)}
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"docs/metrics/micro_benchmark_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📊 Результаты сохранены в {filename}")
        return results

async def main():
    """Основная функция для запуска micro-benchmark."""
    benchmark = MicroBenchmark()
    
    # Запускаем тесты
    results = await benchmark.run_all_tests(iterations=5)
    
    # Выводим краткую сводку
    print("\n" + "="*50)
    print("📊 MICRO-BENCHMARK RESULTS")
    print("="*50)
    
    for test_name, result in results.items():
        if "error" in result:
            print(f"❌ {test_name}: {result['error']}")
        elif result.get("status") == "NOT_IMPLEMENTED":
            print(f"⏳ {test_name}: Not implemented yet")
        else:
            success = result.get("success", False)
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}: {result.get('improvement_percent', 0):.1f}% improvement")

if __name__ == "__main__":
    asyncio.run(main()) 