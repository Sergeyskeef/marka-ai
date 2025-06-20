from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class ReasoningStep:
    """Шаг в цепочке рассуждений"""
    id: str
    content: str
    context: Dict[str, Any]
    timestamp: datetime
    confidence: float
    parent_id: Optional[str] = None
    children_ids: List[str] = None

    def __post_init__(self):
        if self.children_ids is None:
            self.children_ids = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReasoningStep':
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

class ReasoningChain:
    """
    Класс для представления цепочки рассуждений.
    """
    
    def __init__(self, id: str):
        """
        Инициализация цепочки рассуждений.
        
        Args:
            id: Уникальный идентификатор цепочки
        """
        self.id = id
        self.steps: List[ReasoningStep] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    @property
    def chain_id(self) -> str:
        """Алиас для id для совместимости с тестами"""
        return self.id
        
    @property
    def root_step_id(self) -> Optional[str]:
        """ID корневого шага (первого шага без родителя)"""
        for step in self.steps:
            if step.parent_id is None:
                return step.id
        return None

    def add_step(self, step: ReasoningStep) -> None:
        """
        Добавление шага в цепочку.
        
        Args:
            step: Шаг для добавления
        """
        self.steps.append(step)
        self.updated_at = datetime.now()
        
        # Обновляем children_ids родительского шага
        if step.parent_id:
            parent = self.get_step(step.parent_id)
            if parent and step.id not in parent.children_ids:
                parent.children_ids.append(step.id)

    def get_step(self, step_id: str) -> Optional[ReasoningStep]:
        """
        Получение шага по ID.
        
        Args:
            step_id: ID шага
            
        Returns:
            Шаг или None, если не найден
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_chain(self, step_id: str) -> List[ReasoningStep]:
        """Получает цепочку шагов от корня до указанного шага"""
        chain = []
        current = self.get_step(step_id)
        while current:
            chain.append(current)
            current = self.get_step(current.parent_id)
        return list(reversed(chain))

    def evaluate(self) -> float:
        """
        Оценка логической согласованности цепочки.
        
        Returns:
            Оценка от 0 до 1
        """
        if not self.steps:
            return 0.0
            
        # Оцениваем каждый шаг
        step_scores = []
        for step in self.steps:
            # Проверяем наличие родительского шага
            if step.parent_id:
                parent = self.get_step(step.parent_id)
                if not parent:
                    step_scores.append(0.0)
                    continue
                    
                # Оцениваем связь с родительским шагом
                if step.context.get('type') == parent.context.get('type'):
                    step_scores.append(step.confidence)
                else:
                    step_scores.append(step.confidence * 0.5)
            else:
                step_scores.append(step.confidence)
                
        return sum(step_scores) / len(step_scores)
        
    def evaluate_logical_consistency(self) -> float:
        """Алиас для evaluate() для совместимости с тестами"""
        return self.evaluate()

    def to_dict(self) -> Dict[str, Any]:
        """
        Преобразование цепочки в словарь.
        
        Returns:
            Словарь с данными цепочки
        """
        return {
            'id': self.id,
            'steps': [step.to_dict() for step in self.steps],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReasoningChain':
        """
        Создание цепочки из словаря.
        
        Args:
            data: Словарь с данными
            
        Returns:
            Созданная цепочка
        """
        chain = cls(data['id'])
        for step_data in data['steps']:
            chain.add_step(ReasoningStep.from_dict(step_data))
        chain.created_at = datetime.fromisoformat(data['created_at'])
        chain.updated_at = datetime.fromisoformat(data['updated_at'])
        return chain

class ReasoningSystem:
    """Система управления цепочками рассуждений"""
    def __init__(self):
        self.chains: Dict[str, ReasoningChain] = {}
        self.current_chain_id: Optional[str] = None

    def create_chain(self, chain_id: str) -> ReasoningChain:
        """Создает новую цепочку рассуждений"""
        chain = ReasoningChain(chain_id)
        self.chains[chain_id] = chain
        self.current_chain_id = chain_id
        return chain

    def get_chain(self, chain_id: str) -> Optional[ReasoningChain]:
        """Получает цепочку по ID"""
        return self.chains.get(chain_id)

    def add_step(self, chain_id: str, step: ReasoningStep) -> None:
        """Добавляет шаг в указанную цепочку"""
        chain = self.get_chain(chain_id)
        if chain:
            chain.add_step(step)
        else:
            logger.error(f"Chain {chain_id} not found")

    def analyze_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Анализирует контекст и возвращает дополнительные метаданные"""
        # TODO: Реализовать анализ контекста
        return {
            "context_size": len(str(context)),
            "has_code": any(key in context for key in ["code", "function", "class"]),
            "has_text": any(key in context for key in ["text", "content", "message"])
        }

    def evaluate_chain(self, chain_id: str) -> Dict[str, Any]:
        """Оценивает качество цепочки рассуждений"""
        chain = self.get_chain(chain_id)
        if not chain:
            return {"error": "Chain not found"}
        
        # Вычисляем максимальную глубину
        max_depth = 0
        for step in chain.steps:
            depth = len(chain.get_chain(step.id))
            max_depth = max(max_depth, depth)
        
        return {
            "logical_consistency": chain.evaluate(),
            "step_count": len(chain.steps),
            "depth": max_depth,
            "average_confidence": sum(step.confidence for step in chain.steps) / len(chain.steps) if chain.steps else 0.0
        }

    def save_chains(self, filepath: str) -> None:
        """Сохраняет все цепочки в файл"""
        data = {
            "chains": {chain_id: chain.to_dict() for chain_id, chain in self.chains.items()},
            "current_chain_id": self.current_chain_id
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_chains(cls, filepath: str) -> 'ReasoningSystem':
        """Загружает цепочки из файла"""
        system = cls()
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for chain_id, chain_data in data['chains'].items():
            system.chains[chain_id] = ReasoningChain.from_dict(chain_data)
        
        system.current_chain_id = data.get('current_chain_id')
        return system 