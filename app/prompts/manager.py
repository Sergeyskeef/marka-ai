"""
Менеджер промптов с поддержкой версионирования, окружений и эволюции
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pathlib import Path
import asyncio
import aiofiles
from redis.asyncio import Redis
import logging

from .base import (
    PromptTemplate, PromptMetadata, PromptComponent, 
    PromptLayer, PromptEvolutionRecord, PromptSuccessionPackage
)
from ..config import settings

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Централизованный менеджер промптов
    Поддерживает:
    - Версионирование и историю изменений
    - Разделение по окружениям (dev/staging/prod)
    - Кеширование для быстрого доступа
    - A/B тестирование промптов
    - Метрики производительности
    """
    
    def __init__(self, 
                 storage_path: Optional[Path] = None,
                 redis_client: Optional[Redis] = None):
        self.storage_path = storage_path or Path(settings.PROMPTS_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.redis = redis_client
        self.cache_ttl = settings.PROMPTS_CACHE_TTL
        
        # Хранилище промптов в памяти
        self._templates: Dict[str, Dict[str, PromptTemplate]] = {}
        self._active_versions: Dict[str, str] = {}  # name -> active version
        
        # Метрики
        self._usage_stats: Dict[str, Dict[str, Any]] = {}
        
        # Задача загрузки будет запущена извне
        self._load_task = None
    
    async def startup(self):
        """Запуск менеджера - загрузка промптов"""
        if self._load_task is None:
            self._load_task = asyncio.create_task(self._load_all_prompts())
    
    async def shutdown(self):
        """Остановка менеджера"""
        if self._load_task and not self._load_task.done():
            self._load_task.cancel()
            try:
                await self._load_task
            except asyncio.CancelledError:
                pass
    
    async def _load_all_prompts(self):
        """Загрузка всех промптов из хранилища"""
        try:
            for env_dir in self.storage_path.iterdir():
                if env_dir.is_dir():
                    environment = env_dir.name
                    for prompt_file in env_dir.glob("*.json"):
                        async with aiofiles.open(prompt_file, 'r') as f:
                            data = json.loads(await f.read())
                            template = PromptTemplate(**data)
                            self._store_in_memory(template)
                            logger.info(f"Загружен промпт {template.name} v{template.metadata.version} для {environment}")
        except Exception as e:
            logger.error(f"Ошибка загрузки промптов: {e}")
    
    def _store_in_memory(self, template: PromptTemplate):
        """Сохранение промпта в памяти"""
        key = f"{template.metadata.environment}:{template.name}"
        if key not in self._templates:
            self._templates[key] = {}
        
        self._templates[key][template.metadata.version] = template
        
        # Обновляем активную версию если это первая или prod версия
        if (key not in self._active_versions or 
            template.metadata.environment == "production"):
            self._active_versions[key] = template.metadata.version
    
    async def save_prompt(self, template: PromptTemplate) -> str:
        """Сохранение промпта"""
        # Сохраняем в памяти
        self._store_in_memory(template)
        
        # Сохраняем на диск
        env_path = self.storage_path / template.metadata.environment
        env_path.mkdir(exist_ok=True)
        
        filename = f"{template.name}_{template.metadata.version}.json"
        filepath = env_path / filename
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(template.json(indent=2))
        
        # Кешируем в Redis если доступен
        if self.redis:
            cache_key = f"prompt:{template.metadata.environment}:{template.name}:{template.metadata.version}"
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                template.json()
            )
        
        logger.info(f"Сохранен промпт {template.name} v{template.metadata.version}")
        return template.metadata.id
    
    async def get_prompt(self, 
                        name: str,
                        version: Optional[str] = None,
                        environment: str = "production") -> Optional[PromptTemplate]:
        """Получение промпта"""
        # Проверяем кеш Redis
        if self.redis and version:
            cache_key = f"prompt:{environment}:{name}:{version}"
            cached = await self.redis.get(cache_key)
            if cached:
                return PromptTemplate.parse_raw(cached)
        
        # Получаем из памяти
        key = f"{environment}:{name}"
        if key in self._templates:
            if version:
                return self._templates[key].get(version)
            else:
                # Возвращаем активную версию
                active_version = self._active_versions.get(key)
                if active_version:
                    return self._templates[key].get(active_version)
        
        return None
    
    async def list_prompts(self, environment: str = "production") -> List[Dict[str, Any]]:
        """Список всех промптов"""
        prompts = []
        for key, versions in self._templates.items():
            if key.startswith(f"{environment}:"):
                name = key.split(":", 1)[1]
                active_version = self._active_versions.get(key)
                
                prompts.append({
                    "name": name,
                    "environment": environment,
                    "versions": list(versions.keys()),
                    "active_version": active_version,
                    "templates": len(versions)
                })
        
        return prompts
    
    async def promote_prompt(self, 
                            name: str,
                            from_env: str,
                            to_env: str,
                            version: Optional[str] = None) -> str:
        """Продвижение промпта между окружениями"""
        source_prompt = await self.get_prompt(name, version, from_env)
        if not source_prompt:
            raise ValueError(f"Промпт {name} не найден в {from_env}")
        
        # Создаем копию для нового окружения
        promoted = source_prompt.copy(deep=True)
        promoted.metadata.environment = to_env
        promoted.metadata.updated_at = datetime.now()
        promoted.metadata.id = f"{promoted.metadata.id}_promoted_{to_env}"
        
        # Сохраняем
        await self.save_prompt(promoted)
        
        logger.info(f"Промпт {name} продвинут из {from_env} в {to_env}")
        return promoted.metadata.id
    
    async def update_metrics(self, 
                           name: str,
                           version: str,
                           environment: str,
                           metrics: Dict[str, float]):
        """Обновление метрик производительности промпта"""
        template = await self.get_prompt(name, version, environment)
        if template:
            template.metadata.performance_metrics.update(metrics)
            await self.save_prompt(template)
            
            # Обновляем статистику использования
            key = f"{environment}:{name}:{version}"
            if key not in self._usage_stats:
                self._usage_stats[key] = {
                    "count": 0,
                    "total_tokens": 0,
                    "avg_latency": 0,
                    "errors": 0
                }
            
            stats = self._usage_stats[key]
            stats["count"] += 1
            stats["total_tokens"] += metrics.get("tokens_used", 0)
            
            # Обновляем среднюю задержку
            if "latency" in metrics:
                stats["avg_latency"] = (
                    (stats["avg_latency"] * (stats["count"] - 1) + metrics["latency"]) 
                    / stats["count"]
                )
            
            if metrics.get("error", False):
                stats["errors"] += 1
    
    async def evolve_prompt(self, 
                          name: str,
                          version: str,
                          environment: str,
                          succession_package: PromptSuccessionPackage) -> str:
        """Эволюция промпта на основе пакета преемственности"""
        current = await self.get_prompt(name, version, environment)
        if not current:
            raise ValueError(f"Промпт {name} v{version} не найден")
        
        # Генерируем преемника
        successor = succession_package.generate_successor_prompt(current)
        
        # Сохраняем историю эволюции
        evolution_path = self.storage_path / "evolution" / name
        evolution_path.mkdir(parents=True, exist_ok=True)
        
        evolution_file = evolution_path / f"gen_{succession_package.evolution_record.generation}.json"
        async with aiofiles.open(evolution_file, 'w') as f:
            await f.write(succession_package.json(indent=2))
        
        # Сохраняем новый промпт
        await self.save_prompt(successor)
        
        logger.info(f"Промпт {name} эволюционировал до v{successor.metadata.version}")
        return successor.metadata.id
    
    async def rollback_prompt(self, 
                            name: str,
                            to_version: str,
                            environment: str) -> str:
        """Откат к предыдущей версии промпта"""
        key = f"{environment}:{name}"
        if key in self._templates and to_version in self._templates[key]:
            self._active_versions[key] = to_version
            logger.info(f"Промпт {name} откачен к версии {to_version}")
            return to_version
        else:
            raise ValueError(f"Версия {to_version} не найдена для {name}")
    
    async def get_prompt_history(self, 
                               name: str,
                               environment: str) -> List[Dict[str, Any]]:
        """История версий промпта"""
        key = f"{environment}:{name}"
        if key not in self._templates:
            return []
        
        history = []
        for version, template in self._templates[key].items():
            history.append({
                "version": version,
                "created_at": template.metadata.created_at.isoformat(),
                "updated_at": template.metadata.updated_at.isoformat(),
                "author": template.metadata.author,
                "parent_id": template.metadata.parent_id,
                "performance": template.metadata.performance_metrics,
                "tokens": template.estimate_tokens()
            })
        
        return sorted(history, key=lambda x: x["created_at"], reverse=True)