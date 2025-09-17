"""
Базовые классы для системы управления промптами Mark AI
Основано на Context Window Architecture и Agent Lineage Evolution
"""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import json
import logging
import tiktoken

logger = logging.getLogger(__name__)

# Инициализируем tokenizer для подсчета токенов
try:
    tokenizer = tiktoken.encoding_for_model("gpt-4.1-mini")
except Exception:
    try:
        tokenizer = tiktoken.encoding_for_model("gpt-4")
    except Exception:
        tokenizer = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Точный подсчет токенов"""
    return len(tokenizer.encode(text))


class PromptLayer(Enum):
    """11-слойная архитектура контекста (на основе CWA)"""
    INSTRUCTIONS = 1          # Основные инструкции и роль
    USER_INFO = 2             # Информация о пользователе
    KNOWLEDGE_CONTEXT = 3     # RAG слой - фактические знания
    TASK_STATE = 4            # Состояние текущей задачи
    CONVERSATION_HISTORY = 5   # История диалога
    EXAMPLES = 6              # Примеры для few-shot
    TOOL_DEFINITIONS = 7      # Описание доступных инструментов
    CONSTRAINTS = 8           # Ограничения и правила
    METADATA = 9              # Метаданные и настройки
    WORKING_MEMORY = 10       # Временная рабочая память
    USER_QUERY = 11           # Текущий запрос пользователя


class PromptMetadata(BaseModel):
    """Метаданные промпта для версионирования и отслеживания"""
    id: str
    version: str
    created_at: datetime
    updated_at: datetime
    author: str = "system"
    parent_id: Optional[str] = None  # Для эволюции промптов
    performance_metrics: Dict[str, float] = Field(default_factory=dict)
    context_usage: int = 0  # Использование токенов
    tags: List[str] = Field(default_factory=list)
    environment: str = "development"  # development, staging, production


class PromptComponent(BaseModel):
    """Компонент промпта для конкретного слоя"""
    layer: PromptLayer
    content: str
    priority: int = 1  # Для управления приоритетами внутри слоя
    tokens: Optional[int] = None
    dynamic: bool = False  # Может ли изменяться динамически
    validator: Optional[Callable] = None


class PromptTemplate(BaseModel):
    """Шаблон промпта с поддержкой переменных"""
    name: str
    description: str
    components: Dict[PromptLayer, List[PromptComponent]]
    metadata: PromptMetadata
    variables: Dict[str, Any] = Field(default_factory=dict)
    
    def render(self, context: Dict[str, Any]) -> str:
        """Рендеринг промпта с подстановкой переменных"""
        rendered_components = []
        
        # Обходим слои в правильном порядке
        for layer in sorted(PromptLayer, key=lambda x: x.value):
            if layer in self.components:
                for component in sorted(self.components[layer], 
                                      key=lambda x: x.priority, 
                                      reverse=True):
                    content = component.content
                    # Подстановка переменных
                    for var_name, var_value in {**self.variables, **context}.items():
                        content = content.replace(f"{{{var_name}}}", str(var_value))
                    rendered_components.append(content)
        
        return "\n\n".join(rendered_components)
    
    def estimate_tokens(self) -> int:
        """Оценка количества токенов"""
        total = 0
        for components in self.components.values():
            for component in components:
                if component.tokens:
                    total += component.tokens
                else:
                    # Точный подсчет токенов
                    total += count_tokens(component.content)
        return total


class PromptEvolutionRecord(BaseModel):
    """Запись об эволюции промпта (на основе ALE)"""
    generation: int
    trigger_reason: str
    cognitive_state: float  # 0-10
    performance_delta: Dict[str, float]
    inherited_strategies: List[str]
    learned_failures: List[str]
    successor_guidance: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PromptSuccessionPackage(BaseModel):
    """Пакет для передачи знаний следующему поколению промпта"""
    parent_prompt_id: str
    evolution_record: PromptEvolutionRecord
    effective_components: List[PromptComponent]
    deprecated_components: List[PromptComponent]
    context_distillation: str
    user_profile_updates: Dict[str, Any]
    performance_insights: Dict[str, Any]
    
    def generate_successor_prompt(self, base_template: PromptTemplate) -> PromptTemplate:
        """Генерация промпта-преемника на основе наследования"""
        successor = base_template.copy(deep=True)
        successor.metadata.parent_id = self.parent_prompt_id
        successor.metadata.version = f"{base_template.metadata.version}.{self.evolution_record.generation}"
        
        # Применяем эффективные компоненты
        for component in self.effective_components:
            if component.layer not in successor.components:
                successor.components[component.layer] = []
            successor.components[component.layer].append(component)
        
        # Удаляем устаревшие компоненты
        for deprecated in self.deprecated_components:
            if deprecated.layer in successor.components:
                successor.components[deprecated.layer] = [
                    c for c in successor.components[deprecated.layer]
                    if c.content != deprecated.content
                ]
        
        # Добавляем руководство для преемника
        guidance_component = PromptComponent(
            layer=PromptLayer.INSTRUCTIONS,
            content=self.evolution_record.successor_guidance,
            priority=10,
            dynamic=False
        )
        successor.components[PromptLayer.INSTRUCTIONS].append(guidance_component)
        
        return successor