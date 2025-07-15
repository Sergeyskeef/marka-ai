#!/usr/bin/env python3
"""
F2 Connection Pool Benchmark v4 - Корректная версия

Тестирует производительность connection pooling в РЕАЛЬНЫХ сценариях использования:
1. Последовательные запросы (как в старой системе)
2. Множественные операции в рамках одной сессии
3. Поиск и извлечение данных
4. Правильное сравнение со старой системой
"""

import gc
import logging
import statistics
import time
from dataclasses import dataclass

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

class F2ConnectionPoolBenchmarkV4:
    """
    Корректный benchmark для тестирования F2 Connection Pool оптимизации.

    Основные принципы:
    - Тестируем РЕАЛЬНЫЕ сценарии использования
    - Сравниваем с тем, как работала старая система
    - Не создаем искусственных параллельных нагрузок
    - Правильная очистка ресурсов
    """

    def __init__(self, num_samples: int = 5):
        self.num_samples = num_samples
        self.results: list[BenchmarkResult] = []

    def benchmark_sequential_requests(self) -> BenchmarkResult:
        """
        Тестирует последовательные запросы - как в старой системе.
        Каждый запрос создает новый MemoryManager (как было раньше).
        """
        logger.info("🔧 Тестируем последовательные запросы (старая система)...")

        pooled_times = []
        direct_times = []

        for i in range(self.num_samples):
            logger.info(f"  Sample {i+1}/{self.num_samples}")

            # Небольшая задержка между тестами
            if i > 0:
                time.sleep(0.2)

            # Тест pooled операций (новая система)
            start_time = time.time()
            memory = None
            try:
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                memory = MultiLayerMemory()  # Использует pooled клиент

                # Одна операция (как в реальном использовании)
                memory.add_to_short_term(f"seq_session_{i}", "user", f"Последовательный запрос {i}")
                memory.get_short_term_context(f"seq_session_{i}")

                pooled_time = (time.time() - start_time) * 1000
                pooled_times.append(pooled_time)
                logger.info(f"    Pooled (1 op): {pooled_time:.2f}ms")
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
                gc.collect()

            # Тест direct операций (старая система)
            start_time = time.time()
            memory = None
            direct_memory_manager = None
            try:
                from langchain_api.memory.memory_manager import MemoryManager
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory

                # Создаем новый MemoryManager (как в старой системе)
                direct_memory_manager = MemoryManager()
                memory = MultiLayerMemory(memory_manager=direct_memory_manager)

                # Одна операция (как в реальном использовании)
                memory.add_to_short_term(f"seq_session_{i}", "user", f"Последовательный запрос {i}")
                memory.get_short_term_context(f"seq_session_{i}")

                direct_time = (time.time() - start_time) * 1000
                direct_times.append(direct_time)
                logger.info(f"    Direct (1 op): {direct_time:.2f}ms")
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
                gc.collect()

        if not pooled_times or not direct_times:
            logger.error("❌ Не удалось получить результаты теста")
            return BenchmarkResult("Sequential Requests", 0, 0, 0, 0, "Последовательные запросы")

        avg_pooled = statistics.mean(pooled_times)
        avg_direct = statistics.mean(direct_times)
        improvement = ((avg_direct - avg_pooled) / avg_direct) * 100

        result = BenchmarkResult(
            test_name="Sequential Requests",
            pooled_time_ms=avg_pooled,
            direct_time_ms=avg_direct,
            improvement_percent=improvement,
            samples=min(len(pooled_times), len(direct_times)),
            description="Последовательные запросы (как в старой системе)"
        )

        logger.info(f"✅ Sequential Requests: pooled={avg_pooled:.2f}ms, direct={avg_direct:.2f}ms, improvement={improvement:.1f}%")
        return result

    def benchmark_session_operations(self) -> BenchmarkResult:
        """
        Тестирует множественные операции в рамках одной сессии.
        Это более реалистичный сценарий - пользователь делает несколько запросов.
        """
        logger.info("🔧 Тестируем операции в рамках сессии...")

        pooled_times = []
        direct_times = []

        for i in range(self.num_samples):
            logger.info(f"  Sample {i+1}/{self.num_samples}")

            # Небольшая задержка между тестами
            if i > 0:
                time.sleep(0.2)

            # Тест pooled операций в сессии
            start_time = time.time()
            memory = None
            try:
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory
                memory = MultiLayerMemory()  # Использует pooled клиент

                # Несколько операций в рамках одной сессии
                session_id = f"session_{i}"
                for j in range(3):  # 3 операции в сессии
                    memory.add_to_short_term(session_id, "user", f"Сообщение {j} в сессии {i}")
                    memory.add_to_short_term(session_id, "assistant", f"Ответ {j} в сессии {i}")

                # Получаем контекст сессии
                memory.get_short_term_context(session_id)

                pooled_time = (time.time() - start_time) * 1000
                pooled_times.append(pooled_time)
                logger.info(f"    Pooled (session): {pooled_time:.2f}ms")
            except Exception as e:
                logger.error(f"    Pooled session error: {e}")
                continue
            finally:
                # Очищаем ресурсы
                try:
                    if memory:
                        del memory
                except:
                    pass
                gc.collect()

            # Тест direct операций в сессии
            start_time = time.time()
            memory = None
            direct_memory_manager = None
            try:
                from langchain_api.memory.memory_manager import MemoryManager
                from langchain_api.memory.multi_layer_memory import MultiLayerMemory

                # Создаем новый MemoryManager
                direct_memory_manager = MemoryManager()
                memory = MultiLayerMemory(memory_manager=direct_memory_manager)

                # Несколько операций в рамках одной сессии
                session_id = f"session_{i}"
                for j in range(3):  # 3 операции в сессии
                    memory.add_to_short_term(session_id, "user", f"Сообщение {j} в сессии {i}")
                    memory.add_to_short_term(session_id, "assistant", f"Ответ {j} в сессии {i}")

                # Получаем контекст сессии
                memory.get_short_term_context(session_id)

                direct_time = (time.time() - start_time) * 1000
                direct_times.append(direct_time)
                logger.info(f"    Direct (session): {direct_time:.2f}ms")
            except Exception as e:
                logger.error(f"    Direct session error: {e}")
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
                gc.collect()

        if not pooled_times or not direct_times:
            logger.error("❌ Не удалось получить результаты теста")
            return BenchmarkResult("Session Operations", 0, 0, 0, 0, "Операции в сессии")

        avg_pooled = statistics.mean(pooled_times)
        avg_direct = statistics.mean(direct_times)
        improvement = ((avg_direct - avg_pooled) / avg_direct) * 100

        result = BenchmarkResult(
            test_name="Session Operations",
            pooled_time_ms=avg_pooled,
            direct_time_ms=avg_direct,
            improvement_percent=improvement,
            samples=min(len(pooled_times), len(direct_times)),
            description="Множественные операции в рамках одной сессии"
        )

        logger.info(f"✅ Session Operations: pooled={avg_pooled:.2f}ms, direct={avg_direct:.2f}ms, improvement={improvement:.1f}%")
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
                memory.get_short_term_context(f"search_session_{i}")
                memory.get_user_facts()

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
                gc.collect()

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
                memory.get_short_term_context(f"search_session_{i}")
                memory.get_user_facts()

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
                gc.collect()

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

    def run_all_benchmarks(self) -> list[BenchmarkResult]:
        """Запускает все benchmark тесты"""
        logger.info("🚀 Запускаем F2 Connection Pool Benchmark v4 (корректная версия)...")

        self.results = []

        # Тест 1: Последовательные запросы (как в старой системе)
        result1 = self.benchmark_sequential_requests()
        self.results.append(result1)

        # Пауза между тестами
        time.sleep(1.0)

        # Тест 2: Операции в сессии
        result2 = self.benchmark_session_operations()
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
        logger.info("📊 F2 CONNECTION POOL BENCHMARK v4 RESULTS")
        logger.info("="*70)
        logger.info("🔧 Корректное сравнение со старой системой")
        logger.info("="*70)

        total_improvement = 0
        valid_results = 0

        for result in self.results:
            if result.samples > 0:
                logger.info(f"\n🔧 {result.test_name}:")
                logger.info(f"   Description: {result.description}")
                logger.info(f"   Pooled (F2): {result.pooled_time_ms:.2f}ms")
                logger.info(f"   Direct (old): {result.direct_time_ms:.2f}ms")
                logger.info(f"   Samples:  {result.samples}")
                logger.info(f"   Improvement: {result.improvement_percent:+.1f}%")

                if result.improvement_percent > 0:
                    logger.info("   ✅ УЛУЧШЕНИЕ")
                else:
                    logger.info("   ❌ ДЕГРАДАЦИЯ")

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
    benchmark = F2ConnectionPoolBenchmarkV4(num_samples=5)
    results = benchmark.run_all_benchmarks()
    benchmark.print_summary()

    return results

if __name__ == "__main__":
    main()
