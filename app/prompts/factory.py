"""
Фабрика для создания и инициализации системы промптов
"""

import logging
from typing import Optional
from pathlib import Path
from redis.asyncio import Redis

from .manager import PromptManager
from .router import DynamicPromptRouter
from .evolution import PromptEvolution
from .context_architect import ContextArchitect
from ..config import settings

logger = logging.getLogger(__name__)


class PromptSystemFactory:
    """Фабрика для создания компонентов системы промптов"""
    
    @staticmethod
    async def create_system(
        redis_client: Optional[Redis] = None,
        storage_path: Optional[Path] = None
    ) -> dict:
        """
        Создает и инициализирует всю систему промптов
        
        Returns:
            dict с компонентами:
            - manager: PromptManager
            - router: DynamicPromptRouter
            - evolution: PromptEvolution
            - architect: ContextArchitect
        """
        # Создаем менеджер
        manager = PromptManager(
            storage_path=storage_path,
            redis_client=redis_client
        )
        
        # Запускаем загрузку промптов
        await manager.startup()
        
        # Создаем роутер
        router = DynamicPromptRouter(
            prompt_manager=manager,
            alpha=settings.PROMPTS_ROUTER_ALPHA,
            budget_aware=True
        )
        
        # Создаем систему эволюции
        evolution = PromptEvolution(prompt_manager=manager)
        
        # Создаем архитектора контекста
        architect = ContextArchitect(
            max_context_tokens=settings.PROMPTS_MAX_CONTEXT_TOKENS
        )
        
        logger.info("✅ Система промптов инициализирована")
        
        return {
            "manager": manager,
            "router": router,
            "evolution": evolution,
            "architect": architect
        }
    
    @staticmethod
    async def shutdown_system(components: dict):
        """Корректное завершение работы системы"""
        manager = components.get("manager")
        evolution = components.get("evolution")
        
        if evolution:
            # Останавливаем все мониторы
            for key in list(evolution.monitoring_tasks.keys()):
                env, name = key.split(":", 1)
                await evolution.stop_monitoring(name, env)
        
        if manager:
            await manager.shutdown()
        
        logger.info("✅ Система промптов остановлена")