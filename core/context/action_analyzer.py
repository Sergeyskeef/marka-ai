"""
Модуль для анализа действий в системе.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from ..memory.memory_manager import MemoryManager

class ActionAnalyzer:
    """
    Класс для анализа действий в системе.
    
    Отвечает за:
    - Анализ последовательности действий
    - Выявление паттернов
    - Генерацию рекомендаций
    - Интеграцию с LLM для анализа
    """
    
    def __init__(self, memory_manager: MemoryManager):
        """
        Инициализация анализатора действий.
        
        Args:
            memory_manager: Менеджер памяти для интеграции с системой памяти
        """
        self.memory_manager = memory_manager
        
    def analyze_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Анализ последовательности действий.
        
        Args:
            actions: Список действий для анализа
            
        Returns:
            Результаты анализа
        """
        if not actions:
            return {'error': 'Нет действий для анализа'}
            
        # Группируем действия по типу
        action_types = {}
        for action in actions:
            action_type = action['type']
            if action_type not in action_types:
                action_types[action_type] = []
            action_types[action_type].append(action)
            
        # Анализируем последовательности
        sequences = self._analyze_sequences(actions)
        
        # Анализируем временные паттерны
        time_patterns = self._analyze_time_patterns(actions)
        
        return {
            'action_types': {k: len(v) for k, v in action_types.items()},
            'sequences': sequences,
            'time_patterns': time_patterns,
            'total_actions': len(actions)
        }
        
    def _analyze_sequences(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Анализ последовательностей действий.
        
        Args:
            actions: Список действий
            
        Returns:
            Список найденных последовательностей
        """
        sequences = []
        current_sequence = []
        
        for action in actions:
            if not current_sequence:
                current_sequence = [action]
            else:
                # Проверяем, является ли действие продолжением последовательности
                if self._is_sequence_continuation(current_sequence[-1], action):
                    current_sequence.append(action)
                else:
                    if len(current_sequence) > 1:
                        sequences.append({
                            'actions': current_sequence,
                            'length': len(current_sequence)
                        })
                    current_sequence = [action]
                    
        # Добавляем последнюю последовательность
        if len(current_sequence) > 1:
            sequences.append({
                'actions': current_sequence,
                'length': len(current_sequence)
            })
            
        return sequences
        
    def _analyze_time_patterns(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Анализ временных паттернов действий.
        
        Args:
            actions: Список действий
            
        Returns:
            Временные паттерны
        """
        if not actions:
            return {}
            
        # Сортируем действия по времени
        sorted_actions = sorted(actions, key=lambda x: datetime.fromisoformat(x['timestamp']))
        
        # Вычисляем интервалы между действиями
        intervals = []
        for i in range(1, len(sorted_actions)):
            prev_time = datetime.fromisoformat(sorted_actions[i-1]['timestamp'])
            curr_time = datetime.fromisoformat(sorted_actions[i]['timestamp'])
            interval = (curr_time - prev_time).total_seconds()
            intervals.append(interval)
            
        return {
            'min_interval': min(intervals) if intervals else 0,
            'max_interval': max(intervals) if intervals else 0,
            'avg_interval': sum(intervals) / len(intervals) if intervals else 0,
            'total_time': (datetime.fromisoformat(sorted_actions[-1]['timestamp']) - 
                          datetime.fromisoformat(sorted_actions[0]['timestamp'])).total_seconds()
        }
        
    def _is_sequence_continuation(self, prev_action: Dict[str, Any], curr_action: Dict[str, Any]) -> bool:
        """
        Проверка, является ли действие продолжением последовательности.
        
        Args:
            prev_action: Предыдущее действие
            curr_action: Текущее действие
            
        Returns:
            True, если действие является продолжением
        """
        # Проверяем временной интервал
        prev_time = datetime.fromisoformat(prev_action['timestamp'])
        curr_time = datetime.fromisoformat(curr_action['timestamp'])
        time_diff = (curr_time - prev_time).total_seconds()
        
        # Если действия одного типа и близки по времени
        if prev_action['type'] == curr_action['type'] and time_diff < 300:  # 5 минут
            return True
            
        # Если действия связаны по контексту
        if 'related_to' in curr_action.get('details', {}) and curr_action['details']['related_to'] == prev_action.get('id'):
            return True
            
        return False
        
    def generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """
        Генерация рекомендаций на основе анализа.
        
        Args:
            analysis: Результаты анализа
            
        Returns:
            Список рекомендаций
        """
        recommendations = []
        
        # Анализируем частоту действий
        for action_type, count in analysis['action_types'].items():
            if count > 10:  # Если действие выполняется слишком часто
                recommendations.append(f"Рассмотрите возможность оптимизации частых действий типа '{action_type}'")
                
        # Анализируем последовательности
        for sequence in analysis['sequences']:
            if sequence['length'] > 3:  # Если последовательность слишком длинная
                recommendations.append(f"Обнаружена длинная последовательность из {sequence['length']} действий. "
                                    f"Возможно, стоит объединить их в одно действие")
                
        # Анализируем временные паттерны
        if analysis['time_patterns'].get('avg_interval', 0) < 60:  # Если средний интервал меньше минуты
            recommendations.append("Обнаружены частые действия с малым интервалом. "
                                "Рассмотрите возможность пакетной обработки")
                                
        return recommendations 