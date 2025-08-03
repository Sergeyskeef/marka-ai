#!/usr/bin/env python3
"""
Outcome Logger для логирования результатов ToolCall'ов
"""

import time
import logging
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
from contextlib import contextmanager

from ..graphiti_config import get_graphiti_config
from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)


class OutcomeStatus(str, Enum):
    """Статус результата выполнения инструмента"""
    SUCCESS = "success"
    FAIL = "fail"


@dataclass
class ToolCallOutcome:
    """Результат выполнения ToolCall"""
    tool_name: str
    status: OutcomeStatus
    duration_ms: int
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    tool_call_id: Optional[str] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class OutcomeLogger:
    """Логгер результатов выполнения инструментов"""
    
    def __init__(self):
        self.config = get_graphiti_config()
        self._driver: Optional[Driver] = None
        logger.info("📊 OutcomeLogger инициализирован")
    
    @property
    def driver(self) -> Driver:
        """Ленивая инициализация драйвера Neo4j"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_username, self.config.neo4j_password)
            )
        return self._driver
    
    def close(self):
        """Закрытие соединения с Neo4j"""
        if self._driver:
            self._driver.close()
            self._driver = None
    
    @contextmanager
    def measure_execution(self, tool_name: str, tool_call_id: Optional[str] = None):
        """Контекстный менеджер для измерения времени выполнения инструмента"""
        start_time = time.time()
        outcome = None
        error = None
        
        try:
            yield
            outcome = ToolCallOutcome(
                tool_name=tool_name,
                status=OutcomeStatus.SUCCESS,
                duration_ms=int((time.time() - start_time) * 1000),
                tool_call_id=tool_call_id
            )
        except Exception as e:
            error = str(e)
            outcome = ToolCallOutcome(
                tool_name=tool_name,
                status=OutcomeStatus.FAIL,
                duration_ms=int((time.time() - start_time) * 1000),
                error=error,
                tool_call_id=tool_call_id
            )
            raise
        finally:
            if outcome:
                self.log_outcome(outcome)
    
    def log_outcome(self, outcome: ToolCallOutcome):
        """Логирование результата выполнения инструмента в Neo4j"""
        try:
            with self.driver.session() as session:
                query = """
                CREATE (o:Outcome {
                    tool_name: $tool_name,
                    status: $status,
                    duration_ms: $duration_ms,
                    error: $error,
                    details: $details,
                    tool_call_id: $tool_call_id,
                    timestamp: $timestamp,
                    created_at: datetime()
                })
                """
                
                session.run(query, {
                    "tool_name": outcome.tool_name,
                    "status": outcome.status.value,
                    "duration_ms": outcome.duration_ms,
                    "error": outcome.error,
                    "details": outcome.details,
                    "tool_call_id": outcome.tool_call_id,
                    "timestamp": outcome.timestamp
                })
                
                logger.info(f"✅ Outcome logged: {outcome.tool_name} - {outcome.status} ({outcome.duration_ms}ms)")
                
        except Exception as e:
            logger.error(f"❌ Failed to log outcome: {e}")
    
    def log_success(self, tool_name: str, duration_ms: int, details: Optional[Dict[str, Any]] = None, 
                   tool_call_id: Optional[str] = None):
        """Логирование успешного выполнения инструмента"""
        outcome = ToolCallOutcome(
            tool_name=tool_name,
            status=OutcomeStatus.SUCCESS,
            duration_ms=duration_ms,
            details=details,
            tool_call_id=tool_call_id
        )
        self.log_outcome(outcome)
    
    def log_failure(self, tool_name: str, duration_ms: int, error: str, 
                   details: Optional[Dict[str, Any]] = None, tool_call_id: Optional[str] = None):
        """Логирование неудачного выполнения инструмента"""
        outcome = ToolCallOutcome(
            tool_name=tool_name,
            status=OutcomeStatus.FAIL,
            duration_ms=duration_ms,
            error=error,
            details=details,
            tool_call_id=tool_call_id
        )
        self.log_outcome(outcome)
    
    def get_recent_outcomes(self, limit: int = 10) -> list:
        """Получение последних результатов выполнения"""
        try:
            with self.driver.session() as session:
                query = """
                MATCH (o:Outcome)
                RETURN o
                ORDER BY o.timestamp DESC
                LIMIT $limit
                """
                result = session.run(query, {"limit": limit})
                return [record["o"] for record in result]
        except Exception as e:
            logger.error(f"❌ Failed to get recent outcomes: {e}")
            return []
    
    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
        """Получение статистики по инструменту"""
        try:
            with self.driver.session() as session:
                query = """
                MATCH (o:Outcome {tool_name: $tool_name})
                WITH o
                RETURN 
                    count(o) as total_calls,
                    sum(CASE WHEN o.status = 'success' THEN 1 ELSE 0 END) as success_count,
                    sum(CASE WHEN o.status = 'fail' THEN 1 ELSE 0 END) as fail_count,
                    avg(o.duration_ms) as avg_duration_ms,
                    min(o.duration_ms) as min_duration_ms,
                    max(o.duration_ms) as max_duration_ms
                """
                result = session.run(query, {"tool_name": tool_name})
                record = result.single()
                
                if record:
                    total = record["total_calls"]
                    success = record["success_count"]
                    
                    return {
                        "tool_name": tool_name,
                        "total_calls": total,
                        "success_count": success,
                        "fail_count": record["fail_count"],
                        "success_rate": success / total if total > 0 else 0.0,
                        "avg_duration_ms": record["avg_duration_ms"],
                        "min_duration_ms": record["min_duration_ms"],
                        "max_duration_ms": record["max_duration_ms"]
                    }
                else:
                    return {"tool_name": tool_name, "total_calls": 0}
                    
        except Exception as e:
            logger.error(f"❌ Failed to get tool stats: {e}")
            return {"tool_name": tool_name, "error": str(e)}


# Глобальный экземпляр логгера
outcome_logger = OutcomeLogger()