#!/usr/bin/env python3
"""
Нагрузочное тестирование для Mark AI
Используется Locust для симуляции нагрузки
"""
import os
import sys
import json
import random
from locust import HttpUser, task, between, events
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging
import gevent

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Тестовые данные
TEST_MESSAGES = [
    "Привет! Как дела?",
    "Расскажи о своих возможностях",
    "Помоги мне написать код на Python",
    "Что ты помнишь о нашем предыдущем разговоре?",
    "Проанализируй этот код: def hello(): print('world')",
    "Найди ошибку в коде",
    "Создай тест для функции",
    "Объясни, как работает async/await",
    "Какая погода сегодня?",
    "Напиши документацию для API"
]

class MarkAIUser(HttpUser):
    wait_time = between(1, 3)  # Пауза между запросами 1-3 секунды
    
    def on_start(self):
        """Инициализация перед началом тестов"""
        self.headers = {
            "Content-Type": "application/json"
        }
        self.user_id = f"test_user_{random.randint(1000, 9999)}"
    
    @task(3)
    def test_chat_simple(self):
        """Простой чат запрос"""
        message = random.choice(TEST_MESSAGES)
        payload = {
            "message": message,
            "user_id": self.user_id
        }
        
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "response" in data:
                        response.success()
                    else:
                        response.failure("No response field in JSON")
                except Exception as e:
                    response.failure(f"Failed to parse JSON: {e}")
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(1)
    def test_chat_with_tools(self):
        """Чат с использованием инструментов"""
        payload = {
            "message": "Проверь файлы в директории /workspace",
            "user_id": self.user_id
        }
        
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(2)
    def test_prompts_api(self):
        """Тестирование API промптов"""
        with self.client.get(
            "/api/prompts",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(1)
    def test_health_check(self):
        """Health check эндпоинт"""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


def run_load_test(host="http://localhost:8001", users=10, spawn_rate=2, run_time=60):
    """
    Запуск нагрузочного теста
    
    Args:
        host: URL сервера
        users: Количество виртуальных пользователей
        spawn_rate: Скорость создания пользователей в секунду
        run_time: Время выполнения теста в секундах
    """
    # Настройка логирования
    setup_logging("INFO")
    
    # Создание окружения
    env = Environment(user_classes=[MarkAIUser], host=host)
    env.create_local_runner()
    
    # Запуск веб-интерфейса (опционально)
    # env.create_web_ui("127.0.0.1", 8089)
    
    # Запуск теста
    env.runner.start(users, spawn_rate=spawn_rate)
    
    # Запуск сбора статистики
    gevent.spawn(stats_printer(env.stats))
    gevent.spawn(stats_history, env.runner)
    
    # Ожидание завершения
    gevent.spawn_later(run_time, lambda: env.runner.quit())
    
    # Ожидание остановки
    env.runner.greenlet.join()
    
    # Сохранение результатов
    results = {
        "total_requests": env.stats.total.num_requests,
        "total_failures": env.stats.total.num_failures,
        "avg_response_time": env.stats.total.avg_response_time,
        "min_response_time": env.stats.total.min_response_time,
        "max_response_time": env.stats.total.max_response_time,
        "rps": env.stats.total.current_rps,
        "failures_per_sec": env.stats.total.current_fail_per_sec,
        "users": users,
        "spawn_rate": spawn_rate,
        "run_time": run_time
    }
    
    # Детальная статистика по эндпоинтам
    results["endpoints"] = {}
    for name, entry in env.stats.entries.items():
        if name != "Aggregated":
            results["endpoints"][name] = {
                "requests": entry.num_requests,
                "failures": entry.num_failures,
                "avg_time": entry.avg_response_time,
                "min_time": entry.min_response_time,
                "max_time": entry.max_response_time
            }
    
    # Сохранение в файл
    with open("/workspace/load_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Вывод результатов
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ")
    print("="*60)
    print(f"Всего запросов: {results['total_requests']}")
    print(f"Неудачных запросов: {results['total_failures']}")
    print(f"Процент успеха: {(1 - results['total_failures']/max(results['total_requests'], 1)) * 100:.1f}%")
    print(f"Среднее время ответа: {results['avg_response_time']:.0f}ms")
    print(f"RPS: {results['rps']:.1f}")
    
    # Проверка производительности
    success = True
    if results['avg_response_time'] > 1000:  # Больше 1 секунды
        print("\n⚠️  ПРЕДУПРЕЖДЕНИЕ: Среднее время ответа превышает 1 секунду!")
        success = False
    
    if results['total_failures'] / max(results['total_requests'], 1) > 0.01:  # Больше 1% ошибок
        print("\n❌ ОШИБКА: Процент неудачных запросов превышает 1%!")
        success = False
    
    if results['rps'] < 10:  # Меньше 10 RPS
        print("\n⚠️  ПРЕДУПРЕЖДЕНИЕ: RPS меньше 10!")
        success = False
    
    if success:
        print("\n✅ Тест производительности пройден успешно!")
    else:
        print("\n❌ Тест производительности не пройден!")
    
    return success


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Нагрузочное тестирование Mark AI")
    parser.add_argument("--host", default="http://localhost:8001", help="URL сервера")
    parser.add_argument("--users", type=int, default=10, help="Количество пользователей")
    parser.add_argument("--spawn-rate", type=int, default=2, help="Скорость создания пользователей/сек")
    parser.add_argument("--time", type=int, default=60, help="Время теста в секундах")
    
    args = parser.parse_args()
    
    success = run_load_test(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.time
    )
    
    sys.exit(0 if success else 1)