"""Self-learning utilities that build on top of reasoning chains."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .reasoning_chains import ReasoningChain, ReasoningStep, ReasoningSystem


@dataclass
class LearningPattern:
    """Reusable pattern extracted from reasoning steps."""

    id: str
    pattern_type: str
    context: Dict[str, Any]
    confidence: float
    created_at: datetime
    last_used: datetime
    usage_count: int = 0
    success_rate: float = 0.0
    metadata: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "context": self.context,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningPattern":
        created_at = data.get("created_at")
        last_used = data.get("last_used")
        return cls(
            id=data["id"],
            pattern_type=data.get("pattern_type", "general"),
            context=data.get("context", {}),
            confidence=float(data.get("confidence", 0.0)),
            created_at=datetime.fromisoformat(created_at) if isinstance(created_at, str) else created_at,
            last_used=datetime.fromisoformat(last_used) if isinstance(last_used, str) else last_used,
            usage_count=int(data.get("usage_count", 0)),
            success_rate=float(data.get("success_rate", 0.0)),
            metadata=data.get("metadata"),
        )


class SelfLearningSystem:
    """System that keeps track of extracted learning patterns."""

    def __init__(self, reasoning_system: ReasoningSystem) -> None:
        self.reasoning_system = reasoning_system
        self.patterns: Dict[str, LearningPattern] = {}
        self.learning_history: List[Dict[str, Any]] = []

    def analyze_patterns(self, chain_id: str) -> List[LearningPattern]:
        chain = self.reasoning_system.get_chain(chain_id)
        if chain is None:
            return []

        discovered: List[LearningPattern] = []
        for step in chain.steps:
            pattern = self._create_pattern_from_step(chain.chain_id, step)
            self.patterns[pattern.id] = pattern
            discovered.append(pattern)
        return discovered

    def _create_pattern_from_step(self, chain_id: str, step: ReasoningStep) -> LearningPattern:
        pattern_type = self._infer_pattern_type(step.context)
        pattern_id = f"{chain_id}:{step.id}:{pattern_type}"
        now = datetime.utcnow()
        pattern = self.patterns.get(pattern_id)
        if pattern:
            pattern.last_used = now
            pattern.confidence = (pattern.confidence + step.confidence) / 2
            return pattern
        return LearningPattern(
            id=pattern_id,
            pattern_type=pattern_type,
            context=step.context,
            confidence=step.confidence,
            created_at=now,
            last_used=step.timestamp,
        )

    def _infer_pattern_type(self, context: Dict[str, Any]) -> str:
        if not context:
            return "general_pattern"
        if "code" in context:
            return "code_pattern"
        if "text" in context:
            return "text_pattern"
        return f"context_{next(iter(context))}"

    def update_pattern(self, pattern_id: str, success: bool) -> None:
        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return
        previous_usage = pattern.usage_count
        pattern.usage_count += 1
        success_value = 1.0 if success else 0.0
        if pattern.usage_count:
            pattern.success_rate = (
                (pattern.success_rate * previous_usage) + success_value
            ) / pattern.usage_count
        pattern.last_used = datetime.utcnow()

    def get_relevant_patterns(self, context: Dict[str, Any]) -> List[LearningPattern]:
        pattern_type = self._infer_pattern_type(context)
        candidates = [p for p in self.patterns.values() if p.pattern_type == pattern_type]
        if not candidates:
            candidates = list(self.patterns.values())
        candidates.sort(key=lambda p: (p.success_rate, p.confidence, p.last_used), reverse=True)
        return candidates

    def record_learning_event(
        self,
        event_type: str,
        context: Dict[str, Any],
        success: bool,
        patterns_used: Optional[List[str]] = None,
    ) -> None:
        timestamp = datetime.utcnow()
        record = {
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "context": context,
            "success": bool(success),
            "patterns_used": patterns_used or [],
        }
        self.learning_history.append(record)

        for pattern_id in record["patterns_used"]:
            self.update_pattern(pattern_id, success)

    def get_learning_stats(self) -> Dict[str, Any]:
        total_patterns = len(self.patterns)
        total_events = len(self.learning_history)
        average_success = (
            sum(pattern.success_rate for pattern in self.patterns.values()) / total_patterns
            if total_patterns
            else 0.0
        )
        most_used = sorted(
            self.patterns.values(),
            key=lambda pattern: (pattern.usage_count, pattern.success_rate),
            reverse=True,
        )
        return {
            "total_patterns": total_patterns,
            "total_events": total_events,
            "average_success_rate": average_success,
            "most_used_patterns": most_used,
        }

    def save_state(self, filepath: str) -> None:
        data = {
            "patterns": [pattern.to_dict() for pattern in self.patterns.values()],
            "learning_history": list(self.learning_history),
        }
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @classmethod
    def load_state(cls, filepath: str, reasoning_system: ReasoningSystem) -> "SelfLearningSystem":
        path = Path(filepath)
        system = cls(reasoning_system)
        if not path.exists():
            return system
        raw = json.loads(path.read_text())
        for pattern_data in raw.get("patterns", []):
            pattern = LearningPattern.from_dict(pattern_data)
            system.patterns[pattern.id] = pattern
        system.learning_history = list(raw.get("learning_history", []))
        return system


__all__ = ["LearningPattern", "SelfLearningSystem"]
