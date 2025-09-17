from __future__ import annotations

from typing import Dict, Any
from app.memory.fractal_graph import fractal_graph
from core.memory.graphiti_adapter import graphiti_adapter
from datetime import datetime


async def detect_incident(outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Мини-эвристика: если outcome содержит error/exception/fail — логируем инцидент."""
    try:
        text = (outcome.get("text") or "") + " " + (outcome.get("error") or "")
        lowered = text.lower()
        if any(k in lowered for k in ("error", "exception", "traceback", "fail", "429", "timeout")):
            kind = "runtime_error"
            if "429" in lowered or "rate_limit" in lowered:
                kind = "rate_limit"
            payload = {"kind": kind, "raw": text[:500]}
            # Сохраняем эпизод-инцидент
            await graphiti_adapter.create_episode(text=f"[INCIDENT] {kind}", metadata={
                "type": "Incident",
                "kind": kind,
                "raw": text[:500],
                "ts": int(datetime.now().timestamp())
            })
            return {"kind": kind, "payload": payload}
    except Exception:
        pass
    return {"kind": "NONE", "payload": {}}


async def mine_skill(outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Выделяем простой рецепт: если есть steps в outcome — сохраняем как Skill."""
    try:
        steps = outcome.get("steps") or outcome.get("actions")
        name = outcome.get("skill_name") or (outcome.get("goal") or "generic_step")
        if isinstance(steps, list) and steps:
            recipe = {"steps": steps}
            await fractal_graph.upsert_node(node_id=f"skill:{name}", node_type="Skill", scale="meso", payload={"text": name}, motifs=["mined"], extra={"recipe": recipe})
            return {"name": name, "payload": {"steps": steps}}
    except Exception:
        pass
    return {"name": "generic_step", "payload": {}}


