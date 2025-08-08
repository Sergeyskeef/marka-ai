"""
Система эволюции промптов на основе Agent Lineage Evolution (ALE)
Автоматическая эволюция и наследование оптимизаций
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio
import logging
from dataclasses import dataclass

from .base import (
    PromptTemplate, PromptComponent, PromptLayer,
    PromptEvolutionRecord, PromptSuccessionPackage
)
from .manager import PromptManager

logger = logging.getLogger(__name__)


@dataclass
class EvolutionTrigger:
    """Условие для запуска эволюции промпта"""
    name: str
    check_function: callable
    threshold: Any
    description: str


class PromptEvolution:
    """
    Система автоматической эволюции промптов
    
    Основные принципы:
    - Проактивная замена до деградации
    - Behavioral inheritance между поколениями
    - Автоматическая генерация промптов-преемников
    - Мониторинг когнитивного состояния
    """
    
    def __init__(self, prompt_manager: PromptManager):
        self.prompt_manager = prompt_manager
        
        # Триггеры эволюции
        self.triggers = self._initialize_triggers()
        
        # Мониторинг активных промптов
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        
        # История эволюций
        self.evolution_history: List[PromptEvolutionRecord] = []
        
    def _initialize_triggers(self) -> List[EvolutionTrigger]:
        """Инициализация триггеров эволюции"""
        return [
            EvolutionTrigger(
                name="context_usage",
                check_function=lambda stats: stats.get("context_usage", 0) > 0.75,
                threshold=0.75,
                description="Использование контекста превышает 75%"
            ),
            EvolutionTrigger(
                name="interaction_count",
                check_function=lambda stats: stats.get("interactions", 0) > 15,
                threshold=15,
                description="Количество взаимодействий превышает 15"
            ),
            EvolutionTrigger(
                name="quality_degradation",
                check_function=lambda stats: stats.get("avg_quality", 10) < 6,
                threshold=6,
                description="Среднее качество ответов ниже 6/10"
            ),
            EvolutionTrigger(
                name="error_rate",
                check_function=lambda stats: stats.get("error_rate", 0) > 0.2,
                threshold=0.2,
                description="Частота ошибок превышает 20%"
            ),
            EvolutionTrigger(
                name="response_time",
                check_function=lambda stats: stats.get("avg_latency", 0) > 5000,
                threshold=5000,
                description="Средняя задержка превышает 5 секунд"
            )
        ]
    
    async def start_monitoring(self, 
                             prompt_name: str,
                             environment: str = "production"):
        """Запуск мониторинга промпта"""
        key = f"{environment}:{prompt_name}"
        
        if key in self.monitoring_tasks:
            logger.warning(f"Мониторинг для {key} уже запущен")
            return
        
        task = asyncio.create_task(
            self._monitor_prompt(prompt_name, environment)
        )
        self.monitoring_tasks[key] = task
        
        logger.info(f"Запущен мониторинг для {key}")
    
    async def stop_monitoring(self, 
                            prompt_name: str,
                            environment: str = "production"):
        """Остановка мониторинга промпта"""
        key = f"{environment}:{prompt_name}"
        
        if key in self.monitoring_tasks:
            self.monitoring_tasks[key].cancel()
            del self.monitoring_tasks[key]
            logger.info(f"Остановлен мониторинг для {key}")
    
    async def _monitor_prompt(self, 
                            prompt_name: str,
                            environment: str):
        """Мониторинг состояния промпта"""
        while True:
            try:
                # Проверяем каждые 60 секунд
                await asyncio.sleep(60)
                
                # Получаем текущую статистику
                stats = await self._collect_prompt_stats(prompt_name, environment)
                
                # Проверяем триггеры
                triggered = await self._check_triggers(stats)
                
                if triggered:
                    logger.info(f"Триггеры сработали для {prompt_name}: {[t.name for t in triggered]}")
                    
                    # Запускаем эволюцию
                    await self.evolve_prompt(
                        prompt_name,
                        environment,
                        triggered[0].description  # Используем первый триггер как причину
                    )
                    
                    # Останавливаем мониторинг старой версии
                    break
                    
            except asyncio.CancelledError:
                logger.info(f"Мониторинг {prompt_name} отменен")
                break
            except Exception as e:
                logger.error(f"Ошибка мониторинга {prompt_name}: {e}")
                await asyncio.sleep(300)  # Ждем 5 минут при ошибке
    
    async def _collect_prompt_stats(self, 
                                  prompt_name: str,
                                  environment: str) -> Dict[str, Any]:
        """Сбор статистики по промпту"""
        # Получаем историю промпта
        history = await self.prompt_manager.get_prompt_history(prompt_name, environment)
        
        if not history:
            return {}
        
        latest = history[0]
        performance = latest.get("performance", {})
        
        # Базовая статистика
        stats = {
            "version": latest["version"],
            "context_usage": performance.get("context_usage", 0),
            "interactions": performance.get("interaction_count", 0),
            "avg_quality": performance.get("quality_score", 10),
            "error_rate": performance.get("error_rate", 0),
            "avg_latency": performance.get("avg_latency", 0),
            "tokens": latest.get("tokens", 0)
        }
        
        return stats
    
    async def _check_triggers(self, 
                            stats: Dict[str, Any]) -> List[EvolutionTrigger]:
        """Проверка триггеров эволюции"""
        triggered = []
        
        for trigger in self.triggers:
            if trigger.check_function(stats):
                triggered.append(trigger)
        
        return triggered
    
    async def evolve_prompt(self, 
                          prompt_name: str,
                          environment: str,
                          trigger_reason: str) -> str:
        """Выполнить эволюцию промпта"""
        # Получаем текущий промпт
        current = await self.prompt_manager.get_prompt(prompt_name, environment=environment)
        if not current:
            raise ValueError(f"Промпт {prompt_name} не найден")
        
        # Анализируем историю для извлечения паттернов
        analysis = await self._analyze_prompt_history(prompt_name, environment)
        
        # Создаем запись эволюции
        evolution_record = PromptEvolutionRecord(
            generation=self._get_next_generation(current),
            trigger_reason=trigger_reason,
            cognitive_state=analysis["cognitive_state"],
            performance_delta=analysis["performance_delta"],
            inherited_strategies=analysis["effective_strategies"],
            learned_failures=analysis["failures"],
            successor_guidance=self._generate_successor_guidance(analysis),
            timestamp=datetime.now()
        )
        
        # Создаем пакет преемственности
        succession_package = PromptSuccessionPackage(
            parent_prompt_id=current.metadata.id,
            evolution_record=evolution_record,
            effective_components=self._extract_effective_components(current, analysis),
            deprecated_components=self._extract_deprecated_components(current, analysis),
            context_distillation=analysis["context_summary"],
            user_profile_updates=analysis.get("user_profile", {}),
            performance_insights=analysis["insights"]
        )
        
        # Эволюционируем промпт
        new_id = await self.prompt_manager.evolve_prompt(
            prompt_name,
            current.metadata.version,
            environment,
            succession_package
        )
        
        # Запускаем мониторинг новой версии
        await self.start_monitoring(prompt_name, environment)
        
        # Сохраняем в историю
        self.evolution_history.append(evolution_record)
        
        logger.info(f"Промпт {prompt_name} эволюционировал: {trigger_reason}")
        
        return new_id
    
    def _get_next_generation(self, prompt: PromptTemplate) -> int:
        """Получение номера следующего поколения"""
        # Извлекаем из версии если есть
        parts = prompt.metadata.version.split(".")
        if len(parts) > 2:
            try:
                return int(parts[-1]) + 1
            except ValueError:
                pass
        return 1
    
    async def _analyze_prompt_history(self, 
                                    prompt_name: str,
                                    environment: str) -> Dict[str, Any]:
        """Анализ истории промпта для извлечения паттернов"""
        history = await self.prompt_manager.get_prompt_history(prompt_name, environment)
        
        if not history:
            return self._default_analysis()
        
        # Анализируем тренды производительности
        performance_metrics = [h.get("performance", {}) for h in history]
        
        # Определяем эффективные стратегии
        effective_strategies = []
        failures = []
        
        for i, metrics in enumerate(performance_metrics):
            if metrics.get("quality_score", 0) > 8:
                effective_strategies.append(f"Версия {history[i]['version']}: высокое качество")
            elif metrics.get("error_rate", 0) > 0.3:
                failures.append(f"Версия {history[i]['version']}: высокая частота ошибок")
        
        # Вычисляем когнитивное состояние
        latest_quality = performance_metrics[0].get("quality_score", 7) if performance_metrics else 7
        cognitive_state = min(max(latest_quality, 1), 10)
        
        # Дельта производительности
        if len(performance_metrics) > 1:
            performance_delta = {
                k: performance_metrics[0].get(k, 0) - performance_metrics[-1].get(k, 0)
                for k in ["quality_score", "error_rate", "avg_latency"]
            }
        else:
            performance_delta = {}
        
        return {
            "cognitive_state": cognitive_state,
            "performance_delta": performance_delta,
            "effective_strategies": effective_strategies,
            "failures": failures,
            "context_summary": f"Промпт прошел {len(history)} итераций",
            "insights": {
                "total_versions": len(history),
                "avg_lifespan": self._calculate_avg_lifespan(history),
                "trend": "improving" if performance_delta.get("quality_score", 0) > 0 else "degrading"
            }
        }
    
    def _default_analysis(self) -> Dict[str, Any]:
        """Анализ по умолчанию для нового промпта"""
        return {
            "cognitive_state": 7.0,
            "performance_delta": {},
            "effective_strategies": ["Базовая конфигурация"],
            "failures": [],
            "context_summary": "Первое поколение промпта",
            "insights": {
                "total_versions": 1,
                "avg_lifespan": 0,
                "trend": "new"
            }
        }
    
    def _calculate_avg_lifespan(self, history: List[Dict[str, Any]]) -> float:
        """Расчет средней продолжительности жизни версий"""
        if len(history) < 2:
            return 0
        
        lifespans = []
        for i in range(len(history) - 1):
            created = datetime.fromisoformat(history[i+1]["created_at"])
            updated = datetime.fromisoformat(history[i]["created_at"])
            lifespan = (updated - created).total_seconds() / 3600  # В часах
            lifespans.append(lifespan)
        
        return sum(lifespans) / len(lifespans) if lifespans else 0
    
    def _generate_successor_guidance(self, analysis: Dict[str, Any]) -> str:
        """Генерация руководства для преемника"""
        guidance_parts = [
            "РУКОВОДСТВО ДЛЯ ПРЕЕМНИКА:",
            f"Когнитивное состояние предшественника: {analysis['cognitive_state']}/10"
        ]
        
        if analysis["effective_strategies"]:
            guidance_parts.append(
                f"Сохраните эффективные стратегии: {', '.join(analysis['effective_strategies'])}"
            )
        
        if analysis["failures"]:
            guidance_parts.append(
                f"Избегайте ошибок предшественника: {', '.join(analysis['failures'])}"
            )
        
        if analysis["insights"]["trend"] == "degrading":
            guidance_parts.append(
                "ВНИМАНИЕ: Наблюдается деградация производительности. Требуется усиленный контроль."
            )
        
        return "\n".join(guidance_parts)
    
    def _extract_effective_components(self, 
                                    prompt: PromptTemplate,
                                    analysis: Dict[str, Any]) -> List[PromptComponent]:
        """Извлечение эффективных компонентов для наследования"""
        effective = []
        
        # Сохраняем компоненты с высоким приоритетом
        for layer, components in prompt.components.items():
            for component in components:
                if component.priority >= 8:  # Высокоприоритетные
                    effective.append(component)
                elif layer in [PromptLayer.INSTRUCTIONS, PromptLayer.TOOL_DEFINITIONS]:
                    # Всегда сохраняем базовые инструкции и инструменты
                    effective.append(component)
        
        return effective
    
    def _extract_deprecated_components(self, 
                                     prompt: PromptTemplate,
                                     analysis: Dict[str, Any]) -> List[PromptComponent]:
        """Извлечение устаревших компонентов для удаления"""
        deprecated = []
        
        # Помечаем компоненты на удаление на основе анализа
        if analysis["cognitive_state"] < 5:
            # При низком когнитивном состоянии удаляем сложные компоненты
            for components in prompt.components.values():
                for component in components:
                    if "сложн" in component.content.lower() or len(component.content) > 1000:
                        deprecated.append(component)
        
        return deprecated
    
    async def get_evolution_stats(self) -> Dict[str, Any]:
        """Статистика эволюций"""
        return {
            "total_evolutions": len(self.evolution_history),
            "active_monitors": len(self.monitoring_tasks),
            "recent_evolutions": [
                {
                    "generation": record.generation,
                    "trigger": record.trigger_reason,
                    "cognitive_state": record.cognitive_state,
                    "timestamp": record.timestamp.isoformat()
                }
                for record in self.evolution_history[-5:]
            ],
            "triggers": [
                {
                    "name": trigger.name,
                    "threshold": trigger.threshold,
                    "description": trigger.description
                }
                for trigger in self.triggers
            ]
        }