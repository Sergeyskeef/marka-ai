from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from .reasoning_chains import ReasoningSystem, ReasoningStep

logger = logging.getLogger(__name__)

@dataclass
class LearningPattern:
    """Паттерн обучения"""
    id: str
    pattern_type: str
    context: Dict[str, Any]
    confidence: float
    created_at: datetime
    last_used: datetime
    usage_count: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, data: Dict[str, Any]) -> 'LearningPattern':
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
        self.patterns: Dict[str, LearningPattern] = {}
        self.learning_history: List[Dict[str, Any]] = []

    def add_pattern(self, pattern: LearningPattern) -> None:
        """
        Добавление нового паттерна обучения.
        
        Args:
            pattern: Паттерн для добавления
        """
        self.patterns[pattern.id] = pattern
        
    def analyze_patterns(self, chain_id: str) -> List[LearningPattern]:
        """Анализирует цепочку рассуждений и извлекает паттерны"""
        chain = self.reasoning_system.get_chain(chain_id)
        if not chain:
            return []

        patterns = []
        for step in chain.steps.values():
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

    def _determine_pattern_type(self, context_analysis: Dict[str, Any]) -> str:
        """Определяет тип паттерна на основе анализа контекста"""
        if context_analysis["has_code"]:
            return "code_pattern"
        elif context_analysis["has_text"]:
            return "text_pattern"
        else:
            return "general_pattern"

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

    def get_relevant_patterns(self, context: Dict[str, Any]) -> List[LearningPattern]:
        """
        Получение релевантных паттернов для контекста.
        
        Args:
            context: Контекст для поиска
            
        Returns:
            Список релевантных паттернов
        """
        relevant_patterns = []
        
        for pattern in self.patterns.values():
            # Проверяем совпадение типов
            if pattern.pattern_type == context.get('type'):
                # Проверяем совпадение ключевых полей контекста
                context_match = True
                for key, value in context.items():
                    if key in pattern.context and pattern.context[key] != value:
                        context_match = False
                        break
                
                if context_match:
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
                
    def get_learning_stats(self) -> Dict[str, Any]:
        """
        Получение статистики обучения.
        
        Returns:
            Словарь со статистикой
        """
        total_patterns = len(self.patterns)
        successful_patterns = sum(1 for p in self.patterns.values() if p.success_rate > 0.7)
        
        return {
            'total_patterns': total_patterns,
            'successful_patterns': successful_patterns,
            'success_rate': successful_patterns / total_patterns if total_patterns > 0 else 0.0
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
            
    def load_state(self, filepath: str) -> None:
        """
        Загрузка состояния системы.
        
        Args:
            filepath: Путь к файлу
        """
        with open(filepath, 'r') as f:
            state = json.load(f)
            
        self.patterns.clear()
        for pattern_data in state['patterns'].values():
            pattern = LearningPattern(
                id=pattern_data['id'],
                pattern_type=pattern_data['pattern_type'],
                context=pattern_data['context'],
                confidence=pattern_data['confidence'],
                created_at=datetime.fromisoformat(pattern_data['created_at']),
                last_used=datetime.fromisoformat(pattern_data['last_used']),
                usage_count=pattern_data['usage_count'],
                success_rate=pattern_data['success_rate']
            )
            self.patterns[pattern.id] = pattern
        
        self.learning_history = state['learning_history'] 