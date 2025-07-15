#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F2 Connection Pool Benchmark v3 - Исправленная версия

Тестирует производительность connection pooling в реалистичных сценариях:
1. Множественные запросы к одному клиенту
2. Параллельные операции (уменьшенная нагрузка)
3. Долгосрочное использование
4. Правильная очистка ресурсов
"""

import time
import statistics
import logging
import gc
from typing import List, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BenchmarkResult:
    """Результат benchmark теста"""
    test_name: str
    pooled_time_ms: float
    direct_time_ms: float
    improvement_percent: float
    samples: int
    description: str

class F2ConnectionPoolBenchmarkV3:
    """
    Исправленный benchmark для тестирования F2 Connection Pool оптимизации.
    
    Основные улучшения:
    - Правильная очистка ресурсов
    - Уменьшенная нагрузка для параллельных тестов
    - Более реалистичные сценарии
    - Исправленные API вызовы
    """
    
    def __init__(self, num_samples: int = 5):
        self.num_samples = num_samples
        self.results: List[BenchmarkResult] = []
    
    def benchmark_repeated_operations(self) -> BenchmarkResult:
        """Тестирует множественные операции с одним клиентом"""
        logger.info("🔧 Тестируем множественные операции...")
        
        pooled_times = []
        direct_times = []
        
        for i in range(self.num_samples):
            logger.info(f"  Sample {i+1}/{self.num_samples}")
            
            # Небольшая задержка между тестами
            if i > 0:
                time.sleep(0.2)
            
            # Тест pooled операций
            start_time = time.time()
            memory = None
            try:
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                memory = MultiLayerMemory()  # Использует pooled клиент
                
                # Выполняем 5 операций подряд (уменьшили нагрузку)
                for j in range(5):
                    memory.add_to_short_term(f"test_session_{i}_{j}", "user", f"Тестовое сообщение {j}")
                    context = memory.get_short_term_context(f"test_session_{i}_{j}")
                
                pooled_time = (time.time() - start_time) * 1000
                pooled_times.append(pooled_time)
                logger.info(f"    Pooled (5 ops): {pooled_time:.2f}ms")
            except Exception as e:
                logger.error(f"    Pooled error: {e}")
                continue
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                except:
                    pass
                gc.collect()  # Принудительная очистка памяти
            
            # Тест direct операций
            start_time = time.time()
            memory = None
            direct_memory_manager = None
            try:
                from langchain_api.memory.memory_manager import MemoryManager
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                
                # Создаем direct MemoryManager
                direct_memory_manager = MemoryManager()
                memory = MultiLayerMemory(memory_manager=direct_memory_manager)
                
                # Выполняем 5 операций подряд (уменьшили нагрузку)
                for j in range(5):
                    memory.add_to_short_term(f"test_session_{i}_{j}", "user", f"Тестовое сообщение {j}")
                    context = memory.get_short_term_context(f"test_session_{i}_{j}")
                
                direct_time = (time.time() - start_time) * 1000
                direct_times.append(direct_time)
                logger.info(f"    Direct (5 ops): {direct_time:.2f}ms")
            except Exception as e:
                logger.error(f"    Direct error: {e}")
                continue
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                    if direct_memory_manager:
                        del direct_memory_manager
                except:
                    pass
                gc.collect()  # Принудительная очистка памяти
        
        if not pooled_times or not direct_times:
            logger.error("❌ Не удалось получить результаты теста")
            return BenchmarkResult("Repeated Operations", 0, 0, 0, 0, "5 операций подряд")
        
        avg_pooled = statistics.mean(pooled_times)
        avg_direct = statistics.mean(direct_times)
        improvement = ((avg_direct - avg_pooled) / avg_direct) * 100
        
        result = BenchmarkResult(
            test_name="Repeated Operations",
            pooled_time_ms=avg_pooled,
            direct_time_ms=avg_direct,
            improvement_percent=improvement,
            samples=min(len(pooled_times), len(direct_times)),
            description="5 операций подряд с одним клиентом"
        )
        
        logger.info(f"✅ Repeated Operations: pooled={avg_pooled:.2f}ms, direct={avg_direct:.2f}ms, improvement={improvement:.1f}%")
        return result
    
    def benchmark_parallel_operations(self) -> BenchmarkResult:
        """Тестирует параллельные операции (уменьшенная нагрузка)"""
        logger.info("🔧 Тестируем параллельные операции...")
        
        def pooled_operation(session_id: int) -> float:
            """Одна операция с pooled клиентом"""
            start_time = time.time()
            memory = None
            try:
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                memory = MultiLayerMemory()
                memory.add_to_short_term(f"parallel_session_{session_id}", "user", f"Параллельное сообщение {session_id}")
                context = memory.get_short_term_context(f"parallel_session_{session_id}")
                return (time.time() - start_time) * 1000
            except Exception as e:
                logger.error(f"Pooled parallel error: {e}")
                return 0
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                except:
                    pass
        
        def direct_operation(session_id: int) -> float:
            """Одна операция с direct клиентом"""
            start_time = time.time()
            memory = None
            direct_memory_manager = None
            try:
                from langchain_api.memory.memory_manager import MemoryManager
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                direct_memory_manager = MemoryManager()
                memory = MultiLayerMemory(memory_manager=direct_memory_manager)
                memory.add_to_short_term(f"parallel_session_{session_id}", "user", f"Параллельное сообщение {session_id}")
                context = memory.get_short_term_context(f"parallel_session_{session_id}")
                return (time.time() - start_time) * 1000
            except Exception as e:
                logger.error(f"Direct parallel error: {e}")
                return 0
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                    if direct_memory_manager:
                        del direct_memory_manager
                except:
                    pass
        
        # Тест параллельных pooled операций (уменьшенная нагрузка)
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=2) as executor:  # Уменьшили количество потоков
            pooled_futures = [executor.submit(pooled_operation, i) for i in range(3)]  # Уменьшили количество операций
            pooled_results = [future.result() for future in as_completed(pooled_futures)]
        pooled_total_time = (time.time() - start_time) * 1000
        
        # Небольшая пауза между тестами
        time.sleep(0.5)
        
        # Тест параллельных direct операций (уменьшенная нагрузка)
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=2) as executor:  # Уменьшили количество потоков
            direct_futures = [executor.submit(direct_operation, i) for i in range(3)]  # Уменьшили количество операций
            direct_results = [future.result() for future in as_completed(direct_futures)]
        direct_total_time = (time.time() - start_time) * 1000
        
        improvement = ((direct_total_time - pooled_total_time) / direct_total_time) * 100
        
        result = BenchmarkResult(
            test_name="Parallel Operations",
            pooled_time_ms=pooled_total_time,
            direct_time_ms=direct_total_time,
            improvement_percent=improvement,
            samples=1,
            description="3 параллельные операции (2 потока)"
        )
        
        logger.info(f"✅ Parallel Operations: pooled={pooled_total_time:.2f}ms, direct={direct_total_time:.2f}ms, improvement={improvement:.1f}%")
        return result
    
    def benchmark_memory_retrieval(self) -> BenchmarkResult:
        """Тестирует операции поиска в памяти"""
        logger.info("🔧 Тестируем поиск в памяти...")
        
        pooled_times = []
        direct_times = []
        
        for i in range(self.num_samples):
            logger.info(f"  Sample {i+1}/{self.num_samples}")
            
            # Небольшая задержка между тестами
            if i > 0:
                time.sleep(0.2)
            
            # Тест pooled поиска
            start_time = time.time()
            memory = None
            try:
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                memory = MultiLayerMemory()
                
                # Добавляем данные и ищем
                memory.add_to_short_term(f"search_session_{i}", "user", "Поисковый запрос")
                memory.add_to_short_term(f"search_session_{i}", "assistant", "Ответ на запрос")
                
                # Выполняем поиск
                context = memory.get_short_term_context(f"search_session_{i}")
                facts = memory.get_user_facts()
                
                pooled_time = (time.time() - start_time) * 1000
                pooled_times.append(pooled_time)
                logger.info(f"    Pooled search: {pooled_time:.2f}ms")
            except Exception as e:
                logger.error(f"    Pooled search error: {e}")
                continue
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                except:
                    pass
                gc.collect()  # Принудительная очистка памяти
            
            # Тест direct поиска
            start_time = time.time()
            memory = None
            direct_memory_manager = None
            try:
                from langchain_api.memory.memory_manager import MemoryManager
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                
                direct_memory_manager = MemoryManager()
                memory = MultiLayerMemory(memory_manager=direct_memory_manager)
                
                # Добавляем данные и ищем
                memory.add_to_short_term(f"search_session_{i}", "user", "Поисковый запрос")
                memory.add_to_short_term(f"search_session_{i}", "assistant", "Ответ на запрос")
                
                # Выполняем поиск
                context = memory.get_short_term_context(f"search_session_{i}")
                facts = memory.get_user_facts()
                
                direct_time = (time.time() - start_time) * 1000
                direct_times.append(direct_time)
                logger.info(f"    Direct search: {direct_time:.2f}ms")
            except Exception as e:
                logger.error(f"    Direct search error: {e}")
                continue
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                    if direct_memory_manager:
                        del direct_memory_manager
                except:
                    pass
                gc.collect()  # Принудительная очистка памяти
        
        if not pooled_times or not direct_times:
            logger.error("❌ Не удалось получить результаты теста")
            return BenchmarkResult("Memory Retrieval", 0, 0, 0, 0, "Поиск в памяти")
        
        avg_pooled = statistics.mean(pooled_times)
        avg_direct = statistics.mean(direct_times)
        improvement = ((avg_direct - avg_pooled) / avg_direct) * 100
        
        result = BenchmarkResult(
            test_name="Memory Retrieval",
            pooled_time_ms=avg_pooled,
            direct_time_ms=avg_direct,
            improvement_percent=improvement,
            samples=min(len(pooled_times), len(direct_times)),
            description="Поиск и извлечение данных из памяти"
        )
        
        logger.info(f"✅ Memory Retrieval: pooled={avg_pooled:.2f}ms, direct={avg_direct:.2f}ms, improvement={improvement:.1f}%")
        return result
    
    def run_all_benchmarks(self) -> List[BenchmarkResult]:
        """Запускает все benchmark тесты"""
        logger.info("🚀 Запускаем F2 Connection Pool Benchmark v3...")
        
        self.results = []
        
        # Тест 1: Множественные операции
        result1 = self.benchmark_repeated_operations()
        self.results.append(result1)
        
        # Пауза между тестами
        time.sleep(1.0)
        
        # Тест 2: Параллельные операции
        result2 = self.benchmark_parallel_operations()
        self.results.append(result2)
        
        # Пауза между тестами
        time.sleep(1.0)
        
        # Тест 3: Поиск в памяти
        result3 = self.benchmark_memory_retrieval()
        self.results.append(result3)
        
        return self.results
    
    def print_summary(self):
        """Выводит сводку результатов"""
        if not self.results:
            logger.error("❌ Нет результатов для вывода")
            return
        
        logger.info("\n" + "="*70)
        logger.info("📊 F2 CONNECTION POOL BENCHMARK v3 RESULTS")
        logger.info("="*70)
        
        total_improvement = 0
        valid_results = 0
        
        for result in self.results:
            if result.samples > 0:
                logger.info(f"\n🔧 {result.test_name}:")
                logger.info(f"   Description: {result.description}")
                logger.info(f"   Pooled:   {result.pooled_time_ms:.2f}ms")
                logger.info(f"   Direct:   {result.direct_time_ms:.2f}ms")
                logger.info(f"   Samples:  {result.samples}")
                logger.info(f"   Improvement: {result.improvement_percent:+.1f}%")
                
                if result.improvement_percent > 0:
                    logger.info(f"   ✅ УЛУЧШЕНИЕ")
                else:
                    logger.info(f"   ❌ ДЕГРАДАЦИЯ")
                
                total_improvement += result.improvement_percent
                valid_results += 1
        
        if valid_results > 0:
            avg_improvement = total_improvement / valid_results
            logger.info(f"\n🎯 СРЕДНЕЕ УЛУЧШЕНИЕ: {avg_improvement:+.1f}%")
            
            if avg_improvement > 0:
                logger.info("✅ F2 Connection Pool показывает УЛУЧШЕНИЕ производительности")
            else:
                logger.warning("⚠️ F2 Connection Pool показывает ДЕГРАДАЦИЮ производительности")
        else:
            logger.error("❌ Нет валидных результатов")

def main():
    """Главная функция для запуска benchmark"""
    benchmark = F2ConnectionPoolBenchmarkV3(num_samples=3)  # Уменьшили количество сэмплов
    results = benchmark.run_all_benchmarks()
    benchmark.print_summary()
    
    return results

if __name__ == "__main__":
    main() 