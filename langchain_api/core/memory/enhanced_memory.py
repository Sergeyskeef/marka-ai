"""In-memory storage used by reflection related tests."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4


class InsightType(Enum):
    """Types of insights stored inside the enhanced memory."""

    EFFICIENCY = "efficiency"
    PATTERN = "pattern"
    OPTIMIZATION = "optimization"
    WARNING = "warning"


@dataclass
class MemoryEntry:
    id: str
    content: Any
    type: str
    meta: Dict[str, Any]
    timestamp: datetime
    importance: float
    context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.type,
            "meta": self.meta,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
            "context": self.context,
        }


class EnhancedMemory:
    """Simple enhanced memory implementation used in unit tests."""

    def __init__(self) -> None:
        self.memories: Dict[str, Dict[str, Any]] = {}
        self.pattern_counter: Counter[str] = Counter()
        self.categories: Dict[str, List[str]] = {}
        self.insights: Dict[str, Dict[str, Any]] = {}
        self.history: Dict[str, List[Dict[str, Any]]] = {
            "memories": [],
            "insights": [],
        }

    # ------------------------------------------------------------------
    # Memory storage helpers
    # ------------------------------------------------------------------
    def insert(self, data: Dict[str, Any]) -> str:
        """Insert data into memory and update bookkeeping structures."""
        entry_id = data.get("id") or str(uuid4())
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp_value = datetime.fromisoformat(timestamp)
        else:
            timestamp_value = timestamp or datetime.utcnow()

        content = data.get("content", "")
        importance = self._calculate_importance(data)
        entry = {
            "id": entry_id,
            "content": content,
            "type": data.get("type", "general"),
            "meta": data.get("meta", {}),
            "timestamp": timestamp_value.isoformat(),
            "importance": importance,
            "context": data.get("context", {}),
            "metadata": data.get("metadata", {}),
            "evaluation": data.get("evaluation"),
        }
        self.memories[entry_id] = entry

        self.categories.setdefault(entry["type"], []).append(entry_id)
        self._update_patterns(content)

        self.history.setdefault("memories", []).append(
            {"id": entry_id, "timestamp": timestamp_value.isoformat(), "type": entry["type"]}
        )

        return entry_id

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        return self.memories.get(memory_id)

    def search(
        self,
        query: Dict[str, Any],
        *,
        include_patterns: bool = False,
        min_importance: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for entry in self.memories.values():
            if min_importance is not None and entry.get("importance", 0.0) < min_importance:
                continue
            if self._matches(entry, query, include_patterns=include_patterns):
                results.append(entry)
        results.sort(key=lambda item: item.get("importance", 0.0), reverse=True)
        return results

    def get_patterns(self) -> Dict[str, int]:
        return dict(self.pattern_counter)

    def get_categories(self) -> Dict[str, List[Dict[str, Any]]]:
        return {category: [self.memories[mid] for mid in ids] for category, ids in self.categories.items()}

    def get_importance_scores(self) -> Dict[str, float]:
        return {entry_id: entry.get("importance", 0.0) for entry_id, entry in self.memories.items()}

    # ------------------------------------------------------------------
    # Insights management
    # ------------------------------------------------------------------
    def add_insight(
        self,
        insight_type: InsightType,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        insight_id = str(uuid4())
        metadata = metadata.copy() if metadata else {}
        timestamp = metadata.get("timestamp")
        if isinstance(timestamp, str):
            created_at = datetime.fromisoformat(timestamp)
        else:
            created_at = datetime.utcnow()
        insight = {
            "id": insight_id,
            "type": insight_type.value,
            "content": content,
            "metadata": metadata,
            "created_at": created_at.isoformat(),
        }
        self.insights[insight_id] = insight

        self.history.setdefault("insights", []).append(
            {
                "id": insight_id,
                "timestamp": created_at.isoformat(),
                "type": insight_type.value,
            }
        )
        return insight_id

    def get_insights(self, insight_type: Optional[InsightType] = None) -> List[Dict[str, Any]]:
        insights = list(self.insights.values())
        if insight_type:
            insights = [insight for insight in insights if insight["type"] == insight_type.value]
        insights.sort(key=lambda insight: insight["created_at"], reverse=True)
        return insights

    # ------------------------------------------------------------------
    # Historical analytics
    # ------------------------------------------------------------------
    def analyze_historical_data(
        self,
        category: str,
        time_window: Optional[timedelta] = None,
    ) -> Dict[str, Any]:
        records = list(self.history.get(category, []))
        if time_window:
            cutoff = datetime.utcnow() - time_window
            records = [r for r in records if self._parse_timestamp(r["timestamp"]) >= cutoff]

        analysis: Dict[str, Any] = {
            "category": category,
            "total_count": len(records),
            "type_distribution": dict(Counter(r.get("type") for r in records)),
            "trends": self._build_trend_series(records),
        }
        return analysis

    def get_historical_summary(self) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        for category, records in self.history.items():
            if not records:
                continue
            timestamps = [self._parse_timestamp(record["timestamp"]) for record in records]
            last_update = max(timestamps)
            summary[category] = {
                "total_count": len(records),
                "last_update": last_update.isoformat(),
                "trend": self._detect_trend(records),
            }
        return summary

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _update_patterns(self, content: Any) -> None:
        if not isinstance(content, str):
            return
        words = re.findall(r"[A-Za-zА-Яа-я0-9]+", content.lower())
        self.pattern_counter.update(words)

    def _calculate_importance(self, data: Dict[str, Any]) -> float:
        score = 0.2
        meta = data.get("meta") or {}
        if meta:
            score += 0.2
        content = data.get("content", "")
        if isinstance(content, str):
            length = len(content)
            score += min(0.4, length / 100)
            if length > 300:
                score += 0.2
            if any(keyword in content.lower() for keyword in ("important", "critical", "optimize")):
                score += 0.1
        return min(score, 1.0)

    def _matches(self, entry: Dict[str, Any], query: Dict[str, Any], *, include_patterns: bool) -> bool:
        for key, expected in query.items():
            actual = entry.get(key)
            if key == "content" and isinstance(expected, str) and isinstance(actual, str):
                if include_patterns:
                    if expected.lower() not in actual.lower():
                        return False
                elif actual != expected:
                    return False
            elif actual != expected:
                return False
        return True

    def _parse_timestamp(self, timestamp: str) -> datetime:
        return datetime.fromisoformat(timestamp)

    def _build_trend_series(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bucket_counter: Counter[str] = Counter()
        for record in records:
            timestamp = record.get("timestamp")
            if not timestamp:
                continue
            dt = self._parse_timestamp(timestamp)
            bucket_counter[dt.date().isoformat()] += 1
        return [
            {"date": date, "count": count}
            for date, count in sorted(bucket_counter.items())
        ]

    def _detect_trend(self, records: Iterable[Dict[str, Any]]) -> str:
        now = datetime.utcnow()
        recent_window = timedelta(hours=24)
        previous_window = now - recent_window
        earlier_window = previous_window - recent_window

        recent = 0
        previous = 0
        for record in records:
            timestamp = record.get("timestamp")
            if not timestamp:
                continue
            dt = self._parse_timestamp(timestamp)
            if dt >= previous_window and dt < now:
                recent += 1
            elif dt >= earlier_window and dt < previous_window:
                previous += 1
        if recent > previous:
            return "increasing"
        if recent < previous:
            return "decreasing"
        return "stable"


__all__ = ["EnhancedMemory", "InsightType"]
