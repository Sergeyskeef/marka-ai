from __future__ import annotations
from typing import Any, Dict, List, Optional
import time

_last_xtrace: Dict[str, Any] | None = None


def build_xtrace(*, query: str, filters: Optional[Dict[str, Any]], results: List[Dict[str, Any]], timings: Optional[Dict[str, float]] = None, limits: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    used = []
    cap = (limits or {}).get('top_n_preview', 10)
    for r in results[:cap]:
        preview = (r.get('text') or '')[:160]
        used.append({
            'id': r.get('id'),
            'preview': preview,
            'score': float(r.get('score', 0.0)),
            'source': r.get('source', 'graphiti'),
        })
    fkeys = sorted(list((filters or {}).keys()))
    xt = {
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'summary': f"retrieved {len(results)} items for query='{query[:80]}'",
        'query': query,
        'filter_keys': fkeys,
        'used_memory': used,
        'counts': {
            'returned': len(results),
            'previewed': len(used),
            'truncated': max(0, len(results) - len(used)),
        },
        'timings_ms': {k: round(v * 1000.0, 1) for k, v in (timings or {}).items()},
        'limits': limits or {},
        'schema_version': 1,
    }
    return xt


def set_last_xtrace(x: Dict[str, Any]) -> None:
    global _last_xtrace
    _last_xtrace = x


def get_last_xtrace() -> Dict[str, Any] | None:
    return _last_xtrace
