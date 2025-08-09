"""
API endpoints для управления системой промптов
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ..prompts import PromptSystemFactory
from ..prompts.base import PromptTemplate, PromptComponent, PromptLayer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])

# Глобальная система промптов (инициализируется при старте)
_prompt_system: Optional[Dict[str, Any]] = None


class PromptCreateRequest(BaseModel):
    """Запрос на создание промпта"""
    name: str = Field(..., description="Имя промпта")
    description: str = Field(..., description="Описание промпта")
    components: Dict[str, List[Dict[str, Any]]] = Field(..., description="Компоненты промпта")
    environment: str = Field("development", description="Окружение")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Переменные по умолчанию")


class PromptUpdateRequest(BaseModel):
    """Запрос на обновление промпта"""
    description: Optional[str] = None
    components: Optional[Dict[str, List[Dict[str, Any]]]] = None
    variables: Optional[Dict[str, Any]] = None


class PromptResponse(BaseModel):
    """Ответ с информацией о промпте"""
    id: str
    name: str
    description: str
    version: str
    environment: str
    created_at: datetime
    updated_at: datetime
    author: str
    parent_id: Optional[str] = None
    performance_metrics: Dict[str, float]
    estimated_tokens: int


class PromptListResponse(BaseModel):
    """Список промптов"""
    prompts: List[Dict[str, Any]]
    total: int


class PromptStatsResponse(BaseModel):
    """Статистика по промптам"""
    total_prompts: int
    environments: Dict[str, int]
    routing_stats: Dict[str, Any]
    evolution_stats: Dict[str, Any]


async def get_prompt_system() -> Dict[str, Any]:
    """Получить систему промптов"""
    global _prompt_system
    if _prompt_system is None:
        _prompt_system = await PromptSystemFactory.create_system()
    return _prompt_system


@router.get("/", response_model=PromptListResponse)
async def list_prompts(
    environment: str = Query("production", description="Окружение"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Получить список всех промптов"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        all_prompts = await manager.list_prompts(environment)
        
        # Пагинация
        total = len(all_prompts)
        prompts = all_prompts[offset:offset + limit]
        
        return PromptListResponse(
            prompts=prompts,
            total=total
        )
    except Exception as e:
        logger.error(f"Ошибка получения списка промптов: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}", response_model=PromptResponse)
async def get_prompt(
    name: str,
    version: Optional[str] = Query(None, description="Версия промпта"),
    environment: str = Query("production", description="Окружение")
):
    """Получить конкретный промпт"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        prompt = await manager.get_prompt(name, version, environment)
        if not prompt:
            raise HTTPException(status_code=404, detail="Промпт не найден")
        
        return PromptResponse(
            id=prompt.metadata.id,
            name=prompt.name,
            description=prompt.description,
            version=prompt.metadata.version,
            environment=prompt.metadata.environment,
            created_at=prompt.metadata.created_at,
            updated_at=prompt.metadata.updated_at,
            author=prompt.metadata.author,
            parent_id=prompt.metadata.parent_id,
            performance_metrics=prompt.metadata.performance_metrics,
            estimated_tokens=prompt.estimate_tokens()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения промпта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=PromptResponse)
