"""
Модуль для работы с ошибками (Mistake) и инсайтами (Insight)
Часть системы самоанализа проекта Марк
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from core.memory.schema import Mistake, Insight, CausedError, ResolvedBy
from core.memory.graphiti_adapter import GraphitiMemoryAdapter

logger = logging.getLogger(__name__)


class MistakeInsightManager:
    """
    Менеджер для работы с ошибками и инсайтами.
    Реализует паттерн Mistake→Insight для самоанализа.
    """
    
    def __init__(self, graphiti_adapter: GraphitiMemoryAdapter):
        self.adapter = graphiti_adapter
        
    async def record_mistake(
        self,
        message_id: str,
        summary: str,
        details: Optional[str] = None,
        error_type: Optional[str] = None,
        severity: int = 5
    ) -> Mistake:
        """
        Записывает ошибку, связанную с сообщением.
        
        Args:
            message_id: ID сообщения, вызвавшего ошибку
            summary: Краткое описание ошибки
            details: Подробности (опционально)
            error_type: Тип ошибки (опционально)
            severity: Серьезность от 1 до 10
            
        Returns:
            Созданный объект Mistake
        """
        mistake = Mistake(
            id=str(uuid.uuid4()),
            summary=summary,
            details=details,
            error_type=error_type,
            severity=severity
        )
        
        # Сохраняем узел Mistake
        await self.adapter.add_node(
            node_type="Mistake",
            properties=mistake.model_dump(exclude_none=True)
        )
        
        # Создаем связь Message->caused_error->Mistake
        caused_error = CausedError(
            message_id=message_id,
            mistake_id=mistake.id
        )
        
        await self.adapter.add_relationship(
            source_id=message_id,
            target_id=mistake.id,
            relationship_type="caused_error",
            properties=caused_error.model_dump(exclude_none=True)
        )
        
        logger.info(f"📝 Записана ошибка: {summary[:50]}... (severity: {severity})")
        return mistake
        
    async def create_insight(
        self,
        mistake_ids: List[str],
        summary: str,
        description: Optional[str] = None,
        confidence: float = 0.8,
        tags: Optional[List[str]] = None
    ) -> Insight:
        """
        Создает инсайт на основе одной или нескольких ошибок.
        
        Args:
            mistake_ids: Список ID ошибок, из которых получен инсайт
            summary: Краткое описание инсайта
            description: Подробное описание
            confidence: Уверенность от 0 до 1
            tags: Теги для категоризации
            
        Returns:
            Созданный объект Insight
        """
        insight = Insight(
            id=str(uuid.uuid4()),
            summary=summary,
            description=description,
            confidence=confidence,
            tags=tags or []
        )
        
        # Сохраняем узел Insight
        await self.adapter.add_node(
            node_type="Insight",
            properties=insight.model_dump(exclude_none=True)
        )
        
        # Создаем связи Mistake->resolved_by->Insight для каждой ошибки
        for mistake_id in mistake_ids:
            resolved_by = ResolvedBy(
                mistake_id=mistake_id,
                insight_id=insight.id,
                effectiveness=confidence  # Используем confidence как effectiveness
            )
            
            await self.adapter.add_relationship(
                source_id=mistake_id,
                target_id=insight.id,
                relationship_type="resolved_by",
                properties=resolved_by.model_dump(exclude_none=True)
            )
        
        logger.info(f"💡 Создан инсайт: {summary[:50]}... (confidence: {confidence})")
        return insight
        
    async def get_recent_mistakes(
        self,
        hours: int = 6,
        min_severity: int = 3,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получает недавние ошибки для анализа.
        
        Args:
            hours: Количество часов назад
            min_severity: Минимальная серьезность
            limit: Максимальное количество результатов
            
        Returns:
            Список ошибок с деталями
        """
        since_timestamp = datetime.now() - timedelta(hours=hours)
        
        # Запрос через Cypher
        query = """
        MATCH (m:Mistake)
        WHERE m.ts >= $since_timestamp AND m.severity >= $min_severity
        OPTIONAL MATCH (msg:Message)-[:caused_error]->(m)
        RETURN m, msg
        ORDER BY m.ts DESC
        LIMIT $limit
        """
        
        params = {
            "since_timestamp": since_timestamp.isoformat(),
            "min_severity": min_severity,
            "limit": limit
        }
        
        result = await self.adapter.query(query, params)
        
        mistakes = []
        for record in result:
            mistake_data = record["m"]
            mistake_data["caused_by_message"] = record.get("msg")
            mistakes.append(mistake_data)
            
        logger.info(f"🔍 Найдено {len(mistakes)} ошибок за последние {hours} часов")
        return mistakes
        
    async def get_unresolved_mistakes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получает ошибки, для которых еще нет инсайтов.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список неразрешенных ошибок
        """
        query = """
        MATCH (m:Mistake)
        WHERE NOT EXISTS ((m)-[:resolved_by]->(:Insight))
        OPTIONAL MATCH (msg:Message)-[:caused_error]->(m)
        RETURN m, msg
        ORDER BY m.severity DESC, m.ts DESC
        LIMIT $limit
        """
        
        result = await self.adapter.query(query, {"limit": limit})
        
        mistakes = []
        for record in result:
            mistake_data = record["m"]
            mistake_data["caused_by_message"] = record.get("msg")
            mistakes.append(mistake_data)
            
        logger.info(f"🔍 Найдено {len(mistakes)} неразрешенных ошибок")
        return mistakes
        
    async def get_insights_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """
        Получает инсайты по тегу.
        
        Args:
            tag: Тег для поиска
            
        Returns:
            Список инсайтов с указанным тегом
        """
        query = """
        MATCH (i:Insight)
        WHERE $tag IN i.tags
        OPTIONAL MATCH (m:Mistake)-[:resolved_by]->(i)
        RETURN i, collect(m) as resolved_mistakes
        ORDER BY i.confidence DESC, i.ts DESC
        """
        
        result = await self.adapter.query(query, {"tag": tag})
        
        insights = []
        for record in result:
            insight_data = record["i"]
            insight_data["resolved_mistakes"] = record["resolved_mistakes"]
            insights.append(insight_data)
            
        logger.info(f"🔍 Найдено {len(insights)} инсайтов с тегом '{tag}'")
        return insights
        
    async def analyze_mistake_patterns(self) -> Dict[str, Any]:
        """
        Анализирует паттерны ошибок для выявления системных проблем.
        
        Returns:
            Словарь с аналитикой по ошибкам
        """
        # Частые типы ошибок
        type_query = """
        MATCH (m:Mistake)
        WHERE m.error_type IS NOT NULL
        RETURN m.error_type as type, 
               count(m) as count,
               avg(m.severity) as avg_severity
        ORDER BY count DESC
        LIMIT 10
        """
        
        # Ошибки по времени
        time_query = """
        MATCH (m:Mistake)
        WHERE m.ts >= datetime() - duration('P7D')
        RETURN date(m.ts) as date, count(m) as count
        ORDER BY date
        """
        
        # Эффективность инсайтов
        effectiveness_query = """
        MATCH (m:Mistake)-[r:resolved_by]->(i:Insight)
        RETURN avg(r.effectiveness) as avg_effectiveness,
               count(DISTINCT i) as total_insights,
               count(DISTINCT m) as resolved_mistakes
        """
        
        type_stats = await self.adapter.query(type_query, {})
        time_stats = await self.adapter.query(time_query, {})
        effectiveness_stats = await self.adapter.query(effectiveness_query, {})
        
        analysis = {
            "mistake_types": type_stats,
            "mistakes_by_date": time_stats,
            "insight_effectiveness": effectiveness_stats[0] if effectiveness_stats else {},
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info("📊 Анализ паттернов ошибок завершен")
        return analysis


# Вспомогательные методы для GraphitiAdapter
async def add_node(adapter: GraphitiMemoryAdapter, node_type: str, properties: dict) -> dict:
    """Добавляет узел в граф (заглушка для будущей реализации)"""
    # TODO: Реализовать через Graphiti API
    logger.warning(f"add_node пока не реализован: {node_type}")
    return {"success": True, "id": properties.get("id")}

async def add_relationship(adapter: GraphitiMemoryAdapter, source_id: str, target_id: str, 
                          relationship_type: str, properties: dict) -> dict:
    """Добавляет связь в граф (заглушка для будущей реализации)"""
    # TODO: Реализовать через Graphiti API
    logger.warning(f"add_relationship пока не реализован: {relationship_type}")
    return {"success": True}

async def query(adapter: GraphitiMemoryAdapter, cypher: str, params: dict) -> list:
    """Выполняет Cypher запрос (заглушка для будущей реализации)"""
    # TODO: Реализовать через Graphiti API
    logger.warning(f"query пока не реализован: {cypher[:50]}...")
    return []

# Временно добавляем методы к адаптеру
GraphitiMemoryAdapter.add_node = add_node
GraphitiMemoryAdapter.add_relationship = add_relationship
GraphitiMemoryAdapter.query = query