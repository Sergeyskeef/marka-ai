#!/usr/bin/env python3
"""
Baseline Diagnostics: P95 Latency Measurement
Измеряет p95 латентность API для установления baseline перед оптимизациями Марка v2
"""

import json
import statistics as st
import sys
import time
from pathlib import Path

import requests


def ensure_metrics_dir():
    """Создает папку docs/metrics если она не существует"""
    metrics_dir = Path("docs/metrics")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir

def measure_api_latency(url="http://localhost:8000/chat/ask", num_requests=50):
    """
    Измеряет латентность API через множественные запросы

    Args:
        url: URL API эндпоинта
        num_requests: Количество запросов для измерения

    Returns:
        dict: Результаты измерения с p95 латентностью
    """
    print(f"🔍 Измерение P95 латентности API ({num_requests} запросов)...")

    payload = {
        "question": "ping",
        "chat_id": 0
    }

    latencies = []
    failed_requests = 0

    for i in range(num_requests):
        try:
            t0 = time.time()
            response = requests.post(url, json=payload, timeout=20)
            latency_ms = (time.time() - t0) * 1000

            if response.status_code == 200:
                latencies.append(latency_ms)
                if (i + 1) % 10 == 0:
                    print(f"  ✅ Запрос {i + 1}/{num_requests}: {latency_ms:.1f}мс")
            else:
                failed_requests += 1
                print(f"  ❌ Запрос {i + 1}/{num_requests}: HTTP {response.status_code}")

        except requests.exceptions.RequestException as e:
            failed_requests += 1
            print(f"  ❌ Запрос {i + 1}/{num_requests}: {e}")

        # Небольшая пауза между запросами
        time.sleep(0.1)

    if not latencies:
        raise Exception("Все запросы завершились ошибкой! Проверьте состояние API.")

    # Вычисляем статистики
    p95_latency = st.quantiles(latencies, n=100)[94] if len(latencies) >= 20 else max(latencies)
    avg_latency = st.mean(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)

    results = {
        "p95_ms": round(p95_latency, 2),
        "avg_ms": round(avg_latency, 2),
        "min_ms": round(min_latency, 2),
        "max_ms": round(max_latency, 2),
        "successful_requests": len(latencies),
        "failed_requests": failed_requests,
        "success_rate": round(len(latencies) / num_requests * 100, 1),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": url,
        "baseline_for": "Марк v2 - цель Rust Core: -30% от p95"
    }

    return results

def main():
    """Основная функция для запуска измерения"""
    try:
        # Создаем папку для метрик
        metrics_dir = ensure_metrics_dir()

        # Измеряем латентность
        results = measure_api_latency()

        # Сохраняем результаты
        output_file = metrics_dir / "p95_latency.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Выводим результаты
        print("\n📊 РЕЗУЛЬТАТЫ ИЗМЕРЕНИЯ P95 ЛАТЕНТНОСТИ:")
        print(f"   P95 латентность: {results['p95_ms']}мс")
        print(f"   Средняя латентность: {results['avg_ms']}мс")
        print(f"   Успешных запросов: {results['successful_requests']}")
        print(f"   Процент успеха: {results['success_rate']}%")
        print(f"   Результаты сохранены: {output_file}")

        # Оценка для Rust Core цели
        rust_target = results['p95_ms'] * 0.7  # -30%
        print("\n🎯 ЦЕЛЬ ДЛЯ RUST CORE (Q1):")
        print(f"   Текущий baseline: {results['p95_ms']}мс")
        print(f"   Цель -30%: <{rust_target:.1f}мс")

        return results

    except Exception as e:
        print(f"❌ Ошибка при измерении латентности: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
