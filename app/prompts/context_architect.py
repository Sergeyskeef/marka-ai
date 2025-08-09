"""
Архитектор контекста на основе Context Window Architecture (CWA)
Оптимизация структуры и расположения информации в контексте
"""

from typing import Dict, List, Optional, Any, Tuple
import logging
from enum import IntEnum
import time

from .base import PromptTemplate, PromptComponent, PromptLayer
from .metrics import metrics_collector

logger = logging.getLogger(__name__)


class ContextPosition(IntEnum):
    """Позиции в контексте с учетом эффектов primacy и recency"""
    TOP = 1          # Максимальный primacy эффект
    UPPER = 2        # Высокий primacy
    MIDDLE_HIGH = 3  # Средне-высокий
    MIDDLE = 4       # Минимальное внимание (Lost in the Middle)
    MIDDLE_LOW = 5   # Средне-низкий
    LOWER = 6        # Начало recency эффекта
    BOTTOM = 7       # Максимальный recency эффект


class ContextArchitect:
    """
    Архитектор для оптимального построения контекста
    
    Основные принципы:
    - Критическая информация в начале и конце (U-shaped attention)
    - Компрессия середины контекста
    - Динамическая приоритизация слоев
    - Управление размером контекста
    """
    
    def __init__(self, max_context_tokens: int = 8192):
        self.max_context_tokens = max_context_tokens
        
        # Карта оптимального расположения слоев
        self.layer_position_map = self._initialize_position_map()
        
        # Веса важности для разных позиций (U-shaped)
        self.position_weights = {
            ContextPosition.TOP: 1.0,
            ContextPosition.UPPER: 0.9,
            ContextPosition.MIDDLE_HIGH: 0.6,
            ContextPosition.MIDDLE: 0.4,  # Lost in the Middle
            ContextPosition.MIDDLE_LOW: 0.5,
            ContextPosition.LOWER: 0.8,
            ContextPosition.BOTTOM: 0.95
        }
    
    def _initialize_position_map(self) -> Dict[PromptLayer, ContextPosition]:
        """Инициализация карты оптимальных позиций для слоев"""
        return {
            # Критические слои в начале (primacy)
            PromptLayer.INSTRUCTIONS: ContextPosition.TOP,
            PromptLayer.CONSTRAINTS: ContextPosition.TOP,
            
            # Важные контекстные слои
            PromptLayer.USER_INFO: ContextPosition.UPPER,
            PromptLayer.TASK_STATE: ContextPosition.UPPER,
            
            # RAG и знания - могут быть в середине
            PromptLayer.KNOWLEDGE_CONTEXT: ContextPosition.MIDDLE_HIGH,
            PromptLayer.EXAMPLES: ContextPosition.MIDDLE,
            
            # История и метаданные
            PromptLayer.CONVERSATION_HISTORY: ContextPosition.MIDDLE_LOW,
            PromptLayer.METADATA: ContextPosition.LOWER,
            
            # Инструменты и рабочая память
            PromptLayer.TOOL_DEFINITIONS: ContextPosition.LOWER,
            PromptLayer.WORKING_MEMORY: ContextPosition.LOWER,
            
            # Текущий запрос всегда в конце (recency)
            PromptLayer.USER_QUERY: ContextPosition.BOTTOM
        }
    
    def architect_context(self, 
                         template: PromptTemplate,
                         context_data: Dict[str, Any],
                         optimization_mode: str = "balanced") -> Tuple[str, Dict[str, Any]]:
        """
        Архитектурное построение контекста
        
        Args:
            template: Шаблон промпта
            context_data: Данные контекста
            optimization_mode: Режим оптимизации (balanced, memory, performance)
            
        Returns:
            Tuple[оптимизированный_контекст, метрики]
        """
        start_time = time.time()
        
        # Собираем компоненты по позициям
        positioned_components = self._position_components(template)
        
        # Оцениваем размер
        size_estimate = self._estimate_size(positioned_components, context_data)
        
        # Применяем оптимизацию если нужно
        if size_estimate > self.max_context_tokens:
            positioned_components = self._optimize_components(
                positioned_components, 
                size_estimate,
                optimization_mode
            )
        
        # Рендерим финальный контекст
        final_context = self._render_positioned_context(positioned_components, context_data)
        
        # Собираем метрики
        metrics = self._calculate_metrics(final_context, positioned_components)
        
        # Записываем метрики производительности
        duration = time.time() - start_time
        metrics_collector.record_optimization_time(duration)
        
        # Обновляем метрику использования контекста
        if hasattr(template, 'name'):
            metrics_collector.update_context_utilization(
                template.name,
                metrics.get("utilization", 0)
            )
        
        return final_context, metrics
    
    def _position_components(self, 
                           template: PromptTemplate) -> Dict[ContextPosition, List[PromptComponent]]:
        """Распределение компонентов по позициям"""
        positioned = {pos: [] for pos in ContextPosition}
        
        for layer, components in template.components.items():
            target_position = self.layer_position_map.get(layer, ContextPosition.MIDDLE)
            
            for component in components:
                # Корректируем позицию на основе приоритета
                if component.priority >= 9:
                    # Критические компоненты ближе к краям
                    if target_position >= ContextPosition.MIDDLE:
                        target_position = ContextPosition.LOWER
                    else:
                        target_position = ContextPosition.TOP
                
                positioned[target_position].append(component)
        
        return positioned
    
    def _estimate_size(self, 
                      positioned: Dict[ContextPosition, List[PromptComponent]],
                      context_data: Dict[str, Any]) -> int:
        """Оценка размера контекста в токенах"""
        total_tokens = 0
        
        for components in positioned.values():
            for component in components:
                if component.tokens:
                    total_tokens += component.tokens
                else:
                    # Рендерим с данными для оценки
                    rendered = component.content
                    for key, value in context_data.items():
                        rendered = rendered.replace(f"{{{key}}}", str(value))
                    total_tokens += len(rendered) // 4
        
        return total_tokens
    
    def _optimize_components(self, 
                           positioned: Dict[ContextPosition, List[PromptComponent]],
                           current_size: int,
                           mode: str) -> Dict[ContextPosition, List[PromptComponent]]:
        """Оптимизация компонентов для уменьшения размера"""
        target_reduction = current_size - self.max_context_tokens
        
        if mode == "balanced":
            # Сбалансированная оптимизация
            return self._balanced_optimization(positioned, target_reduction)
        elif mode == "memory":
            # Приоритет памяти - агрессивная компрессия
            return self._memory_optimization(positioned, target_reduction)
        elif mode == "performance":
            # Приоритет производительности - минимальная компрессия
            return self._performance_optimization(positioned, target_reduction)
        
        return positioned
    
    def _balanced_optimization(self, 
                             positioned: Dict[ContextPosition, List[PromptComponent]],
                             target_reduction: int) -> Dict[ContextPosition, List[PromptComponent]]:
        """Сбалансированная оптимизация с учетом U-shaped attention"""
        optimized = {}
        current_reduction = 0
        
        # Начинаем с середины (наименьший вес)
        for position in sorted(ContextPosition, 
                             key=lambda p: self.position_weights[p]):
            components = positioned[position]
            
            if current_reduction >= target_reduction:
                optimized[position] = components
                continue
            
            # Фильтруем низкоприоритетные компоненты
            filtered = []
            for comp in sorted(components, key=lambda c: c.priority, reverse=True):
                if comp.priority < 5 and current_reduction < target_reduction:
                    # Пропускаем низкоприоритетный компонент
                    current_reduction += comp.tokens or (len(comp.content) // 4)
                else:
                    filtered.append(comp)
            
            optimized[position] = filtered
        
        return optimized
    
    def _memory_optimization(self, 
                           positioned: Dict[ContextPosition, List[PromptComponent]],
                           target_reduction: int) -> Dict[ContextPosition, List[PromptComponent]]:
        """Агрессивная оптимизация для экономии памяти"""
        optimized = {}
        
        for position, components in positioned.items():
            # Оставляем только высокоприоритетные
            optimized[position] = [
                c for c in components 
                if c.priority >= 7 or position in [ContextPosition.TOP, ContextPosition.BOTTOM]
            ]
        
        return optimized
    
    def _performance_optimization(self, 
                                positioned: Dict[ContextPosition, List[PromptComponent]],
                                target_reduction: int) -> Dict[ContextPosition, List[PromptComponent]]:
        """Минимальная оптимизация для сохранения производительности"""
        optimized = {}
        
        for position, components in positioned.items():
            # Удаляем только компоненты с приоритетом < 3
            optimized[position] = [c for c in components if c.priority >= 3]
        
        return optimized
    
    def _render_positioned_context(self, 
                                 positioned: Dict[ContextPosition, List[PromptComponent]],
                                 context_data: Dict[str, Any]) -> str:
        """Рендеринг финального контекста с учетом позиций"""
        sections = []
        
        # Проходим по позициям в правильном порядке
        for position in sorted(ContextPosition):
            components = positioned.get(position, [])
            
            # Сортируем по приоритету внутри позиции
            for component in sorted(components, key=lambda c: c.priority, reverse=True):
                rendered = component.content
                
                # Подстановка переменных
                for key, value in context_data.items():
                    rendered = rendered.replace(f"{{{key}}}", str(value))
                
                sections.append(rendered)
        
        return "\n\n".join(sections)
    
    def _calculate_metrics(self, 
                         context: str,
                         positioned: Dict[ContextPosition, List[PromptComponent]]) -> Dict[str, Any]:
        """Расчет метрик построенного контекста"""
        total_tokens = len(context) // 4
        
        # Распределение по позициям
        position_distribution = {}
        for position, components in positioned.items():
            position_distribution[position.name] = len(components)
        
        # Оценка качества на основе U-shaped attention
        quality_score = 0
        total_weight = 0
        
        for position, components in positioned.items():
            weight = self.position_weights[position]
            component_importance = sum(c.priority for c in components)
            quality_score += weight * component_importance
            total_weight += component_importance
        
        if total_weight > 0:
            quality_score /= total_weight
        
        return {
            "total_tokens": total_tokens,
            "utilization": total_tokens / self.max_context_tokens,
            "position_distribution": position_distribution,
            "quality_score": quality_score,
            "components_count": sum(len(c) for c in positioned.values())
        }
    
    def analyze_attention_distribution(self, 
                                     template: PromptTemplate) -> Dict[str, Any]:
        """Анализ распределения внимания в шаблоне"""
        analysis = {
            "layers": {},
            "recommendations": []
        }
        
        for layer, components in template.components.items():
            position = self.layer_position_map.get(layer, ContextPosition.MIDDLE)
            weight = self.position_weights[position]
            
            analysis["layers"][layer.name] = {
                "position": position.name,
                "attention_weight": weight,
                "components": len(components),
                "avg_priority": sum(c.priority for c in components) / len(components) if components else 0
            }
            
            # Рекомендации
            if weight < 0.5 and any(c.priority >= 8 for c in components):
                analysis["recommendations"].append(
                    f"Слой {layer.name} содержит высокоприоритетные компоненты, "
                    f"но находится в зоне низкого внимания (Lost in the Middle)"
                )
        
        return analysis
    
    def optimize_for_model(self, 
                         template: PromptTemplate,
                         model_name: str) -> PromptTemplate:
        """Оптимизация под конкретную модель"""
        optimized = template.copy(deep=True)
        
        # Настройки для разных моделей
        model_configs = {
            "gpt-4": {"max_tokens": 8192, "attention_curve": "standard"},
            "gpt-4.1-mini": {"max_tokens": 16384, "attention_curve": "improved"},
            "gpt-5-mini": {"max_tokens": 32768, "attention_curve": "advanced"},  # GPT-5 с улучшенной обработкой контекста
            "claude-3": {"max_tokens": 100000, "attention_curve": "flat"},
            "gemini-pro": {"max_tokens": 32768, "attention_curve": "standard"}
        }
        
        config = model_configs.get(model_name, {"max_tokens": 4096, "attention_curve": "standard"})
        
        # Адаптируем под размер контекста
        self.max_context_tokens = config["max_tokens"]
        
        # Корректируем веса для разных кривых внимания
        if config["attention_curve"] == "flat":
            # Более равномерное распределение внимания
            for pos in ContextPosition:
                self.position_weights[pos] = max(0.7, self.position_weights[pos])
        elif config["attention_curve"] == "improved":
            # Улучшенная работа с серединой
            self.position_weights[ContextPosition.MIDDLE] = 0.6
            self.position_weights[ContextPosition.MIDDLE_HIGH] = 0.7
            self.position_weights[ContextPosition.MIDDLE_LOW] = 0.65
        elif config["attention_curve"] == "advanced":
            # GPT-5 продвинутая обработка - почти равномерное внимание
            self.position_weights[ContextPosition.MIDDLE] = 0.8
            self.position_weights[ContextPosition.MIDDLE_HIGH] = 0.85
            self.position_weights[ContextPosition.MIDDLE_LOW] = 0.8
        
        return optimized