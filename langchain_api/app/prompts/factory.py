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
import yaml
from .base import PromptTemplate, PromptComponent, PromptLayer, PromptMetadata
from datetime import datetime

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
        # Определяем путь хранилища
        from pathlib import Path
        storage = Path(storage_path or settings.PROMPTS_STORAGE_PATH)
        storage.mkdir(parents=True, exist_ok=True)

        manager = PromptManager(
            storage_path=storage,
            redis_client=redis_client
        )
        
        # Запускаем загрузку промптов
        await manager.startup()

        # Если в production нет ни одного промпта — сидируем базовые
        try:
            existing = await manager.list_prompts("production")
            if not existing:
                from .templates.mark_base import (
                    create_mark_base_prompt,
                    create_mark_code_expert_prompt,
                    create_mark_learning_prompt,
                    create_mark_chat_prompt,
                )
                for maker in [
                    create_mark_base_prompt,
                    create_mark_chat_prompt,
                    create_mark_code_expert_prompt,
                    create_mark_learning_prompt,
                ]:
                    prompt = maker()
                    prompt.metadata.environment = "production"
                    await manager.save_prompt(prompt)
                logger.info("🌱 Сидированы базовые промпты в production")

            # Загружаем prompts.yaml если существует (дополняем production)
            yaml_path = Path("/app/langchain_api/prompts/prompts.yaml")
            if yaml_path.exists():
                with open(yaml_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                # Собираем уже существующие имена, чтобы не дублировать
                existing_names = {p["name"] for p in (await manager.list_prompts("production"))}
                for name, data in cfg.items():
                    system_text = (data or {}).get("system", "")
                    if not system_text:
                        continue
                    full_name = f"mark_{name}"
                    if full_name in existing_names:
                        continue
                    metadata = PromptMetadata(
                        id=f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        version="1.0.0",
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                        author="yaml",
                        tags=[name],
                        environment="production",
                    )
                    components = {
                        PromptLayer.INSTRUCTIONS: [
                            PromptComponent(
                                layer=PromptLayer.INSTRUCTIONS,
                                content=system_text,
                                priority=10,
                                dynamic=False,
                            )
                        ]
                    }
                    tpl = PromptTemplate(
                        name=full_name,
                        description=f"Prompt from YAML: {name}",
                        components=components,
                        metadata=metadata,
                        variables={"context": ""},
                    )
                    await manager.save_prompt(tpl)
                logger.info("📥 Загружены промпты из prompts.yaml в production")
        except Exception as e:
            logger.warning(f"Не удалось выполнить автосидинг промптов: {e}")
        
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