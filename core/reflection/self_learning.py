import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .reasoning_chains import ReasoningSystem

logger = logging.getLogger(__name__)

@dataclass
class LearningPattern:
    """Паттерн обучения"""
    id: str
    pattern_type: str
    context: dict[str, Any]
    confidence: float
    created_at: datetime
    last_used: datetime
    usage_count: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "context": self.context,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "usage_count": self.usage_count,
            "success_rate": self.success_rate
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'LearningPattern':
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['last_used'] = datetime.fromisoformat(data['last_used'])
        return cls(**data)

class SelfLearningSystem:
    """
    Система самообучения для анализа и использования паттернов.
    """

    def __init__(self, reasoning_system: ReasoningSystem):
        """
        Инициализация системы самообучения.

        Args:
            reasoning_system: Система рассуждений для анализа
        """
        self.reasoning_system = reasoning_system
        self.patterns: dict[str, LearningPattern] = {}
        self.learning_history: list[dict[str, Any]] = []

    def add_pattern(self, pattern: LearningPattern) -> None:
        """
        Добавление нового паттерна обучения.

        Args:
            pattern: Паттерн для добавления
        """
        self.patterns[pattern.id] = pattern

    def analyze_patterns(self, chain_id: str) -> list[LearningPattern]:
        """Анализирует цепочку рассуждений и извлекает паттерны"""
        chain = self.reasoning_system.get_chain(chain_id)
        if not chain:
            return []

        patterns = []
        for step in chain.steps:
            # Анализируем контекст шага
            context_analysis = self.reasoning_system.analyze_context(step.context)

            # Создаем паттерн на основе анализа
            pattern = LearningPattern(
                id=f"pattern_{len(self.patterns)}",
                pattern_type=self._determine_pattern_type(context_analysis),
                context=step.context,
                confidence=step.confidence,
                created_at=datetime.now(),
                last_used=datetime.now()
            )
            patterns.append(pattern)
            self.patterns[pattern.id] = pattern

        return patterns

    def _determine_pattern_type(self, context_analysis: dict[str, Any]) -> str:
        """Определяет тип паттерна на основе анализа контекста"""
        if context_analysis["has_code"]:
            return "code_pattern"
        elif context_analysis["has_text"]:
            return "text_pattern"
        else:
            return "general_pattern"

    def record_learning_event(self, event_type: str, context: dict[str, Any],
                            success: bool, patterns_used: list[str]) -> None:
        """
        Записывает событие обучения.

        Args:
            event_type: Тип события
            context: Контекст события
            success: Успешность события
            patterns_used: Список использованных паттернов
        """
        event = {
            "event_type": event_type,
            "context": context,
            "success": success,
            "patterns_used": patterns_used,
            "timestamp": datetime.now().isoformat()
        }
        self.learning_history.append(event)

        # Обновляем статистику использованных паттернов
        for pattern_id in patterns_used:
            self.update_pattern_stats(pattern_id, success)

    def update_pattern(self, pattern_id: str, success: bool) -> None:
        """Обновляет статистику использования паттерна"""
        pattern = self.patterns.get(pattern_id)
        if pattern:
            pattern.usage_count += 1
            pattern.last_used = datetime.now()

            # Обновляем успешность
            current_success = pattern.success_rate * (pattern.usage_count - 1)
            new_success = current_success + (1 if success else 0)
            pattern.success_rate = new_success / pattern.usage_count

    def get_relevant_patterns(self, context: dict[str, Any]) -> list[LearningPattern]:
        """
        Получение релевантных паттернов для контекста.

        Args:
            context: Контекст для поиска

        Returns:
            Список релевантных паттернов
        """
        relevant_patterns = []

        for pattern in self.patterns.values():
            # Проверяем совпадение типов контекста
            # Если в контексте есть 'code', то ищем code_pattern
            if 'code' in context and pattern.pattern_type == 'code_pattern':
                relevant_patterns.append(pattern)
            # Если в контексте есть 'text', то ищем text_pattern
            elif 'text' in context and pattern.pattern_type == 'text_pattern':
                relevant_patterns.append(pattern)
            # Если в контексте есть 'type', то ищем паттерн с таким же типом
            elif 'type' in context and pattern.pattern_type == context['type']:
                relevant_patterns.append(pattern)
            # Если нет специфичных полей, ищем general_pattern
            elif not any(key in context for key in ['code', 'text', 'type']) and pattern.pattern_type == 'general_pattern':
                relevant_patterns.append(pattern)

        # Сортируем по уверенности
        relevant_patterns.sort(key=lambda x: x.confidence, reverse=True)

        return relevant_patterns

    def update_pattern_stats(self, pattern_id: str, success: bool) -> None:
        """
        Обновление статистики паттерна.

        Args:
            pattern_id: ID паттерна
            success: Успешность использования
        """
        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            pattern.usage_count += 1
            pattern.last_used = datetime.utcnow()

            # Обновляем показатель успешности
            if pattern.usage_count == 1:
                pattern.success_rate = 1.0 if success else 0.0
            else:
                pattern.success_rate = (
                    (pattern.success_rate * (pattern.usage_count - 1) + (1.0 if success else 0.0))
                    / pattern.usage_count
                )

    def get_learning_stats(self) -> dict[str, Any]:
        """
        Получение статистики обучения.

        Returns:
            Словарь со статистикой
        """
        total_patterns = len(self.patterns)
        successful_patterns = sum(1 for p in self.patterns.values() if p.success_rate > 0.7)
        total_events = len(self.learning_history)

        # Вычисляем среднюю успешность по паттернам, а не по событиям
        if total_patterns > 0:
            average_success_rate = sum(p.success_rate for p in self.patterns.values()) / total_patterns
        else:
            average_success_rate = 0.0

        # Получаем наиболее используемые паттерны
        most_used_patterns = sorted(
            self.patterns.values(),
            key=lambda x: x.usage_count,
            reverse=True
        )

        return {
            'total_patterns': total_patterns,
            'successful_patterns': successful_patterns,
            'success_rate': successful_patterns / total_patterns if total_patterns > 0 else 0.0,
            'total_events': total_events,
            'average_success_rate': average_success_rate,
            'most_used_patterns': most_used_patterns
        }

    def save_state(self, filepath: str) -> None:
        """
        Сохранение состояния системы.

        Args:
            filepath: Путь к файлу
        """
        state = {
            'patterns': {
                pattern_id: {
                    'id': pattern.id,
                    'pattern_type': pattern.pattern_type,
                    'context': pattern.context,
                    'confidence': pattern.confidence,
                    'created_at': pattern.created_at.isoformat(),
                    'last_used': pattern.last_used.isoformat(),
                    'usage_count': pattern.usage_count,
                    'success_rate': pattern.success_rate
                }
                for pattern_id, pattern in self.patterns.items()
            },
            'learning_history': self.learning_history
        }

        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)

    @classmethod
    def load_state(cls, filepath: str, reasoning_system: ReasoningSystem) -> 'SelfLearningSystem':
        """
        Загрузка состояния системы.

        Args:
            filepath: Путь к файлу
            reasoning_system: Система рассуждений

        Returns:
            Загруженная система
        """
        with open(filepath) as f:
            state = json.load(f)

        learning_system = cls(reasoning_system)

        # Загружаем паттерны
        for pattern_id, pattern_data in state['patterns'].items():
            pattern = LearningPattern.from_dict(pattern_data)
            learning_system.patterns[pattern_id] = pattern

        # Загружаем историю
        learning_system.learning_history = state['learning_history']

        return learning_system
