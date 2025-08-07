"""
Vector Search Tools - инструменты для векторного поиска в памяти
"""

import json
import logging
from typing import List, Optional

from app.memory.vector_search import vector_search_engine
from core.memory.memory_manager import memory_manager
from .tools import register_tool, format_tool_result, format_tool_error

logger = logging.getLogger(__name__)


@register_tool()
async def vector_search_memory(
    query: str,
    memory_type: Optional[str] = None,
    limit: int = 10,
    threshold: float = 0.7
) -> str:
    """
    Выполнить векторный поиск по памяти
    
    Args:
        query: Поисковый запрос
        memory_type: Тип памяти для поиска (Fact/Episode/Skill) или None для всех
        limit: Максимальное количество результатов
        threshold: Минимальный порог сходства (0-1)
    """
    try:
        logger.info(f"🔍 Векторный поиск: '{query}' (type: {memory_type}, threshold: {threshold})")
        
        # Получаем все элементы памяти
        all_items = await memory_manager.search_episodes("", limit=1000)
        candidates = all_items.get("items", [])
        
        # Фильтруем по типу если указан
        if memory_type:
            candidates = [
                item for item in candidates
                if item.get("metadata", {}).get("type") == memory_type
            ]
        
        # Выполняем векторный поиск
        results = await vector_search_engine.vector_search(
            query=query,
            candidates=candidates,
            top_k=limit,
            threshold=threshold
        )
        
        # Форматируем результаты
        formatted_results = []
        for result in results:
            metadata = result.get("metadata", {})
            formatted_results.append({
                "type": metadata.get("type", "unknown"),
                "text": result.get("text", ""),
                "similarity": round(result["similarity_score"], 3),
                "id": metadata.get("id"),
                "metadata": {
                    k: v for k, v in metadata.items()
                    if k not in ["embedding", "text", "id", "type"]
                }
            })
        
        return json.dumps({
            "found": len(formatted_results),
            "results": formatted_results,
            "query": query,
            "search_type": "vector"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в vector_search_memory: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def hybrid_search_memory(
    query: str,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    limit: int = 10
) -> str:
    """
    Выполнить гибридный поиск (векторный + текстовый) по памяти
    
    Args:
        query: Поисковый запрос
        vector_weight: Вес векторного поиска (0-1)
        text_weight: Вес текстового поиска (0-1)
        limit: Максимальное количество результатов
    """
    try:
        logger.info(f"🔍 Гибридный поиск: '{query}' (v:{vector_weight}, t:{text_weight})")
        
        # Получаем кандидатов
        all_items = await memory_manager.search_episodes("", limit=1000)
        candidates = all_items.get("items", [])
        
        # Выполняем гибридный поиск
        results = await vector_search_engine.hybrid_search(
            query=query,
            candidates=candidates,
            text_field="text",
            vector_weight=vector_weight,
            text_weight=text_weight,
            top_k=limit
        )
        
        # Форматируем результаты
        formatted_results = []
        for result in results:
            metadata = result.get("metadata", {})
            formatted_results.append({
                "type": metadata.get("type", "unknown"),
                "text": result.get("text", ""),
                "scores": {
                    "hybrid": round(result["hybrid_score"], 3),
                    "vector": round(result["vector_score"], 3),
                    "text": round(result["text_score"], 3)
                },
                "id": metadata.get("id")
            })
        
        return json.dumps({
            "found": len(formatted_results),
            "results": formatted_results,
            "query": query,
            "search_type": "hybrid",
            "weights": {
                "vector": vector_weight,
                "text": text_weight
            }
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в hybrid_search_memory: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def find_similar_memories(
    reference_id: str,
    limit: int = 5
) -> str:
    """
    Найти воспоминания, похожие на указанное
    
    Args:
        reference_id: ID эталонного воспоминания
        limit: Количество похожих для поиска
    """
    try:
        logger.info(f"🔍 Поиск похожих на: {reference_id}")
        
        # Получаем все элементы
        all_items = await memory_manager.search_episodes("", limit=1000)
        candidates = all_items.get("items", [])
        
        # Находим эталонное воспоминание
        reference = None
        for item in candidates:
            if item.get("metadata", {}).get("id") == reference_id:
                reference = item
                break
        
        if not reference:
            return json.dumps({
                "success": False,
                "error": f"Воспоминание {reference_id} не найдено"
            }, ensure_ascii=False)
        
        # Получаем embedding эталона
        reference_embedding = (
            reference.get("embedding") or
            reference.get("metadata", {}).get("embedding")
        )
        
        if not reference_embedding:
            return json.dumps({
                "success": False,
                "error": "У эталонного воспоминания нет векторного представления"
            }, ensure_ascii=False)
        
        # Ищем похожие
        similar = await vector_search_engine.find_similar(
            reference_embedding=reference_embedding,
            candidates=candidates,
            top_k=limit + 1,  # +1 так как сам эталон тоже будет в результатах
            exclude_ids=[reference_id]
        )
        
        # Форматируем результаты
        formatted_results = []
        for result in similar[:limit]:  # Берем только limit результатов
            metadata = result.get("metadata", {})
            formatted_results.append({
                "type": metadata.get("type", "unknown"),
                "text": result.get("text", ""),
                "similarity": round(result["similarity_score"], 3),
                "id": metadata.get("id"),
                "key_info": {
                    "subject": metadata.get("subject"),
                    "outcome": metadata.get("outcome"),
                    "lesson": metadata.get("lesson_learned")
                }
            })
        
        return json.dumps({
            "success": True,
            "reference": {
                "id": reference_id,
                "text": reference.get("text", "")[:100] + "..."
            },
            "similar_count": len(formatted_results),
            "similar_memories": formatted_results
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в find_similar_memories: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def update_memory_embeddings(
    memory_type: Optional[str] = None,
    force: bool = False
) -> str:
    """
    Обновить векторные представления для воспоминаний
    
    Args:
        memory_type: Тип памяти для обновления или None для всех
        force: Принудительное обновление даже если embedding уже есть
    """
    try:
        logger.info(f"🔄 Обновление embeddings (type: {memory_type}, force: {force})")
        
        # Получаем элементы для обновления
        all_items = await memory_manager.search_episodes("", limit=1000)
        items = all_items.get("items", [])
        
        # Фильтруем по типу
        if memory_type:
            items = [
                item for item in items
                if item.get("metadata", {}).get("type") == memory_type
            ]
        
        # Обновляем embeddings
        updated = await vector_search_engine.update_embeddings(
            items=items,
            text_field="text",
            force_update=force
        )
        
        # TODO: Сохранить обновленные embeddings обратно в Graphiti
        
        return json.dumps({
            "success": True,
            "total_items": len(items),
            "updated": updated,
            "message": f"Обновлено {updated} из {len(items)} элементов"
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в update_memory_embeddings: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


@register_tool()
async def analyze_memory_clusters() -> str:
    """
    Анализировать кластеры в памяти для выявления паттернов
    """
    try:
        logger.info("📊 Анализ кластеров памяти")
        
        # Получаем все элементы с embeddings
        all_items = await memory_manager.search_episodes("", limit=500)
        items_with_embeddings = []
        
        for item in all_items.get("items", []):
            embedding = (
                item.get("embedding") or
                item.get("metadata", {}).get("embedding")
            )
            if embedding:
                items_with_embeddings.append(item)
        
        if len(items_with_embeddings) < 10:
            return json.dumps({
                "success": False,
                "message": "Недостаточно данных для кластерного анализа"
            }, ensure_ascii=False)
        
        # Простой анализ: находим плотные группы
        clusters = []
        analyzed = set()
        
        for i, item in enumerate(items_with_embeddings):
            if i in analyzed:
                continue
                
            # Находим похожие элементы
            item_embedding = (
                item.get("embedding") or
                item.get("metadata", {}).get("embedding")
            )
            
            similar = await vector_search_engine.find_similar(
                reference_embedding=item_embedding,
                candidates=items_with_embeddings,
                top_k=10,
                exclude_ids=[item.get("metadata", {}).get("id")]
            )
            
            # Если есть достаточно похожих - это кластер
            high_similarity = [s for s in similar if s["similarity_score"] > 0.85]
            if len(high_similarity) >= 3:
                cluster_items = [item] + high_similarity[:5]
                clusters.append({
                    "size": len(cluster_items),
                    "avg_similarity": sum(s["similarity_score"] for s in high_similarity) / len(high_similarity),
                    "sample_texts": [it.get("text", "")[:100] for it in cluster_items[:3]],
                    "types": list(set(it.get("metadata", {}).get("type", "unknown") for it in cluster_items))
                })
                
                # Помечаем как проанализированные
                for it in cluster_items:
                    idx = items_with_embeddings.index(it)
                    analyzed.add(idx)
        
        return json.dumps({
            "success": True,
            "total_memories": len(items_with_embeddings),
            "clusters_found": len(clusters),
            "clusters": clusters[:5],  # Топ-5 кластеров
            "insights": [
                f"Найдено {len(clusters)} тематических групп в памяти",
                f"Самый большой кластер содержит {max(c['size'] for c in clusters) if clusters else 0} элементов",
                "Рекомендуется изучить кластеры для выявления паттернов"
            ]
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в analyze_memory_clusters: {e}")
        return json.dumps(format_tool_error(e), ensure_ascii=False)


# Экспортируем инструменты векторного поиска
VECTOR_SEARCH_TOOLS = [
    vector_search_memory,
    hybrid_search_memory,
    find_similar_memories,
    update_memory_embeddings,
    analyze_memory_clusters
]