import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class InsightType(Enum):
    EFFICIENCY = "efficiency"
    PATTERN = "pattern"
    RECOMMENDATION = "recommendation"
    OPTIMIZATION = "optimization"

@dataclass
class Insight:
    type: InsightType
    title: str
    description: str
    confidence: float
    timestamp: datetime
    context: dict[str, Any]
    recommendations: list[str]

class ReflectionSystem:
    """
    Расширенная система рефлексии для анализа действий и генерации инсайтов.

    Attributes:
        action_history (List[Dict[str, Any]]): История выполненных действий
        insights (List[Insight]): Список сгенерированных инсайтов
        metrics (Dict[str, float]): Метрики эффективности
    """

    def __init__(self):
        self.action_history: list[dict[str, Any]] = []
        self.insights: list[Insight] = []
        self.metrics: dict[str, float] = {}

    def add_action(self, action: dict[str, Any]) -> None:
        """
        Добавляет действие в историю и обновляет метрики.

        Args:
            action (Dict[str, Any]): Словарь с информацией о действии
        """
        action['timestamp'] = datetime.now().isoformat()
        self.action_history.append(action)
        self._update_metrics(action)
        logger.debug(f"Added action to history: {action}")

    def _update_metrics(self, action: dict[str, Any]) -> None:
        """
        Обновляет метрики на основе нового действия.

        Args:
            action (Dict[str, Any]): Информация о действии
        """
        action_type = action.get('type', 'unknown')
        duration = action.get('duration', 0)
        success = action.get('success', False)

        if action_type not in self.metrics:
            self.metrics[action_type] = {
                'total_count': 0,
                'success_count': 0,
                'total_duration': 0,
                'avg_duration': 0
            }

        metrics = self.metrics[action_type]
        metrics['total_count'] += 1
        if success:
            metrics['success_count'] += 1
        metrics['total_duration'] += duration
        metrics['avg_duration'] = metrics['total_duration'] / metrics['total_count']

    def analyze_actions(self) -> list[Insight]:
        """
        Анализирует историю действий и генерирует инсайты.

        Returns:
            List[Insight]: Список сгенерированных инсайтов
        """
        insights = []

        # Анализ эффективности
        efficiency_insights = self._analyze_efficiency()
        insights.extend(efficiency_insights)

        # Анализ паттернов
        pattern_insights = self._analyze_patterns()
        insights.extend(pattern_insights)

        # Генерация рекомендаций
        recommendation_insights = self._generate_recommendations()
        insights.extend(recommendation_insights)

        self.insights.extend(insights)
        return insights

    def _analyze_efficiency(self) -> list[Insight]:
        """
        Анализирует эффективность действий.

        Returns:
            List[Insight]: Список инсайтов об эффективности
        """
        insights = []

        for action_type, metrics in self.metrics.items():
            if metrics['total_count'] < 2:
                continue

            success_rate = metrics['success_count'] / metrics['total_count']
            avg_duration = metrics['avg_duration']

            # Находим максимальную длительность для этого типа действий
            max_duration = max(
                action.get('duration', 0)
                for action in self.action_history
                if action.get('type') == action_type
            )

            if success_rate < 0.7:
                insights.append(Insight(
                    type=InsightType.EFFICIENCY,
                    title=f"Низкая эффективность действий типа {action_type}",
                    description=f"Успешность выполнения составляет {success_rate:.2%}",
                    confidence=0.8,
                    timestamp=datetime.now(),
                    context={'action_type': action_type, 'metrics': metrics},
                    recommendations=[
                        f"Рассмотрите возможность оптимизации действий типа {action_type}",
                        "Проверьте условия успешного выполнения",
                        "Проанализируйте причины неудачных попыток"
                    ]
                ))

            if max_duration > 1000:  # Проверяем максимальную длительность
                insights.append(Insight(
                    type=InsightType.OPTIMIZATION,
                    title=f"Длительное выполнение действий типа {action_type}",
                    description=f"Максимальное время выполнения: {max_duration:.2f}мс, среднее: {avg_duration:.2f}мс",
                    confidence=0.7,
                    timestamp=datetime.now(),
                    context={'action_type': action_type, 'metrics': metrics, 'max_duration': max_duration},
                    recommendations=[
                        f"Оптимизируйте производительность действий типа {action_type}",
                        "Рассмотрите возможность асинхронного выполнения",
                        "Проверьте наличие узких мест в коде"
                    ]
                ))

        return insights

    def _analyze_patterns(self) -> list[Insight]:
        """
        Анализирует паттерны в действиях.

        Returns:
            List[Insight]: Список инсайтов о паттернах
        """
        insights = []

        # Группировка действий по типам
        action_types = {}
        for action in self.action_history:
            action_type = action.get('type', 'unknown')
            if action_type not in action_types:
                action_types[action_type] = []
            action_types[action_type].append(action)

        # Анализ последовательностей
        for action_type, actions in action_types.items():
            if len(actions) > 2:
                # Поиск повторяющихся последовательностей
                sequences = self._find_repeating_sequences(actions)
                if sequences:
                    insights.append(Insight(
                        type=InsightType.PATTERN,
                        title=f"Обнаружены повторяющиеся последовательности в {action_type}",
                        description=f"Найдено {len(sequences)} повторяющихся паттернов",
                        confidence=0.9,
                        timestamp=datetime.now(),
                        context={'action_type': action_type, 'sequences': sequences},
                        recommendations=[
                            "Рассмотрите возможность автоматизации повторяющихся действий",
                            "Создайте шаблоны для часто используемых последовательностей",
                            "Документируйте обнаруженные паттерны"
                        ]
                    ))

        return insights

    def _find_repeating_sequences(self, actions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """
        Находит повторяющиеся последовательности действий.

        Args:
            actions (List[Dict[str, Any]]): Список действий

        Returns:
            List[List[Dict[str, Any]]]: Список повторяющихся последовательностей
        """
        sequences = []
        min_sequence_length = 2
        max_sequence_length = 5

        def _action_key(action: dict[str, Any]) -> str:
            """Создает ключ для сравнения действий."""
            return f"{action.get('type', '')}:{action.get('success', False)}"

        def _sequence_key(sequence: list[dict[str, Any]]) -> str:
            """Создает ключ для сравнения последовательностей."""
            return "->".join(_action_key(action) for action in sequence)

        for length in range(min_sequence_length, min(max_sequence_length + 1, len(actions))):
            for i in range(len(actions) - length + 1):
                sequence = actions[i:i + length]
                sequence_key = _sequence_key(sequence)

                # Проверяем, встречается ли эта последовательность еще раз
                for j in range(i + 1, len(actions) - length + 1):
                    other_sequence = actions[j:j + length]
                    if _sequence_key(other_sequence) == sequence_key:
                        sequences.append(sequence)
                        break

        return sequences

    def _generate_recommendations(self) -> list[Insight]:
        """
        Генерирует рекомендации на основе анализа.

        Returns:
            List[Insight]: Список инсайтов с рекомендациями
        """
        insights = []

        # Анализ успешности действий
        success_rates = {
            action_type: metrics['success_count'] / metrics['total_count']
            for action_type, metrics in self.metrics.items()
            if metrics['total_count'] > 0
        }

        # Находим действия с низкой успешностью
        low_success_actions = {
            action_type: rate
            for action_type, rate in success_rates.items()
            if rate < 0.7
        }

        if low_success_actions:
            insights.append(Insight(
                type=InsightType.RECOMMENDATION,
                title="Рекомендации по улучшению успешности действий",
                description="Обнаружены действия с низкой успешностью выполнения",
                confidence=0.8,
                timestamp=datetime.now(),
                context={'low_success_actions': low_success_actions},
                recommendations=[
                    f"Улучшите обработку ошибок для действий типа {action_type}"
                    for action_type in low_success_actions.keys()
                ]
            ))

        return insights

    def get_insights(self) -> list[Insight]:
        """
        Возвращает список всех сгенерированных инсайтов.

        Returns:
            List[Insight]: Список инсайтов
        """
        return self.insights
