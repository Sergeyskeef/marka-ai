"""Utilities to integrate reasoning and learning systems with memory."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

from core.memory.enhanced_memory import EnhancedMemory

from .reasoning_chains import ReasoningChain, ReasoningSystem
from .self_learning import LearningPattern, SelfLearningSystem


class MemoryIntegration:
    """High level helper that connects memory with reasoning and learning."""

    def __init__(self, memory: EnhancedMemory, learning_system: SelfLearningSystem) -> None:
        self.memory = memory
        self.learning_system = learning_system

    def save_reasoning_chain(self, chain: ReasoningChain) -> str:
        """Persist a reasoning chain in memory and register patterns."""
        self.learning_system.reasoning_system.import_chain(chain)
        self.learning_system.analyze_patterns(chain.chain_id)

        entry: Dict[str, Any] = {
            "id": chain.chain_id,
            "type": "reasoning_chain",
            "content": [step.to_dict() for step in chain.steps],
            "context": self._aggregate_context(chain),
            "evaluation": chain.evaluate_logical_consistency(),
            "metadata": {
                "step_count": len(chain.steps),
                "depth": chain.depth(),
                "average_confidence": chain.average_confidence(),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        return self.memory.insert(entry)

    def get_relevant_memories(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return memories that match provided context with relevance scores."""
        results: List[Dict[str, Any]] = []
        for entry in self.memory.memories.values():
            relevance = self._calculate_relevance(entry, context)
            if relevance <= 0:
                continue
            enriched = dict(entry)
            enriched["relevance"] = relevance
            results.append(enriched)
        results.sort(key=lambda item: item["relevance"], reverse=True)
        return results

    def analyze_historical_experience(self, context: Dict[str, Any]) -> Dict[str, Any]:
        patterns = self.learning_system.get_relevant_patterns(context)
        memories = self.get_relevant_memories(context)

        pattern_payload = [pattern.to_dict() for pattern in patterns]
        reasoning_chains = [memory for memory in memories if memory.get("type") == "reasoning_chain"]

        success_inputs: List[Dict[str, Any]] = [
            {"type": "pattern", "data": pattern}
            for pattern in patterns
        ] + [
            {"type": "memory", "data": memory}
            for memory in reasoning_chains
        ]

        return {
            "successful_patterns": pattern_payload,
            "reasoning_chains": reasoning_chains,
            "total_experience": len(patterns) + len(memories),
            "success_rate": self._calculate_success_rate(success_inputs),
        }

    def _aggregate_context(self, chain: ReasoningChain) -> Dict[str, Any]:
        aggregated: Dict[str, Any] = {}
        for step in chain.steps:
            for key, value in (step.context or {}).items():
                aggregated.setdefault(key, value)
        return aggregated

    def _calculate_relevance(self, memory: Dict[str, Any], context: Dict[str, Any]) -> float:
        score = 0.0
        if not context:
            return score

        memory_type = memory.get("type")
        context_type = context.get("type")
        if memory_type and context_type and memory_type == context_type:
            score += 0.4

        stored_context = memory.get("context")
        if isinstance(stored_context, dict):
            matches = sum(1 for key, value in context.items() if stored_context.get(key) == value)
            if matches:
                score += min(0.4, matches / max(len(context), 1))

        content = memory.get("content")
        if isinstance(content, str) and isinstance(context_type, str) and context_type in content:
            score += 0.2
        elif isinstance(content, list):
            # reasoning chains store a list of steps – check their content for matches
            for step in content:
                step_context = step.get("context", {})
                if any(step_context.get(k) == v for k, v in context.items()):
                    score += 0.2
                    break
        return min(score, 1.0)

    def _calculate_success_rate(self, items: List[Dict[str, Any]]) -> float:
        if not items:
            return 0.0
        scores: List[float] = []
        for item in items:
            if item.get("type") == "pattern":
                data = item.get("data")
                if isinstance(data, LearningPattern):
                    scores.append(max(0.0, min(1.0, data.success_rate)))
                elif isinstance(data, dict):
                    scores.append(max(0.0, min(1.0, float(data.get("success_rate", 0.0)))))
                else:
                    rate = getattr(data, "success_rate", None)
                    if isinstance(rate, (int, float)):
                        scores.append(max(0.0, min(1.0, float(rate))))
            elif item.get("type") == "memory":
                data = item.get("data") or {}
                evaluation = data.get("evaluation")
                if isinstance(evaluation, (int, float)):
                    scores.append(max(0.0, min(1.0, float(evaluation))))
        if not scores:
            return 0.0
        return sum(scores) / len(scores)


__all__ = ["MemoryIntegration"]
