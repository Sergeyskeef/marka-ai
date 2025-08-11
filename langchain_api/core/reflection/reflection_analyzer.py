import logging
from datetime import datetime, timedelta
from typing import Any
from collections import Counter
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

    def add_action(self, action: dict[str, Any]) -> None:
        """
        Добавляет действие в историю.

        Args:
            action (Dict[str, Any]): Словарь с информацией о действии
        """
        action['timestamp'] = datetime.now().isoformat()
        self.action_history.append(action)
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
        for actions in action_types.values():
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
        Анализирует последовательность действий для выявления паттернов.
        """
        if len(actions) < 3:
            return None

        # Конвертируем строковые timestamp в datetime если нужно
        for action in actions:
            if isinstance(action.get('timestamp'), str):
                action['timestamp'] = datetime.fromisoformat(action['timestamp'])

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
        Анализирует эффективность действий на основе времени выполнения.
        """
        if len(actions) < 2:
            return None

        # Собираем время выполнения для каждого действия
        execution_times = []
        for action in actions:
            if 'execution_time' in action and action['execution_time'] is not None:
                execution_times.append(action['execution_time'])
        
        if len(execution_times) < 2:
            return None
        
        # Вычисляем статистику
        avg_time = statistics.mean(execution_times)
        median_time = statistics.median(execution_times)
        
        # Если есть значительная разница между средним и медианой
        if avg_time > median_time * 1.5:
            slow_actions = [t for t in execution_times if t > median_time * 2]
            if len(slow_actions) >= 2:
                return {
                    'type': 'efficiency_analysis',
                    'action_type': actions[0].get('type'),
                    'insight': f'Обнаружены медленные операции: {len(slow_actions)} действий выполняются значительно дольше среднего',
                    'avg_time': round(avg_time, 2),
                    'median_time': round(median_time, 2),
                    'slow_count': len(slow_actions),
                    'recommendation': 'Исследуйте причины медленного выполнения и оптимизируйте',
                    'timestamp': datetime.now().isoformat()
                }
        
        return None

    def _analyze_errors(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """
        Анализирует паттерны ошибок в действиях.
        """
        errors = [a for a in actions if not a.get('success', True) or a.get('error')]
        
        if len(errors) < 2:
            return None
        
        # Группируем ошибки по типам
        error_types = Counter()
        for error in errors:
            error_msg = error.get('error', 'unknown')
            # Простая категоризация ошибок
            if 'timeout' in str(error_msg).lower():
                error_types['timeout'] += 1
            elif 'connection' in str(error_msg).lower():
                error_types['connection'] += 1
            elif 'permission' in str(error_msg).lower():
                error_types['permission'] += 1
            else:
                error_types['other'] += 1
        
        if error_types:
            most_common_error = error_types.most_common(1)[0]
            return {
                'type': 'error_analysis',
                'action_type': actions[0].get('type'),
                'insight': f'Частые ошибки типа "{most_common_error[0]}" ({most_common_error[1]} раз)',
                'error_distribution': dict(error_types),
                'total_errors': len(errors),
                'recommendation': f'Требуется исправить проблемы с {most_common_error[0]}',
                'timestamp': datetime.now().isoformat()
            }
        
        return None

    def _analyze_time_patterns(self, actions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """
        Анализирует временные паттерны выполнения действий.
        """
        if len(actions) < 5:
            return None
        
        # Конвертируем timestamp если нужно
        for action in actions:
            if isinstance(action.get('timestamp'), str):
                action['timestamp'] = datetime.fromisoformat(action['timestamp'])
        
        # Группируем действия по часам
        hourly_counts = Counter()
        for action in actions:
            if 'timestamp' in action:
                hour = action['timestamp'].hour
                hourly_counts[hour] += 1
        
        if hourly_counts:
            peak_hour = hourly_counts.most_common(1)[0]
            if peak_hour[1] >= 3:
                return {
                    'type': 'time_pattern_analysis',
                    'action_type': actions[0].get('type'),
                    'insight': f'Пиковая активность в {peak_hour[0]}:00 ({peak_hour[1]} действий)',
                    'hourly_distribution': dict(hourly_counts),
                    'peak_hour': peak_hour[0],
                    'peak_count': peak_hour[1],
                    'recommendation': 'Учитывайте пиковые часы при планировании ресурсоемких операций',
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
    
    def save_insights_to_memory(self, memory_manager) -> None:
        """
        Сохраняет инсайты в память через memory_manager.
        
        Args:
            memory_manager: Менеджер памяти для сохранения
        """
        for insight in self.insights:
            try:
                # Форматируем инсайт для сохранения
                insight_text = f"Reflection insight ({insight['type']}): {insight['insight']}"
                
                # Добавляем метаданные
                metadata = {
                    "type": "reflection_insight",
                    "insight_type": insight['type'],
                    "action_type": insight.get('action_type'),
                    "recommendation": insight.get('recommendation'),
                    "timestamp": insight['timestamp']
                }
                
                # Добавляем дополнительные данные в зависимости от типа
                if insight['type'] == 'sequence_analysis':
                    metadata['pattern'] = insight.get('pattern')
                    metadata['frequency'] = insight.get('frequency')
                elif insight['type'] == 'efficiency_analysis':
                    metadata['avg_time'] = insight.get('avg_time')
                    metadata['median_time'] = insight.get('median_time')
                elif insight['type'] == 'error_analysis':
                    metadata['error_distribution'] = insight.get('error_distribution')
                    metadata['total_errors'] = insight.get('total_errors')
                elif insight['type'] == 'time_pattern_analysis':
                    metadata['peak_hour'] = insight.get('peak_hour')
                    metadata['peak_count'] = insight.get('peak_count')
                
                # Сохраняем в память
                memory_manager.save(insight_text, metadata=metadata)
                logger.info(f"Сохранен инсайт в память: {insight['type']}")
                
            except Exception as e:
                logger.error(f"Ошибка при сохранении инсайта: {e}")
    
    def get_summary(self) -> dict[str, Any]:
        """
        Возвращает сводку по анализу.
        
        Returns:
            Dict[str, Any]: Сводная статистика
        """
        return {
            'total_actions': len(self.action_history),
            'total_insights': len(self.insights),
            'insight_types': Counter(i['type'] for i in self.insights),
            'action_types': Counter(a.get('type', 'unknown') for a in self.action_history),
            'last_analysis': datetime.now().isoformat()
        }
