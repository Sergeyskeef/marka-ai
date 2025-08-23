# 📝 Руководство по системе управления промптами Mark AI

## 🎯 Обзор

Новая система управления промптами Mark AI объединяет передовые исследования 2025 года для создания самообучающейся, адаптивной системы промптов. Основные инновации:

- **Agent Lineage Evolution (ALE)** - автоматическая эволюция промптов
- **Context Window Architecture (CWA)** - оптимальная структура контекста
- **Dynamic Prompt Routing** - автоматический выбор промптов
- **Behavioral Inheritance** - наследование оптимизаций между поколениями

## 🏗️ Архитектура системы

### 1. Базовые компоненты (`app/prompts/base.py`)

#### 11-слойная структура контекста:
1. **INSTRUCTIONS** - основные инструкции и роль (максимальный primacy эффект)
2. **USER_INFO** - информация о пользователе
3. **KNOWLEDGE_CONTEXT** - RAG слой для фактических знаний
4. **TASK_STATE** - состояние текущей задачи
5. **CONVERSATION_HISTORY** - история диалога
6. **EXAMPLES** - примеры для few-shot learning
7. **TOOL_DEFINITIONS** - описание доступных инструментов
8. **CONSTRAINTS** - ограничения и правила
9. **METADATA** - метаданные и настройки
10. **WORKING_MEMORY** - временная рабочая память
11. **USER_QUERY** - текущий запрос (максимальный recency эффект)

### 2. Менеджер промптов (`app/prompts/manager.py`)

Централизованное управление всеми промптами:

```python
from app.prompts import PromptManager

# Инициализация
manager = PromptManager()

# Получение промпта
prompt = await manager.get_prompt(
    name="mark_base",
    environment="production"
)

# Сохранение нового промпта
await manager.save_prompt(template)

# Продвижение между окружениями
await manager.promote_prompt(
    name="mark_base",
    from_env="development",
    to_env="production"
)
```

### 3. Динамический роутер (`app/prompts/router.py`)

Автоматический выбор оптимального промпта:

```python
from app.prompts import DynamicPromptRouter

router = DynamicPromptRouter(prompt_manager)

# Выбор промпта на основе контекста
prompt, confidence = await router.select_prompt(
    context={
        "query": "Напиши функцию сортировки",
        "domain": "technical",
        "requires_tools": True,
        "complexity": 0.7
    }
)

# Обновление награды после использования
await router.update_reward(
    prompt_name="mark_code_expert",
    context=context,
    reward=0.9  # Высокая оценка качества
)
```

### 4. Система эволюции (`app/prompts/evolution.py`)

Автоматическая эволюция промптов:

```python
from app.prompts import PromptEvolution

evolution = PromptEvolution(prompt_manager)

# Запуск мониторинга
await evolution.start_monitoring("mark_base")

# Эволюция сработает автоматически при:
# - Использовании >75% контекста
# - >15 взаимодействий
# - Снижении качества <6/10
# - Частоте ошибок >20%
# - Задержке >5 секунд
```

### 5. Архитектор контекста (`app/prompts/context_architect.py`)

Оптимизация структуры контекста:

```python
from app.prompts import ContextArchitect

architect = ContextArchitect(max_context_tokens=8192)

# Построение оптимизированного контекста
context, metrics = architect.architect_context(
    template=prompt,
    context_data={
        "user_query": "Как работает память?",
        "user_id": "123",
        "working_memory": "..."
    },
    optimization_mode="balanced"
)

# Анализ распределения внимания
analysis = architect.analyze_attention_distribution(prompt)
```

## 🚀 Использование

### Создание нового промпта

```python
from app.prompts.templates.mark_base import create_mark_base_prompt

# Базовый промпт
base_prompt = create_mark_base_prompt()

# Специализированные варианты
code_prompt = create_mark_code_expert_prompt()
learning_prompt = create_mark_learning_prompt()

# Сохранение
await manager.save_prompt(base_prompt)
```

### Интеграция с агентом

```python
# В chat_handler.py
async def process_message(message: str, user_id: str):
    # Подготовка контекста
    context = {
        "query": message,
        "user_id": user_id,
        "domain": classify_domain(message),
        "complexity": estimate_complexity(message),
        "conversation_length": len(history)
    }
    
    # Выбор промпта
    prompt, confidence = await router.select_prompt(context)
    
    # Построение оптимизированного контекста
    final_context, metrics = architect.architect_context(
        template=prompt,
        context_data={
            "user_query": message,
            "user_id": user_id,
            "working_memory": agent.working_memory,
            # ... другие данные
        }
    )
    
    # Использование промпта
    response = await agent.generate(final_context)
    
    # Оценка качества
    quality = evaluate_response(response)
    
    # Обновление награды
    await router.update_reward(
        prompt.name,
        context,
        quality
    )
    
    return response
```

## 📊 Мониторинг и аналитика

### Статистика маршрутизации

```python
stats = await router.get_routing_stats()
print(f"Всего выборов: {stats['total_selections']}")
for name, data in stats['prompts'].items():
    print(f"{name}: {data['selections']} раз, средняя награда: {data['avg_reward']}")
```

### Статистика эволюций

```python
evolution_stats = await evolution.get_evolution_stats()
print(f"Всего эволюций: {evolution_stats['total_evolutions']}")
print(f"Активных мониторов: {evolution_stats['active_monitors']}")
```

### История промптов

```python
history = await manager.get_prompt_history("mark_base", "production")
for version in history:
    print(f"Версия {version['version']}: {version['performance']}")
```

## 🔧 Настройка и оптимизация

### Параметры роутера

```python
# Более агрессивное исследование новых промптов
router = DynamicPromptRouter(
    prompt_manager,
    alpha=0.5,  # Больше исследования (по умолчанию 0.25)
    budget_aware=True  # Учитывать стоимость
)
```

### Параметры эволюции

```python
# Настройка триггеров
evolution.triggers.append(
    EvolutionTrigger(
        name="custom_metric",
        check_function=lambda stats: stats.get("custom") > threshold,
        threshold=0.8,
        description="Кастомная метрика превышена"
    )
)
```

### Оптимизация под модель

```python
# Адаптация под конкретную модель
optimized = architect.optimize_for_model(
    template=prompt,
    model_name="gpt-5-mini"  # или "claude-3", "gemini-pro"
)
```

## 📈 Лучшие практики

1. **Начните с базового промпта** и дайте системе эволюционировать
2. **Мониторьте метрики** для понимания эффективности
3. **Используйте специализированные промпты** для разных задач
4. **Доверяйте автоматической эволюции**, но проверяйте результаты
5. **Настройте триггеры** под ваши требования
6. **Используйте разные окружения** для безопасного тестирования

## 🔍 Отладка

### Логирование

```python
import logging

# Включить детальное логирование
logging.getLogger("app.prompts").setLevel(logging.DEBUG)
```

### Проверка эволюции

```python
# Посмотреть последние эволюции
for record in evolution.evolution_history[-5:]:
    print(f"Поколение {record.generation}: {record.trigger_reason}")
    print(f"Когнитивное состояние: {record.cognitive_state}/10")
```

## 🎯 Результаты

Система обеспечивает:

- **Автоматическую оптимизацию** промптов без ручного вмешательства
- **Адаптацию к пользователям** через динамическую маршрутизацию
- **Предотвращение деградации** через проактивную эволюцию
- **Оптимальное использование контекста** с учетом U-shaped attention
- **Наследование знаний** между поколениями промптов

Это позволяет Mark постоянно улучшаться и адаптироваться к меняющимся требованиям!