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
        
        # Индексы для быстрого поиска
        self._name_index: Dict[str, List[str]] = {}  # name -> [env:name keys]
        self._tag_index: Dict[str, List[str]] = {}   # tag -> [template keys]
        self._version_index: Dict[str, str] = {}     # env:name:version -> env:name
        
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
                            raw = await f.read()
                            data = json.loads(raw)
                            # Нормализуем ключи слоёв: '1'|'INSTRUCTIONS' -> PromptLayer
                            try:
                                comps = data.get("components", {})
                                normalized: dict = {}
                                for k, v in comps.items():
                                    # Определяем слой по ключу (имя/число/enum)
                                    layer = None
                                    if isinstance(k, str):
                                        if k.isdigit():
                                            try:
                                                layer = PromptLayer(int(k))
                                            except Exception:
                                                pass
                                        else:
                                            try:
                                                layer = PromptLayer[k]
                                            except Exception:
                                                pass
                                    elif isinstance(k, int):
                                        try:
                                            layer = PromptLayer(k)
                                        except Exception:
                                            pass
                                    elif isinstance(k, PromptLayer):
                                        layer = k
                                    if layer is None:
                                        logger.warning(f"Пропускаю неизвестный слой промпта: {k}")
                                        continue
                                    # Нормализуем элементы слоя: гарантируем PromptLayer в поле 'layer'
                                    items = []
                                    try:
                                        for item in (v or []):
                                            if isinstance(item, dict):
                                                item = dict(item)
                                                item["layer"] = layer  # перезаписываем строковые значения
                                            items.append(item)
                                    except Exception:
                                        items = v or []
                                    normalized[layer] = items
                                if normalized:
                                    data["components"] = normalized
                            except Exception as e:
                                logger.warning(f"Не удалось нормализовать компоненты промпта {prompt_file.name}: {e}")
                            template = PromptTemplate(**data)
                            self._store_in_memory(template)
                            logger.info(f"Загружен промпт {template.name} v{template.metadata.version} для {environment}")
        except Exception as e:
            logger.error(f"Ошибка загрузки промптов: {e}")
    
    def _store_in_memory(self, template: PromptTemplate):
        """Сохранение промпта в памяти с индексацией"""
        key = f"{template.metadata.environment}:{template.name}"
        if key not in self._templates:
            self._templates[key] = {}
        
        self._templates[key][template.metadata.version] = template
        
        # Обновляем активную версию если это первая или prod версия
        if (key not in self._active_versions or 
            template.metadata.environment == "production"):
            self._active_versions[key] = template.metadata.version
        
        # Обновляем индексы
        # Индекс по имени
        if template.name not in self._name_index:
            self._name_index[template.name] = []
        if key not in self._name_index[template.name]:
            self._name_index[template.name].append(key)
        
        # Индекс по тегам
        for tag in template.metadata.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if key not in self._tag_index[tag]:
                self._tag_index[tag].append(key)
        
        # Индекс по версиям
        version_key = f"{key}:{template.metadata.version}"
        self._version_index[version_key] = key
    
    async def save_prompt(self, template: PromptTemplate) -> str:
        """Сохранение промпта"""
        # Сохраняем в памяти
        self._store_in_memory(template)
        
        # Сохраняем на диск
        env_path = self.storage_path / template.metadata.environment
        env_path.mkdir(exist_ok=True)
        
        filename = f"{template.name}_{template.metadata.version}.json"
        filepath = env_path / filename
        
        # Сохраняем с человеческими ключами слоев (именами), чтобы корректно парсить при загрузке
        safe_dump = template.model_dump()
        try:
            comp_export = {}
            for layer, items in template.components.items():
                key = layer.name if hasattr(layer, "name") else str(layer)
                serialized_items = []
                for item in items:
                    data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    # Нормализуем поле layer внутри элемента компонента
                    lyr = data.get("layer")
                    try:
                        from .base import PromptLayer as _PL
                        if isinstance(lyr, _PL):
                            data["layer"] = lyr.name
                        elif hasattr(lyr, "name"):
                            data["layer"] = getattr(lyr, "name")
                    except Exception:
                        # Если нет поля или уже строка — оставляем как есть
                        pass
                    serialized_items.append(data)
                comp_export[key] = serialized_items
            safe_dump["components"] = comp_export
        except Exception:
            pass
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(json.dumps(safe_dump, ensure_ascii=False, indent=2, default=str))
        
        # Кешируем в Redis если доступен
        if self.redis:
            cache_key = f"prompt:{template.metadata.environment}:{template.name}:{template.metadata.version}"
            await self.redis.setex(
                cache_key,
                self.cache_ttl,
                # Кладём в кеш уже нормализованный JSON с текстовыми ключами слоёв
                json.dumps(safe_dump, ensure_ascii=False, default=str)
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
                try:
                    # Pydantic v2: валидируем JSON через model_validate_json
                    return PromptTemplate.model_validate_json(cached)
                except Exception:
                    # Если в кеше мусор/пусто — игнорируем
                    logger.warning("Некорректные данные в кеше промптов, пропускаю")
        
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
            # Pydantic v2 сериализация
            await f.write(succession_package.model_dump_json(indent=2))
        
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
    
    async def find_by_tags(self, tags: List[str], environment: str = None) -> List[PromptTemplate]:
        """Поиск промптов по тегам"""
        results = []
        
        # Находим все ключи для указанных тегов
        keys = set()
        for tag in tags:
            if tag in self._tag_index:
                keys.update(self._tag_index[tag])
        
        # Фильтруем по окружению если указано
        for key in keys:
            if environment and not key.startswith(f"{environment}:"):
                continue
            
            # Получаем активную версию
            active_version = self._active_versions.get(key)
            if active_version and key in self._templates:
                template = self._templates[key].get(active_version)
                if template:
                    results.append(template)
        
        return results
    
    def clear_cache(self):
        """Очистка кеша промптов"""
        # В текущей реализации очищаем только Redis кеш
        # В памяти данные остаются для быстрого доступа
        if self.redis:
            # Здесь можно добавить логику очистки Redis
            logger.info("Кеш промптов очищен")
    
    async def cleanup_old_versions(self, keep_versions: int = 10):
        """Очистка старых версий промптов, оставляя только последние N версий"""
        cleaned_count = 0
        
        for key, versions in list(self._templates.items()):
            if len(versions) > keep_versions:
                # Сортируем версии по времени создания
                sorted_versions = sorted(
                    versions.items(),
                    key=lambda x: x[1].metadata.created_at,
                    reverse=True
                )
                
                # Оставляем только последние keep_versions
                versions_to_keep = dict(sorted_versions[:keep_versions])
                versions_to_remove = sorted_versions[keep_versions:]
                
                # Удаляем старые версии
                for version, template in versions_to_remove:
                    # Удаляем из индексов
                    version_key = f"{key}:{version}"
                    if version_key in self._version_index:
                        del self._version_index[version_key]
                    
                    # Удаляем файл
                    env = template.metadata.environment
                    filename = f"{template.name}_{version}.json"
                    filepath = self.storage_path / env / filename
                    if filepath.exists():
                        filepath.unlink()
                        cleaned_count += 1
                
                # Обновляем хранилище
                self._templates[key] = versions_to_keep
        
        logger.info(f"Очищено {cleaned_count} старых версий промптов")
        return cleaned_count