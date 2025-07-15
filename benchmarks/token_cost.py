#!/usr/bin/env python3
"""
Baseline Diagnostics: Token Cost Measurement
Измеряет стоимость токенов для установления baseline перед оптимизациями Марка v2
"""

import json
import sys
import time
from pathlib import Path


def ensure_metrics_dir():
    """Создает папку docs/metrics если она не существует"""
    metrics_dir = Path("docs/metrics")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir

def estimate_token_cost(num_tests=100):
    """
    Оценивает стоимость токенов на основе типичных запросов

    Args:
        num_tests: Количество тестовых запросов для симуляции

    Returns:
        dict: Результаты оценки стоимости токенов
    """
    print(f"💰 Оценка стоимости токенов ({num_tests} симуляций)...")

    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
    except ImportError:
        print("⚠️  tiktoken не установлен, используем приблизительную оценку")
        # Примерная оценка: ~4 символа на токен для русского текста
        def count_tokens(text):
            return len(text) // 4
        enc = None

    # Типичные запросы пользователей к Марку
    typical_queries = [
        "Привет, как дела?",
        "Помоги решить задачу по программированию",
        "Объясни архитектуру системы",
        "Создай план проекта",
        "Проанализируй код",
        "Найди ошибки в логике",
        "Предложи улучшения",
        "Напиши документацию",
        "Создай техническое задание",
        "Оптимизируй производительность"
    ]

    # Типичные ответы Марка (примерные длины)
    typical_responses = [
        "Привет! У меня всё отлично, готов помочь с любыми задачами.",
        "Конечно! Для решения этой задачи нужно использовать следующий подход...",
        "Архитектура системы состоит из нескольких ключевых компонентов...",
        "Вот детальный план проекта с основными этапами и задачами...",
        "Анализируя представленный код, я вижу следующие особенности...",
        "Обнаружил несколько потенциальных проблем в логике приложения...",
        "Рекомендую следующие улучшения для повышения эффективности...",
        "Документация должна включать описание основных функций и API...",
        "Техническое задание для данного проекта должно содержать...",
        "Для оптимизации производительности предлагаю применить кэширование..."
    ]

    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(num_tests):
        # Выбираем случайный запрос и ответ
        query = typical_queries[i % len(typical_queries)]
        response = typical_responses[i % len(typical_responses)]

        if enc:
            input_tokens = len(enc.encode(query))
            output_tokens = len(enc.encode(response))
        else:
            input_tokens = len(query) // 4
            output_tokens = len(response) // 4

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        if (i + 1) % 20 == 0:
            print(f"  📝 Симуляция {i + 1}/{num_tests}: вход={input_tokens}, выход={output_tokens}")

    # Средние токены на запрос
    avg_input_tokens = total_input_tokens / num_tests
    avg_output_tokens = total_output_tokens / num_tests
    avg_total_tokens = avg_input_tokens + avg_output_tokens

    # Примерные расценки OpenAI (на момент 2025)
    # GPT-3.5-turbo: ~$0.001 за 1K input tokens, ~$0.002 за 1K output tokens
    # GPT-4: ~$0.01 за 1K input tokens, ~$0.03 за 1K output tokens

    pricing_models = {
        "gpt-3.5-turbo": {
            "input_per_1k": 0.001,
            "output_per_1k": 0.002
        },
        "gpt-4": {
            "input_per_1k": 0.01,
            "output_per_1k": 0.03
        }
    }

    cost_estimates = {}
    for model, pricing in pricing_models.items():
        input_cost_per_1k = (avg_input_tokens / 1000) * pricing["input_per_1k"]
        output_cost_per_1k = (avg_output_tokens / 1000) * pricing["output_per_1k"]
        total_cost_per_1k = input_cost_per_1k + output_cost_per_1k

        cost_estimates[model] = {
            "input_cost_per_1k_requests": round(input_cost_per_1k, 6),
            "output_cost_per_1k_requests": round(output_cost_per_1k, 6),
            "total_cost_per_1k_requests": round(total_cost_per_1k, 6)
        }

    results = {
        "avg_input_tokens_per_request": round(avg_input_tokens, 1),
        "avg_output_tokens_per_request": round(avg_output_tokens, 1),
        "avg_total_tokens_per_request": round(avg_total_tokens, 1),
        "cost_estimates_usd": cost_estimates,
        "simulated_requests": num_tests,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseline_for": "Марк v2 - цель Promptbreeder: -10% от стоимости",
        "encoding_method": "tiktoken" if enc else "approximate"
    }

    return results

def main():
    """Основная функция для запуска измерения стоимости токенов"""
    try:
        # Создаем папку для метрик
        metrics_dir = ensure_metrics_dir()

        # Измеряем стоимость токенов
        results = estimate_token_cost()

        # Сохраняем результаты
        output_file = metrics_dir / "token_cost.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Выводим результаты
        print("\n💰 РЕЗУЛЬТАТЫ ОЦЕНКИ СТОИМОСТИ ТОКЕНОВ:")
        print(f"   Средние токены на запрос: {results['avg_total_tokens_per_request']}")
        print(f"   - Входящие: {results['avg_input_tokens_per_request']}")
        print(f"   - Исходящие: {results['avg_output_tokens_per_request']}")

        print("\n📊 СТОИМОСТЬ ЗА 1000 ЗАПРОСОВ:")
        for model, costs in results['cost_estimates_usd'].items():
            print(f"   {model}: ${costs['total_cost_per_1k_requests']:.6f}")

        # Цель для Promptbreeder
        gpt4_cost = results['cost_estimates_usd']['gpt-4']['total_cost_per_1k_requests']
        target_cost = gpt4_cost * 0.9  # -10%

        print("\n🎯 ЦЕЛЬ ДЛЯ PROMPTBREEDER (Q3):")
        print(f"   Текущий baseline (GPT-4): ${gpt4_cost:.6f}/1K запросов")
        print(f"   Цель -10%: <${target_cost:.6f}/1K запросов")
        print(f"   Результаты сохранены: {output_file}")

        return results

    except Exception as e:
        print(f"❌ Ошибка при измерении стоимости токенов: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
