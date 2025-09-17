from __future__ import annotations

from typing import List, Dict, Any

from .rules import DEFAULT_RULES
from .budget import Budget
from app.memory.fractal_graph import fractal_graph


def expand(goal: str, context: Dict[str, Any]) -> List[str]:
    """Эвристика декомпозиции: сперва правила, затем простая сегментация."""
    for r in DEFAULT_RULES:
        if r.pattern == goal and r.guard(context):
            return list(r.expand)
    g = (goal or "").strip()
    if not g:
        return []
    for sep in [";", "\n", " и ", " then ", " -> "]:
        if sep in g:
            parts = [p.strip() for p in g.split(sep) if p.strip()]
            if len(parts) > 1:
                return parts
    return [g]


async def fractal_solve(goal: str, scale: str, budget: Budget, context: Dict[str, Any]) -> Dict[str, Any]:
    """Мини-каркас: планируем, спускаемся по масштабам и возвращаем сводку."""
    if budget.exhausted() or scale == "micro":
        # atomic step — ищем контекст и возвращаем заготовку
        ctx = await fractal_graph.retrieve_context(query=goal, scale="auto", k=6)
        return {"goal": goal, "scale": scale, "used": 1, "context": ctx}

    tasks = expand(goal, context) or [goal]
    parts: List[Dict] = []
    for t in tasks:
        child = await fractal_solve(t, next_scale(scale), budget.split(len(tasks)), context)
        parts.append(child)
    return {"goal": goal, "scale": scale, "parts": parts}


def next_scale(scale: str) -> str:
    order = ["macro", "meso", "micro"]
    try:
        idx = order.index(scale)
    except ValueError:
        return "meso"
    return order[min(len(order) - 1, idx + 1)]


