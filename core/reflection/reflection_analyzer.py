import logging
from datetime import datetime, timedelta
from typing import Any
from collections import Counter, defaultdict
import statistics

logger = logging.getLogger(__name__)

class ReflectionAnalyzer:
    """
    Класс для анализа выполненных действий и генерации инсайтов.

    Attributes:
        action_history (List[Dict[str, Any]]): История выполненных действий
        insights (List[Dict[str, Any]]): Список сгенерированных инсайтов
    """

    def __init__(self):
        self.action_history: list[dict[str, Any]] = []
        self.insights: list[dict[str, Any]] = []
        self.patterns: dict[str, list[dict]] = defaultdict(list)
        self.performance_metrics: dict[str, list[float]] = defaultdict(list)

    def add_action(self, action: dict[str, Any]) -> None:
        """
        Добавляет действие в историю.

        Args:
            action (Dict[str, Any]): Словарь с информацией о действии
        """
        action['timestamp'] = datetime.now()
        action['timestamp_str'] = action['timestamp'].isoformat()
        self.action_history.append(action)
        
        # Сохраняем метрики производительности
        if 'duration' in action:
            self.performance_metrics[action.get('type', 'unknown')].append(action['duration'])
        
        logger.debug(f"Added action to history: {action}")

    def analyze_actions(self) -> list[dict[str, Any]]:
        """
        Анализирует историю действий и генерирует инсайты.

        Returns:
            List[Dict[str, Any]]: Список сгенерированных инсайтов
        """
        insights = []

        # Группировка действий по типам
        action_types = {}
        for action in self.action_history:
            action_type = action.get('type', 'unknown')
            if action_type not in action_types:
                action_types[action_type] = []
            action_types[action_type].append(action)

        # Анализ паттернов в действиях
        for action_type, actions in action_types.items():
            if len(actions) > 1:
                # Анализ последовательности действий
                sequence_insight = self._analyze_sequence(actions)
                if sequence_insight:
                    insights.append(sequence_insight)

                # Анализ эффективности действий
                efficiency_insight = self._analyze_efficiency(actions)
                if efficiency_insight:
                    insights.append(efficiency_insight)
                
                # Анализ ошибок
                error_insight = self._analyze_errors(actions)
                if error_insight:
                    insights.append(error_insight)
                
                # Анализ временных паттернов
                time_insight = self._analyze_time_patterns(actions)
                if time_insight:
                    insights.append(time_insight)

        self.insights.extend(insights)
        return insights

    def _analyze_sequence(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """
        Анализирует последовательность действий.

        Args:
            actions (List[Dict[str, Any]]): Список действий одного типа

        Returns:
            Optional[Dict[str, Any]]: Инсайт о последовательности действий или None
        """
        if len(actions) < 3:
            return None

        # Анализируем частоту последовательных действий
        sequences = []
        for i in range(len(actions) - 1):
            if i + 1 < len(actions):
                time_diff = (actions[i+1]['timestamp'] - actions[i]['timestamp']).total_seconds()
                if time_diff < 60:  # Действия в пределах минуты
                    sequences.append({
                        'action1': actions[i],
                        'action2': actions[i+1],
                        'time_diff': time_diff
                    })
        
        if len(sequences) >= 3:
            # Находим повторяющиеся паттерны
            pattern_counts = Counter()
            for seq in sequences:
                pattern_key = f"{seq['action1'].get('subtype', '')}->{seq['action2'].get('subtype', '')}"
                pattern_counts[pattern_key] += 1
            
            most_common = pattern_counts.most_common(1)
            if most_common and most_common[0][1] >= 3:
                return {
                    'type': 'sequence_analysis',
                    'action_type': actions[0].get('type'),
                    'insight': f'Обнаружена частая последовательность действий: {most_common[0][0]} (повторяется {most_common[0][1]} раз)',
                    'pattern': most_common[0][0],
                    'frequency': most_common[0][1],
                    'recommendation': 'Рассмотрите возможность автоматизации этой последовательности',
                    'timestamp': datetime.now().isoformat()
                }
        
        return None

    def _analyze_efficiency(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """
        Анализирует эффективность действий.

        Args:
            actions (List[Dict[str, Any]]): Список действий одного типа

        Returns:
            Optional[Dict[str, Any]]: Инсайт об эффективности действий или None
        """
        if len(actions) < 3:
            return None

        # Собираем метрики производительности
        durations = [a.get('duration', 0) for a in actions if 'duration' in a]
        error_count = sum(1 for a in actions if a.get('status') == 'error')
        success_count = sum(1 for a in actions if a.get('status') == 'success')
        
        if not durations:
            return None
        
        # Вычисляем статистику
        avg_duration = statistics.mean(durations)
        median_duration = statistics.median(durations)
        
        # Определяем тренд производительности
        if len(durations) >= 5:
            first_half = durations[:len(durations)//2]
            second_half = durations[len(durations)//2:]
            
            avg_first = statistics.mean(first_half)
            avg_second = statistics.mean(second_half)
            
            performance_trend = "улучшается" if avg_second < avg_first else "ухудшается"
            trend_percentage = abs((avg_second - avg_first) / avg_first * 100)
            
            if trend_percentage > 20:  # Значительное изменение
                return {
                    'type': 'efficiency_analysis',
                    'action_type': actions[0].get('type'),
                    'insight': f'Производительность {performance_trend} на {trend_percentage:.1f}%',
                    'metrics': {
                        'average_duration': avg_duration,
                        'median_duration': median_duration,
                        'error_rate': error_count / len(actions) if actions else 0,
                        'success_rate': success_count / len(actions) if actions else 0,
                        'trend': performance_trend,
                        'trend_percentage': trend_percentage
                    },
                    'recommendation': 'Исследуйте причины изменения производительности' if performance_trend == "ухудшается" else 'Продолжайте применять успешные оптимизации',
                    'timestamp': datetime.now().isoformat()
                }
        
        # Анализ общей эффективности
        if error_count > len(actions) * 0.3:  # Более 30% ошибок
            return {
                'type': 'efficiency_analysis',
                'action_type': actions[0].get('type'),
                'insight': f'Высокий уровень ошибок: {error_count}/{len(actions)} ({error_count/len(actions)*100:.1f}%)',
                'metrics': {
                    'error_rate': error_count / len(actions),
                    'success_rate': success_count / len(actions),
                    'average_duration': avg_duration
                },
                'recommendation': 'Необходимо исследовать и устранить причины частых ошибок',
                'timestamp': datetime.now().isoformat()
            }
        
        return None

    def _analyze_errors(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """
        Анализирует ошибки в действиях.
        
        Args:
            actions: Список действий для анализа
            
        Returns:
            Инсайт об ошибках или None
        """
        errors = [a for a in actions if a.get('status') == 'error' or a.get('error')]
        
        if len(errors) < 2:
            return None
        
        # Группируем ошибки по типам
        error_types = Counter()
        error_messages = []
        
        for error in errors:
            error_type = error.get('error_type', 'unknown')
            error_types[error_type] += 1
            if 'error_message' in error:
                error_messages.append(error['error_message'])
        
        most_common_error = error_types.most_common(1)[0]
        
        return {
            'type': 'error_analysis',
            'action_type': actions[0].get('type'),
            'insight': f'Наиболее частая ошибка: {most_common_error[0]} ({most_common_error[1]} раз)',
            'error_statistics': dict(error_types),
            'total_errors': len(errors),
            'error_rate': len(errors) / len(actions),
            'recommendation': 'Реализуйте обработку наиболее частых типов ошибок',
            'timestamp': datetime.now().isoformat()
        }

    def _analyze_time_patterns(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """
        Анализирует временные паттерны действий.
        
        Args:
            actions: Список действий для анализа
            
        Returns:
            Инсайт о временных паттернах или None
        """
        if len(actions) < 5:
            return None
        
        # Анализируем распределение по времени суток
        hour_distribution = Counter()
        weekday_distribution = Counter()
        
        for action in actions:
            timestamp = action['timestamp']
            hour_distribution[timestamp.hour] += 1
            weekday_distribution[timestamp.weekday()] += 1
        
        # Находим пиковые часы
        peak_hours = hour_distribution.most_common(3)
        peak_days = weekday_distribution.most_common(2)
        
        if peak_hours[0][1] > len(actions) * 0.3:  # Более 30% действий в определенный час
            weekday_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
            peak_day_names = [weekday_names[day[0]] for day in peak_days]
            
            return {
                'type': 'time_pattern_analysis',
                'action_type': actions[0].get('type'),
                'insight': f'Пиковая активность в {peak_hours[0][0]}:00-{peak_hours[0][0]+1}:00 ({peak_hours[0][1]} действий)',
                'patterns': {
                    'peak_hours': [f"{h[0]}:00" for h in peak_hours],
                    'peak_days': peak_day_names,
                    'hour_distribution': dict(hour_distribution),
                    'weekday_distribution': dict(weekday_distribution)
                },
                'recommendation': 'Учитывайте временные паттерны при планировании ресурсов',
                'timestamp': datetime.now().isoformat()
            }
        
        return None

    def get_insights(self) -> list[dict[str, Any]]:
        """
        Возвращает список всех сгенерированных инсайтов.

        Returns:
            List[Dict[str, Any]]: Список инсайтов
        """
        return self.insights
    
    def get_summary(self) -> dict[str, Any]:
        """
        Возвращает сводку по всем действиям и инсайтам.
        
        Returns:
            Dict с общей статистикой
        """
        total_actions = len(self.action_history)
        action_types = Counter(a.get('type', 'unknown') for a in self.action_history)
        
        success_count = sum(1 for a in self.action_history if a.get('status') == 'success')
        error_count = sum(1 for a in self.action_history if a.get('status') == 'error')
        
        return {
            'total_actions': total_actions,
            'action_types': dict(action_types),
            'success_rate': success_count / total_actions if total_actions > 0 else 0,
            'error_rate': error_count / total_actions if total_actions > 0 else 0,
            'total_insights': len(self.insights),
            'insight_types': Counter(i['type'] for i in self.insights),
            'last_analysis': datetime.now().isoformat()
        }