async def create_prompt(request: PromptCreateRequest):
    """Создать новый промпт"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        # Создаем компоненты
        components = {}
        for layer_name, component_list in request.components.items():
            layer = PromptLayer[layer_name]
            components[layer] = []
            
            for comp_data in component_list:
                component = PromptComponent(
                    layer=layer,
                    content=comp_data["content"],
                    priority=comp_data.get("priority", 5),
                    dynamic=comp_data.get("dynamic", False)
                )
                components[layer].append(component)
        
        # Создаем метаданные
        from uuid import uuid4
        metadata = {
            "id": f"{request.name}_{uuid4().hex[:8]}",
            "version": "1.0.0",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "author": "api",
            "environment": request.environment
        }
        
        # Создаем промпт
        from ..prompts.base import PromptMetadata
        prompt = PromptTemplate(
            name=request.name,
            description=request.description,
            components=components,
            metadata=PromptMetadata(**metadata),
            variables=request.variables
        )
        
        # Сохраняем
        prompt_id = await manager.save_prompt(prompt)
        
        # Запускаем мониторинг эволюции
        if system.get("evolution"):
            await system["evolution"].start_monitoring(request.name, request.environment)
        
        return PromptResponse(
            id=prompt_id,
            name=prompt.name,
            description=prompt.description,
            version=prompt.metadata.version,
            environment=prompt.metadata.environment,
            created_at=prompt.metadata.created_at,
            updated_at=prompt.metadata.updated_at,
            author=prompt.metadata.author,
            parent_id=None,
            performance_metrics={},
            estimated_tokens=prompt.estimate_tokens()
        )
    except Exception as e:
        logger.error(f"Ошибка создания промпта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{name}")
async def update_prompt(
    name: str,
    request: PromptUpdateRequest,
    version: Optional[str] = Query(None),
    environment: str = Query("development")
):
    """Обновить существующий промпт"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        # Получаем текущий промпт
        current = await manager.get_prompt(name, version, environment)
        if not current:
            raise HTTPException(status_code=404, detail="Промпт не найден")
        
        # Обновляем поля
        if request.description is not None:
            current.description = request.description
        
        if request.components is not None:
            # Обновляем компоненты
            for layer_name, component_list in request.components.items():
                layer = PromptLayer[layer_name]
                current.components[layer] = []
                
                for comp_data in component_list:
                    component = PromptComponent(
                        layer=layer,
                        content=comp_data["content"],
                        priority=comp_data.get("priority", 5),
                        dynamic=comp_data.get("dynamic", False)
                    )
                    current.components[layer].append(component)
        
        if request.variables is not None:
            current.variables.update(request.variables)
        
        # Обновляем метаданные
        current.metadata.updated_at = datetime.now()
        
        # Сохраняем
        await manager.save_prompt(current)
        
        return {"message": "Промпт обновлен", "id": current.metadata.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления промпта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/promote")
async def promote_prompt(
    name: str,
    from_env: str = Query(..., description="Исходное окружение"),
    to_env: str = Query(..., description="Целевое окружение"),
    version: Optional[str] = Query(None)
):
    """Продвинуть промпт в другое окружение"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        promoted_id = await manager.promote_prompt(name, from_env, to_env, version)
        
        return {
            "message": f"Промпт {name} продвинут из {from_env} в {to_env}",
            "id": promoted_id
        }
    except Exception as e:
        logger.error(f"Ошибка продвижения промпта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/rollback")
async def rollback_prompt(
    name: str,
    to_version: str = Query(..., description="Версия для отката"),
    environment: str = Query("production")
):
    """Откатить промпт к предыдущей версии"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        rolled_back = await manager.rollback_prompt(name, to_version, environment)
        
        return {
            "message": f"Промпт {name} откачен к версии {to_version}",
            "version": rolled_back
        }
    except Exception as e:
        logger.error(f"Ошибка отката промпта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/history")
async def get_prompt_history(
    name: str,
    environment: str = Query("production"),
    limit: int = Query(50, ge=1, le=200)
):
    """Получить историю версий промпта"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        history = await manager.get_prompt_history(name, environment)
        
        # Ограничиваем количество
        history = history[:limit]
        
        return {
            "prompt_name": name,
            "environment": environment,
            "history": history,
            "total_versions": len(history)
        }
    except Exception as e:
        logger.error(f"Ошибка получения истории: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/overview", response_model=PromptStatsResponse)
async def get_prompts_stats():
    """Получить общую статистику по промптам"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        router = system["router"]
        evolution = system["evolution"]
        
        # Собираем статистику
        all_envs = ["development", "staging", "production"]
        env_counts = {}
        total_prompts = 0
        
        for env in all_envs:
            prompts = await manager.list_prompts(env)
            count = len(prompts)
            env_counts[env] = count
            total_prompts += count
        
        # Статистика роутера
        routing_stats = await router.get_routing_stats()
        
        # Статистика эволюций
        evolution_stats = await evolution.get_evolution_stats()
        
        return PromptStatsResponse(
            total_prompts=total_prompts,
            environments=env_counts,
            routing_stats=routing_stats,
            evolution_stats=evolution_stats
        )
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/metrics")
async def update_prompt_metrics(
    name: str,
    metrics: Dict[str, float] = Body(...),
    version: Optional[str] = Query(None),
    environment: str = Query("production")
):
    """Обновить метрики производительности промпта"""
    try:
        system = await get_prompt_system()
        manager = system["manager"]
        
        await manager.update_metrics(name, version, environment, metrics)
        
        return {"message": "Метрики обновлены", "metrics": metrics}
    except Exception as e:
        logger.error(f"Ошибка обновления метрик: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/router/select")
async def select_prompt_via_router(
    context: Dict[str, Any] = Body(..., description="Контекст для выбора промпта")
):
    """Выбрать оптимальный промпт через роутер"""
    try:
        system = await get_prompt_system()
        router = system["router"]
        
        selected, confidence = await router.select_prompt(context)
        
        return {
            "selected_prompt": {
                "name": selected.name,
                "version": selected.metadata.version,
                "description": selected.description
            },
            "confidence": confidence,
            "context": context
        }
    except Exception as e:
        logger.error(f"Ошибка выбора промпта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Функция для регистрации в основном приложении
def register_prompts_api(app):
    """Регистрация API промптов в приложении FastAPI"""
    app.include_router(router)