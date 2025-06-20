"""
Модуль для интеграции системы рассуждений с системой памяти.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json

from ..memory.enhanced_memory import EnhancedMemory
from .reasoning_chains import ReasoningChain, ReasoningStep
from .self_learning import SelfLearningSystem, LearningPattern

logger = logging.getLogger(__name__)

class MemoryIntegration:
    """
    Класс для интеграции системы рассуждений с системой памяти.
    
    Особенности:
    - Сохранение цепочек рассуждений в памяти
    - Извлечение релевантных воспоминаний для рассуждений
    - Интеграция с системой самообучения
    - Анализ и использование исторического опыта
    """
    
    def __init__(self, memory: EnhancedMemory, learning_system: SelfLearningSystem):
        """
        Инициализация интеграции.
        
        Args:
            memory: Экземпляр расширенной памяти
            learning_system: Экземпляр системы самообучения
        """
        self.memory = memory
        self.learning_system = learning_system
        
    def save_reasoning_chain(self, chain: ReasoningChain) -> str:
        """
        Сохранение цепочки рассуждений в памяти.
        
        Args:
            chain: Цепочка рассуждений для сохранения
            
        Returns:
            ID сохраненной цепочки
        """
        # Преобразуем цепочку в словарь
        chain_data = chain.to_dict()
        
        # Добавляем метаданные
        chain_data['type'] = 'reasoning_chain'
        chain_data['timestamp'] = datetime.utcnow().isoformat()
        chain_data['id'] = f"chain_{len(self.memory.get_all())}"
        
        # Добавляем контекст из первого шага
        if chain.steps:
            chain_data['context'] = chain.steps[0].context
        
        # Сохраняем в память
        self.memory.insert(chain_data)
        
        # Анализируем паттерны для самообучения
        self._analyze_chain_for_learning(chain)
        
        return chain_data['id']
    
    def get_relevant_memories(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Получение релевантных воспоминаний для заданного контекста.
        
        Args:
            context: Контекст для поиска релевантных воспоминаний
            
        Returns:
            Список релевантных воспоминаний
        """
        # Получаем все воспоминания
        memories = self.memory.get_all()
        
        # Фильтруем только цепочки рассуждений
        reasoning_chains = [m for m in memories if m.get('type') == 'reasoning_chain']
        
        # Рассчитываем релевантность для каждой цепочки
        for chain in reasoning_chains:
            chain['relevance'] = self._calculate_relevance(chain, context)
        
        # Сортируем по релевантности
        relevant_memories = sorted(reasoning_chains, key=lambda x: x['relevance'], reverse=True)
        
        return relevant_memories
    
    def analyze_historical_experience(self, 
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализ исторического опыта для текущего контекста.
        
        Args:
            context: Текущий контекст
            
        Returns:
            Словарь с анализом исторического опыта
        """
        # Получаем релевантные воспоминания
        memories = self.get_relevant_memories(context)
        
        # Анализируем успешные паттерны
        successful_patterns = [
            m['data'] for m in memories 
            if m['type'] == 'pattern' and m['data'].success_rate > 0.7
        ]
        
        # Анализируем цепочки рассуждений
        reasoning_chains = [
            m['data'] for m in memories 
            if m['type'] == 'memory' and m['data']['type'] == 'reasoning_chain'
        ]
        
        return {
            'successful_patterns': successful_patterns,
            'reasoning_chains': reasoning_chains,
            'total_experience': len(memories),
            'success_rate': self._calculate_success_rate(memories)
        }
    
    def _analyze_chain_for_learning(self, chain: ReasoningChain) -> None:
        """
        Анализ цепочки рассуждений для самообучения.
        
        Args:
            chain: Цепочка рассуждений для анализа
        """
        if not chain.steps:
            return
            
        # Извлекаем контекст из первого шага
        context = chain.steps[0].context.copy()
        context['chain_id'] = chain.id
        context['steps_count'] = len(chain.steps)
        context['evaluation'] = chain.evaluate()
        
        # Создаем паттерн обучения
        pattern = LearningPattern(
            id=f"pattern_{len(self.learning_system.patterns)}",
            pattern_type=context.get('type', 'unknown'),
            context=context,
            confidence=chain.evaluate(),
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
            usage_count=1,
            success_rate=1.0
        )
        
        # Добавляем паттерн в систему обучения
        self.learning_system.add_pattern(pattern)
    
    def _calculate_relevance(self, 
                           memory: Dict[str, Any], 
                           context: Dict[str, Any]) -> float:
        """
        Расчет релевантности воспоминания для контекста.
        
        Args:
            memory: Воспоминание
            context: Контекст
            
        Returns:
            Оценка релевантности от 0 до 1
        """
        relevance = 0.0
        
        # Проверяем совпадение типов
        if memory.get('type') == context.get('type'):
            relevance += 0.3
            
        # Проверяем совпадение ключевых полей
        for key, value in context.items():
            if key in memory and memory[key] == value:
                relevance += 0.2
                
        # Учитываем важность воспоминания
        importance = self.memory.importance_scores.get(memory['id'], 0.0)
        relevance += importance * 0.3
        
        return min(relevance, 1.0)
    
    def _calculate_success_rate(self, 
                              memories: List[Dict[str, Any]]) -> float:
        """
        Расчет общего показателя успешности.
        
        Args:
            memories: Список воспоминаний
            
        Returns:
            Показатель успешности от 0 до 1
        """
        if not memories:
            return 0.0
            
        success_count = 0
        for memory in memories:
            if memory['type'] == 'pattern':
                success_count += memory['data'].success_rate
            elif memory['type'] == 'memory':
                # Для цепочек рассуждений используем их оценку
                if memory['data']['type'] == 'reasoning_chain':
                    success_count += memory['data'].get('evaluation', 0.0)
                    
        return success_count / len(memories) 