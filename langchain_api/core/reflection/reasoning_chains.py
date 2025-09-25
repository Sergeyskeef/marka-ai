"""Core reasoning chain data structures used by the reflection system tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ReasoningStep:
    """Single reasoning step captured inside a reasoning chain."""

    id: str
    content: str
    context: Dict[str, Any]
    timestamp: datetime
    confidence: float
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the step into a JSON serialisable dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningStep":
        """Restore a reasoning step from dictionary data."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp_value = datetime.fromisoformat(timestamp)
        else:
            timestamp_value = timestamp or datetime.utcnow()

        children = data.get("children_ids") or []
        return cls(
            id=data["id"],
            content=data.get("content", ""),
            context=data.get("context", {}),
            timestamp=timestamp_value,
            confidence=float(data.get("confidence", 0.0)),
            parent_id=data.get("parent_id"),
            children_ids=list(children),
            metadata=data.get("metadata"),
        )


class ReasoningChain:
    """Container that groups reasoning steps into a coherent chain."""

    def __init__(self, chain_id: str):
        self.chain_id = chain_id
        self.steps: List[ReasoningStep] = []
        self._step_index: Dict[str, ReasoningStep] = {}
        self.root_step_id: Optional[str] = None

    def add_step(self, step: ReasoningStep) -> None:
        """Add a step to the chain and update hierarchy relationships."""
        if step.id in self._step_index:
            raise ValueError(f"Step with id '{step.id}' already exists in chain '{self.chain_id}'")

        self.steps.append(step)
        self._step_index[step.id] = step

        if step.parent_id:
            parent = self._step_index.get(step.parent_id)
            if parent:
                if step.id not in parent.children_ids:
                    parent.children_ids.append(step.id)
            else:
                # If parent isn't present yet we simply keep the relationship for later linking.
                pass
        elif self.root_step_id is None:
            self.root_step_id = step.id

    def get_step(self, step_id: str) -> Optional[ReasoningStep]:
        """Return step by identifier if present."""
        return self._step_index.get(step_id)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the whole chain."""
        return {
            "chain_id": self.chain_id,
            "root_step_id": self.root_step_id,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningChain":
        chain = cls(data["chain_id"])
        chain.root_step_id = data.get("root_step_id")
        for step_data in data.get("steps", []):
            chain.add_step(ReasoningStep.from_dict(step_data))
        return chain

    def evaluate_logical_consistency(self) -> float:
        """Return average confidence score as a proxy for logical consistency."""
        if not self.steps:
            return 0.0
        total_confidence = sum(step.confidence for step in self.steps)
        return total_confidence / len(self.steps)

    def average_confidence(self) -> float:
        """Return the average confidence of all steps."""
        return self.evaluate_logical_consistency()

    def depth(self) -> int:
        """Calculate depth of the reasoning tree."""
        if not self.steps:
            return 0

        roots = [step for step in self.steps if step.parent_id is None]
        if not roots and self.root_step_id:
            root = self.get_step(self.root_step_id)
            roots = [root] if root else []
        if not roots and self.steps:
            roots = [self.steps[0]]

        def _depth_from(step: ReasoningStep) -> int:
            if not step.children_ids:
                return 1
            children_depths = []
            for child_id in step.children_ids:
                child = self.get_step(child_id)
                if child:
                    children_depths.append(_depth_from(child))
            return 1 + (max(children_depths) if children_depths else 0)

        return max(_depth_from(root) for root in roots)


class ReasoningSystem:
    """System level manager for reasoning chains."""

    def __init__(self) -> None:
        self.chains: Dict[str, ReasoningChain] = {}
        self.current_chain_id: Optional[str] = None

    def create_chain(self, chain_id: str) -> ReasoningChain:
        if chain_id in self.chains:
            raise ValueError(f"Chain '{chain_id}' already exists")
        chain = ReasoningChain(chain_id)
        self.chains[chain_id] = chain
        self.current_chain_id = chain_id
        return chain

    def import_chain(self, chain: ReasoningChain) -> None:
        """Register an externally created chain inside the system."""
        self.chains[chain.chain_id] = chain
        if chain.root_step_id and chain.root_step_id not in {s.id for s in chain.steps}:
            chain.root_step_id = None
        self.current_chain_id = chain.chain_id

    def get_chain(self, chain_id: str) -> Optional[ReasoningChain]:
        return self.chains.get(chain_id)

    def add_step(self, chain_id: str, step: ReasoningStep) -> None:
        chain = self.get_chain(chain_id)
        if chain is None:
            raise KeyError(f"Chain '{chain_id}' not found")
        chain.add_step(step)

    def analyze_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform lightweight analysis of supplied context."""
        text_fragments = [str(value) for value in context.values() if isinstance(value, str)]
        combined_text = " ".join(text_fragments)
        context_size = len(combined_text)
        has_code = bool(context.get("code"))
        has_text = any(key != "code" and isinstance(value, str) and value.strip() for key, value in context.items())
        keywords = []
        if combined_text:
            words = combined_text.lower().split()
            seen = set()
            for word in words:
                if word not in seen:
                    keywords.append(word)
                    seen.add(word)
                if len(keywords) >= 5:
                    break
        return {
            "context_size": context_size,
            "has_code": has_code,
            "has_text": has_text,
            "keywords": keywords,
        }

    def evaluate_chain(self, chain_id: str) -> Dict[str, Any]:
        chain = self.get_chain(chain_id)
        if chain is None:
            raise KeyError(f"Chain '{chain_id}' not found")
        return {
            "logical_consistency": chain.evaluate_logical_consistency(),
            "step_count": len(chain.steps),
            "depth": chain.depth(),
            "average_confidence": chain.average_confidence(),
        }

    def save_chains(self, filepath: str) -> None:
        """Persist chains into JSON file."""
        data = {
            "current_chain_id": self.current_chain_id,
            "chains": {chain_id: chain.to_dict() for chain_id, chain in self.chains.items()},
        }
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @classmethod
    def load_chains(cls, filepath: str) -> "ReasoningSystem":
        path = Path(filepath)
        system = cls()
        if not path.exists():
            return system
        raw_data = json.loads(path.read_text())
        for chain_id, chain_data in raw_data.get("chains", {}).items():
            system.chains[chain_id] = ReasoningChain.from_dict(chain_data)
        system.current_chain_id = raw_data.get("current_chain_id")
        return system


__all__ = [
    "ReasoningChain",
    "ReasoningStep",
    "ReasoningSystem",
]
