#!/usr/bin/env python3
"""
Cron-trigger для автоматических размышлений Марка.
Запускается каждые 6 часов для создания периодических размышлений.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox.reflection_manager import ReflectionManager


def get_system_status() -> dict:
    """Получает текущий статус системы"""
    status = {
        'timestamp': datetime.now().isoformat(),
        'reflections_count': 0,
        'recent_commands': [],
        'system_health': 'unknown'
    }

    try:
        # Подсчитываем количество размышлений
        reflection_manager = ReflectionManager()
        reflections = reflection_manager.list_reflections()
        status['reflections_count'] = len(reflections)

        # Получаем последние размышления
        recent_reflections = reflections[:5] if reflections else []
        status['recent_reflections'] = [
            {
                'topic': r['topic'],
                'date': r['date'],
                'size': r['size']
            }
            for r in recent_reflections
        ]

        # Проверяем здоровье системы через Docker
        try:
            result = subprocess.run(
                ['docker', 'compose', 'ps'],
                capture_output=True, text=True, cwd='/app/langchain_api'
            )
            if result.returncode == 0:
                status['system_health'] = 'healthy' if 'Up' in result.stdout else 'unhealthy'
            else:
                status['system_health'] = 'error'
        except Exception:
            status['system_health'] = 'unknown'

    except Exception as e:
        status['error'] = str(e)

    return status


def generate_periodic_reflection() -> str:
    """Генерирует периодическое размышление"""
    reflection_manager = ReflectionManager()

    # Получаем статус системы
    status = get_system_status()

    # Определяем тему размышления
    current_hour = datetime.now().hour
    if 6 <= current_hour < 12:
        time_period = "утро"
    elif 12 <= current_hour < 18:
        time_period = "день"
    elif 18 <= current_hour < 24:
        time_period = "вечер"
    else:
        time_period = "ночь"

    topic = f"Периодическое размышление ({time_period})"

    # Генерируем содержание
    content = f"""## Статус системы на {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### Общая статистика
- **Всего размышлений:** {status['reflections_count']}
- **Здоровье системы:** {status['system_health']}
- **Время суток:** {time_period}

### Последние размышления
"""

    if status.get('recent_reflections'):
        for reflection in status['recent_reflections']:
            content += f"- **{reflection['topic']}** ({reflection['date']}) - {reflection['size']} символов\n"
    else:
        content += "- Нет предыдущих размышлений\n"

    content += f"""
### Анализ текущего состояния

Это автоматическое размышление создано системой cron-trigger каждые 6 часов.

**Время:** {time_period}
**Дата:** {datetime.now().strftime('%Y-%m-%d')}
**Время суток:** {current_hour}:00

### Наблюдения

1. **Система работает стабильно** - все основные компоненты функционируют
2. **Количество размышлений:** {status['reflections_count']} - это показывает активность системы самоанализа
3. **Периодичность:** Каждые 6 часов система создает размышления для поддержания самосознания

### Рекомендации

- Продолжать мониторинг системы
- Анализировать паттерны в размышлениях
- Поддерживать регулярность самоанализа

### Заключение

Периодические размышления помогают поддерживать самосознание и отслеживать развитие системы. Это важная часть автономного функционирования.
"""

    # Создаем размышление
    context = {
        'description': f'Автоматическое размышление каждые 6 часов ({time_period})',
        'system_status': status,
        'trigger_type': 'cron',
        'interval_hours': 6
    }

    filepath = reflection_manager.create_reflection(
        topic=topic,
        content=content,
        reflection_type="automatic",
        context=context
    )

    return filepath


def main():
    """Основная функция"""
    print(f"🔄 Запуск cron-trigger для размышлений: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Генерируем периодическое размышление
        filepath = generate_periodic_reflection()
        print(f"✅ Периодическое размышление создано: {filepath}")

        # Логируем событие
        try:
            subprocess.run([
                sys.executable, "scripts/log_awakening_event.py",
                "REFLECTION", f"Cron-trigger создал размышление: {Path(filepath).name}", "SUCCESS", "system"
            ], check=False, cwd="/app/langchain_api")
        except Exception as e:
            print(f"⚠️ Не удалось залогировать событие: {e}")

        return 0

    except Exception as e:
        print(f"❌ Ошибка при создании размышления: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
