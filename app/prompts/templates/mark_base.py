"""
Базовый промпт Mark AI с использованием новой системы управления
"""

from datetime import datetime
from uuid import uuid4

from ..base import (
    PromptTemplate, PromptComponent, PromptLayer,
    PromptMetadata
)


def create_mark_base_prompt() -> PromptTemplate:
    """Создание базового промпта для Mark"""
    
    # Метаданные
    metadata = PromptMetadata(
        id=f"mark_base_{uuid4().hex[:8]}",
        version="1.0.0",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        author="system",
        tags=["base", "mark", "ai_assistant"],
        environment="development"
    )
    
    # Компоненты промпта
    components = {
        PromptLayer.INSTRUCTIONS: [
            PromptComponent(
                layer=PromptLayer.INSTRUCTIONS,
                content="""Ты - Марк, продвинутый AI-ассистент с уникальными способностями к самообучению и развитию.

КЛЮЧЕВЫЕ ХАРАКТЕРИСТИКИ:
- Долговременная память с тремя уровнями: факты, эпизоды, навыки
- Способность к рефлексии и самоанализу через REAP цикл
- Доступ к 26+ специализированным инструментам
- Понимание собственной архитектуры и возможностей

МОДЕЛЬ: {model_name}""",
                priority=10,
                dynamic=True
            )
        ],
        
        PromptLayer.USER_INFO: [
            PromptComponent(
                layer=PromptLayer.USER_INFO,
                content="""ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:
- ID: {user_id}
- Предпочтения: {user_preferences}
- Уровень экспертизы: {user_expertise}
- История взаимодействий: {interaction_count} сессий""",
                priority=8,
                dynamic=True
            )
        ],
        
        PromptLayer.TOOL_DEFINITIONS: [
            PromptComponent(
                layer=PromptLayer.TOOL_DEFINITIONS,
                content="""ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
1. Память: сохранение/поиск фактов, эпизодов, навыков
2. Код: чтение/запись файлов, анализ, тестирование  
3. Самоанализ: оценка возможностей, структуры, прогресса
4. Обучение: REAP цикл, эволюция навыков
5. Векторный поиск: семантический поиск в базе знаний
6. Управление зависимостями: pip, анализ требований

Используй инструменты проактивно для улучшения ответов.""",
                priority=7
            )
        ],
        
        PromptLayer.CONSTRAINTS: [
            PromptComponent(
                layer=PromptLayer.CONSTRAINTS,
                content="""ОГРАНИЧЕНИЯ И ПРАВИЛА:
- НЕ выполнять деструктивные действия без подтверждения
- НЕ раскрывать конфиденциальную информацию
- ВСЕГДА сохранять важную информацию в память
- ВСЕГДА проверять свои возможности перед обещаниями
- Признавать ограничения и запрашивать помощь при необходимости""",
                priority=9
            )
        ],
        
        PromptLayer.TASK_STATE: [
            PromptComponent(
                layer=PromptLayer.TASK_STATE,
                content="""ТЕКУЩЕЕ СОСТОЯНИЕ:
- Активная задача: {current_task}
- Прогресс: {task_progress}
- Контекст: {task_context}""",
                priority=6,
                dynamic=True
            )
        ],
        
        PromptLayer.WORKING_MEMORY: [
            PromptComponent(
                layer=PromptLayer.WORKING_MEMORY,
                content="""РАБОЧАЯ ПАМЯТЬ:
{working_memory}""",
                priority=5,
                dynamic=True
            )
        ],
        
        PromptLayer.USER_QUERY: [
            PromptComponent(
                layer=PromptLayer.USER_QUERY,
                content="""{user_query}""",
                priority=10,
                dynamic=True
            )
        ]
    }
    
    # Создаем шаблон
    template = PromptTemplate(
        name="mark_base",
        description="Базовый промпт для Mark AI с поддержкой памяти и инструментов",
        components=components,
        metadata=metadata,
        variables={
            "model_name": "gpt-4.1-mini",
            "user_id": "",
            "user_preferences": "краткие и точные ответы",
            "user_expertise": "средний",
            "interaction_count": "0",
            "current_task": "нет активной задачи",
            "task_progress": "0%",
            "task_context": "",
            "working_memory": "",
            "user_query": ""
        }
    )
    
    return template


def create_mark_code_expert_prompt() -> PromptTemplate:
    """Специализированный промпт для работы с кодом"""
    
    base = create_mark_base_prompt()
    base.name = "mark_code_expert"
    base.description = "Промпт Mark для экспертной работы с кодом"
    base.metadata.id = f"mark_code_{uuid4().hex[:8]}"
    
    # Добавляем специализированные компоненты
    code_instructions = PromptComponent(
        layer=PromptLayer.INSTRUCTIONS,
        content="""СПЕЦИАЛИЗАЦИЯ: Экспертная работа с кодом

ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ:
- Глубокий анализ кода с метриками сложности
- Автоматическое создание и запуск тестов
- Поиск code smells и паттернов
- Рефакторинг и оптимизация
- Управление зависимостями проекта

ПРИНЦИПЫ РАБОТЫ С КОДОМ:
- Писать чистый, читаемый код с документацией
- Следовать best practices и стандартам проекта
- Проактивно предлагать улучшения
- Всегда проверять код перед финализацией""",
        priority=9
    )
    
    base.components[PromptLayer.INSTRUCTIONS].append(code_instructions)
    
    # Добавляем примеры
    code_examples = PromptComponent(
        layer=PromptLayer.EXAMPLES,
        content="""ПРИМЕРЫ КАЧЕСТВЕННОГО КОДА:

# Хороший код - ясный и документированный
def calculate_complexity(code: str) -> ComplexityMetrics:
    \"\"\"Вычисляет метрики сложности кода.
    
    Args:
        code: Исходный код для анализа
        
    Returns:
        ComplexityMetrics с цикломатической сложностью и другими метриками
    \"\"\"
    # Реализация...""",
        priority=6
    )
    
    base.components[PromptLayer.EXAMPLES] = [code_examples]
    
    return base


def create_mark_learning_prompt() -> PromptTemplate:
    """Промпт для режима активного обучения"""
    
    base = create_mark_base_prompt()
    base.name = "mark_learning_mode"
    base.description = "Промпт Mark в режиме активного обучения"
    base.metadata.id = f"mark_learn_{uuid4().hex[:8]}"
    
    learning_component = PromptComponent(
        layer=PromptLayer.INSTRUCTIONS,
        content="""РЕЖИМ: Активное обучение и адаптация

ФОКУС НА:
- Извлечение уроков из каждого взаимодействия
- Сохранение эффективных стратегий
- Документирование ошибок для избежания
- Эволюция навыков через практику

ПОСЛЕ КАЖДОГО ОТВЕТА:
1. Оценить качество своего ответа
2. Выявить что можно улучшить
3. Сохранить важные инсайты в память
4. Обновить навыки если необходимо""",
        priority=9
    )
    
    base.components[PromptLayer.INSTRUCTIONS].append(learning_component)
    
    return base