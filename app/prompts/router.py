"""
Динамический роутер промптов на основе контекстных бандитов
Автоматически выбирает оптимальный промпт для каждого запроса
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from datetime import datetime
import logging
from collections import defaultdict
import asyncio
import time

from .base import PromptTemplate, PromptLayer
from .manager import PromptManager
from .metrics import metrics_collector

logger = logging.getLogger(__name__)


class DynamicPromptRouter:
    """
    Роутер для автоматического выбора промптов на основе:
    - Контекста запроса
    - Исторической производительности
    - Multi-armed bandit алгоритма (LinUCB)
    - Бюджета на вычисления
    """
    
    def __init__(self, 
                 prompt_manager: PromptManager,
                 alpha: float = 0.25,  # Параметр исследования для LinUCB
                 budget_aware: bool = True):
        self.prompt_manager = prompt_manager
        self.alpha = alpha
        self.budget_aware = budget_aware
        
        # Параметры LinUCB для каждого промпта
        self.arms: Dict[str, LinUCBArm] = {}
        
        # История выборов
        self.selection_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000  # Ограничение размера истории
        
        # Контекстные признаки
        self.context_features = ContextFeatureExtractor()
        
        # Кеш маршрутизации
        self.routing_cache: Dict[str, str] = {}
        
    async def select_prompt(self, 
                          context: Dict[str, Any],
                          candidates: Optional[List[str]] = None,
                          environment: str = "production") -> Tuple[PromptTemplate, float]:
        """
        Выбор оптимального промпта для контекста
        
        Returns:
            Tuple[PromptTemplate, confidence_score]
        """
        start_time = time.time()
        
        # Извлекаем признаки контекста
        features = self.context_features.extract(context)
        
        # Получаем кандидатов
        if candidates is None:
            all_prompts = await self.prompt_manager.list_prompts(environment)
            candidates = [p["name"] for p in all_prompts if p["active_version"]]
        
        if not candidates:
            # Создаем дефолтный промпт если нет других
            logger.warning("Нет доступных промптов, создаю дефолтный")
            from .templates.mark_base import create_mark_base_prompt
            default_prompt = create_mark_base_prompt()
            await self.prompt_manager.save_prompt(default_prompt)
            candidates = [default_prompt.name]
        
        # Инициализируем arms для новых промптов
        for name in candidates:
            if name not in self.arms:
                self.arms[name] = LinUCBArm(features.shape[0])
        
        # Вычисляем UCB для каждого кандидата
        ucb_scores = {}
        for name in candidates:
            arm = self.arms[name]
            ucb = arm.get_ucb(features, self.alpha)
            
            # Учитываем бюджет если включено
            if self.budget_aware and "budget" in context:
                prompt = await self.prompt_manager.get_prompt(name, environment=environment)
                if prompt:
                    cost_factor = self._calculate_cost_factor(prompt, context["budget"])
                    ucb *= cost_factor
            
            ucb_scores[name] = ucb
        
        # Выбираем промпт с максимальным UCB
        selected_name = max(ucb_scores, key=ucb_scores.get)
        confidence = ucb_scores[selected_name]
        
        # Получаем выбранный промпт
        selected_prompt = await self.prompt_manager.get_prompt(
            selected_name, 
            environment=environment
        )
        
        # Записываем выбор
        self.selection_history.append({
            "timestamp": datetime.now(),
            "context": context,
            "features": features.tolist(),
            "selected": selected_name,
            "confidence": confidence,
            "candidates": ucb_scores
        })
        
        # Ограничиваем размер истории
        if len(self.selection_history) > self.max_history_size:
            self.selection_history = self.selection_history[-self.max_history_size:]
        
        logger.info(f"Выбран промпт {selected_name} с уверенностью {confidence:.3f}")
        
        # Записываем метрики
        duration = time.time() - start_time
        metrics_collector.record_selection(
            selected_name,
            environment,
            confidence,
            duration
        )
        
        return selected_prompt, confidence
    
    async def update_reward(self, 
                          prompt_name: str,
                          context: Dict[str, Any],
                          reward: float):
        """Обновление награды после использования промпта"""
        if prompt_name not in self.arms:
            logger.warning(f"Промпт {prompt_name} не найден в arms")
            return
        
        features = self.context_features.extract(context)
        self.arms[prompt_name].update(features, reward)
        
        # Обновляем метрики в менеджере
        await self.prompt_manager.update_metrics(
            prompt_name,
            version=None,  # Используем активную версию
            environment="production",
            metrics={"reward": reward}
        )
        
        # Записываем метрику награды
        metrics_collector.record_reward(prompt_name, reward)
    
    def _calculate_cost_factor(self, 
                             prompt: PromptTemplate,
                             budget: Dict[str, float]) -> float:
        """Расчет фактора стоимости для бюджетно-осознанной маршрутизации"""
        estimated_tokens = prompt.estimate_tokens()
        
        if "max_tokens" in budget:
            if estimated_tokens > budget["max_tokens"]:
                return 0.1  # Сильно штрафуем превышение бюджета
            else:
                # Линейное снижение для больших промптов
                return 1.0 - (estimated_tokens / budget["max_tokens"]) * 0.3
        
        return 1.0
    
    async def get_routing_stats(self) -> Dict[str, Any]:
        """Статистика маршрутизации"""
        stats = {
            "total_selections": len(self.selection_history),
            "prompts": {},
            "recent_performance": []
        }
        
        # Подсчет выборов по промптам
        selection_counts = defaultdict(int)
        for record in self.selection_history:
            selection_counts[record["selected"]] += 1
        
        # Статистика по каждому промпту
        for name, arm in self.arms.items():
            stats["prompts"][name] = {
                "selections": selection_counts[name],
                "avg_reward": arm.get_average_reward(),
                "exploration_bonus": arm.get_exploration_bonus(self.alpha)
            }
        
        # Последние 10 выборов
        stats["recent_performance"] = [
            {
                "timestamp": r["timestamp"].isoformat(),
                "selected": r["selected"],
                "confidence": r["confidence"]
            }
            for r in self.selection_history[-10:]
        ]
        
        return stats


class LinUCBArm:
    """
    Реализация LinUCB arm для одного промпта
    """
    
    def __init__(self, feature_dim: int):
        self.feature_dim = feature_dim
        
        # Параметры модели
        self.A = np.identity(feature_dim)  # Матрица признаков
        self.b = np.zeros(feature_dim)     # Вектор наград
        self.theta = None                   # Оценка параметров
        
        # Кеш для обратной матрицы
        self._A_inv = np.identity(feature_dim)
        self._A_inv_valid = True
        
        # Статистика
        self.num_selections = 0
        self.total_reward = 0.0
        
    def get_ucb(self, features: np.ndarray, alpha: float) -> float:
        """Вычисление Upper Confidence Bound с кешированием"""
        # Вычисляем обратную матрицу если нужно
        if not self._A_inv_valid:
            self._A_inv = np.linalg.inv(self.A)
            self._A_inv_valid = True
        
        # Решаем систему используя кешированную обратную матрицу
        self.theta = self._A_inv.dot(self.b)
        
        # Предсказанная награда
        predicted_reward = features.dot(self.theta)
        
        # Бонус за исследование
        exploration_bonus = alpha * np.sqrt(
            features.dot(self._A_inv.dot(features))
        )
        
        return predicted_reward + exploration_bonus
    
    def update(self, features: np.ndarray, reward: float):
        """Обновление параметров после получения награды"""
        self.A += np.outer(features, features)
        self.b += features * reward
        self.num_selections += 1
        self.total_reward += reward
        
        # Инвалидируем кеш обратной матрицы
        self._A_inv_valid = False
    
    def get_average_reward(self) -> float:
        """Средняя награда"""
        if self.num_selections == 0:
            return 0.0
        return self.total_reward / self.num_selections
    
    def get_exploration_bonus(self, alpha: float) -> float:
        """Текущий бонус за исследование"""
        if self.theta is None:
            return alpha
        
        # Примерный бонус на единичном векторе
        unit_features = np.ones(self.feature_dim) / np.sqrt(self.feature_dim)
        return alpha * np.sqrt(
            unit_features.dot(np.linalg.solve(self.A, unit_features))
        )


class ContextFeatureExtractor:
    """
    Извлечение признаков из контекста для маршрутизации
    """
    
    def __init__(self):
        self.feature_names = [
            "query_length",
            "has_code",
            "has_data", 
            "complexity_score",
            "domain_technical",
            "domain_creative",
            "requires_memory",
            "requires_tools",
            "user_expertise",
            "conversation_depth"
        ]
        self.feature_dim = len(self.feature_names)
    
    def extract(self, context: Dict[str, Any]) -> np.ndarray:
        """Извлечение вектора признаков из контекста"""
        features = np.zeros(self.feature_dim)
        
        # Базовые признаки запроса
        if "query" in context:
            query = context["query"]
            features[0] = len(query) / 1000.0  # Нормализованная длина
            features[1] = 1.0 if any(kw in query.lower() for kw in ["код", "code", "function", "class"]) else 0.0
            features[2] = 1.0 if any(kw in query.lower() for kw in ["данные", "data", "таблица", "csv"]) else 0.0
        
        # Оценка сложности
        features[3] = context.get("complexity", 0.5)
        
        # Домен задачи
        if "domain" in context:
            features[4] = 1.0 if context["domain"] == "technical" else 0.0
            features[5] = 1.0 if context["domain"] == "creative" else 0.0
        
        # Требования к возможностям
        features[6] = 1.0 if context.get("requires_memory", False) else 0.0
        features[7] = 1.0 if context.get("requires_tools", False) else 0.0
        
        # Характеристики пользователя
        features[8] = context.get("user_expertise", 0.5)
        
        # Глубина разговора
        features[9] = min(context.get("conversation_length", 0) / 20.0, 1.0)
        
        return features