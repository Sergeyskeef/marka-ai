"""
Интеграционный слой между системой действий и системой обучения.
"""

from typing import Dict, Any, Optional
from datetime import datetime

from langchain_api.core.learning_system import LearningSystem
from langchain_api.core.memory.memory_manager import MemoryManager
from langchain_api.core.memory.enhanced_memory import EnhancedMemory
from langchain_api.core.context.action_types import ActionSystem, Action

class ActionLearningIntegration:
    """Интеграционный слой между системой действий и системой обучения."""
    
    def __init__(
        self,
        action_system: ActionSystem,
        learning_system: LearningSystem,
        memory_manager: MemoryManager,
        enhanced_memory: EnhancedMemory
    ):
        self.action_system = action_system
        self.learning_system = learning_system
        self.memory_manager = memory_manager
        self.enhanced_memory = enhanced_memory

    async def process_action_result(self, action_id: str, result: Dict[str, Any]) -> None:
        """Обработать результат выполнения действия.
        
        Args:
            action_id: ID действия
            result: Результат выполнения
        """
        action = self.action_system.action_tracker.get_action_by_id(action_id)
        if not action:
            return

        # Сохраняем результат в EnhancedMemory
        await self._save_to_enhanced_memory(action, result)
        
        # Анализируем действие через LearningSystem
        analysis = self.learning_system.analyze_action(action, result)
        
        # Обновляем паттерны
        self.learning_system.update_patterns(analysis["patterns"])
        
        # Генерируем инсайты
        await self._generate_insights(action, result, analysis)

    async def _save_to_enhanced_memory(self, action: Action, result: Dict[str, Any]) -> None:
        """Сохранить результат действия в EnhancedMemory.
        
        Args:
            action: Действие
            result: Результат выполнения
        """
        await self.enhanced_memory.store_action_result(
            action_id=action.id,
            action_type=action.type,
            result=result,
            timestamp=datetime.now()
        )

    async def _generate_insights(self, action: Action, result: Dict[str, Any], analysis: Dict[str, Any]) -> None:
        """Сгенерировать инсайты на основе результата действия.
        
        Args:
            action: Действие
            result: Результат выполнения
            analysis: Результат анализа
        """
        insight = {
            "action_id": action.id,
            "action_type": action.type,
            "result": result,
            "analysis": analysis,
            "timestamp": datetime.now()
        }
        
        await self.memory_manager.store_insight(insight)

    def get_action_recommendations(self, context: Dict[str, Any]) -> list[Dict[str, Any]]:
        """Получить рекомендации по действиям на основе контекста.
        
        Args:
            context: Контекст для генерации рекомендаций
            
        Returns:
            Список рекомендаций
        """
        recommendations = self.learning_system.generate_recommendations(context)
        
        # Добавляем похожие действия из EnhancedMemory
        for rec in recommendations:
            similar_actions = self.enhanced_memory.find_similar_actions(
                action_type=rec["type"],
                context=context
            )
            rec["similar_actions"] = similar_actions
            
        return recommendations 