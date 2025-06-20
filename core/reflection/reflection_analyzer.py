from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ReflectionAnalyzer:
    """
    Класс для анализа выполненных действий и генерации инсайтов.
    
    Attributes:
        action_history (List[Dict[str, Any]]): История выполненных действий
        insights (List[Dict[str, Any]]): Список сгенерированных инсайтов
    """
    
    def __init__(self):
        self.action_history: List[Dict[str, Any]] = []
        self.insights: List[Dict[str, Any]] = []
        
    def add_action(self, action: Dict[str, Any]) -> None:
        """
        Добавляет действие в историю.
        
        Args:
            action (Dict[str, Any]): Словарь с информацией о действии
        """
        action['timestamp'] = datetime.now().isoformat()
        self.action_history.append(action)
        logger.debug(f"Added action to history: {action}")
        
    def analyze_actions(self) -> List[Dict[str, Any]]:
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
                    
        self.insights.extend(insights)
        return insights
        
    def _analyze_sequence(self, actions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Анализирует последовательность действий.
        
        Args:
            actions (List[Dict[str, Any]]): Список действий одного типа
            
        Returns:
            Optional[Dict[str, Any]]: Инсайт о последовательности действий или None
        """
        if len(actions) < 2:
            return None
            
        # Здесь будет логика анализа последовательности
        return {
            'type': 'sequence_analysis',
            'action_type': actions[0].get('type'),
            'insight': 'Обнаружена повторяющаяся последовательность действий',
            'timestamp': datetime.now().isoformat()
        }
        
    def _analyze_efficiency(self, actions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Анализирует эффективность действий.
        
        Args:
            actions (List[Dict[str, Any]]): Список действий одного типа
            
        Returns:
            Optional[Dict[str, Any]]: Инсайт об эффективности действий или None
        """
        if len(actions) < 2:
            return None
            
        # Здесь будет логика анализа эффективности
        return {
            'type': 'efficiency_analysis',
            'action_type': actions[0].get('type'),
            'insight': 'Обнаружены возможности для оптимизации',
            'timestamp': datetime.now().isoformat()
        }
        
    def get_insights(self) -> List[Dict[str, Any]]:
        """
        Возвращает список всех сгенерированных инсайтов.
        
        Returns:
            List[Dict[str, Any]]: Список инсайтов
        """
        return self.insights 