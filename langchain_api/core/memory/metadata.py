from __future__ import annotations
from typing import Any, Dict
import re

SUSPECT_KEYS = re.compile(r'(password|secret|token|api[_-]?key|authorization)', re.I)

REDACTED = '***redacted***'

ALLOWED_SCALARS = (str, int, float, bool)


def normalize_metadata(meta: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not meta:
        return None
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        key = str(k)[:64]
        if SUSPECT_KEYS.search(key):
            out[key] = REDACTED
            continue
        if isinstance(v, ALLOWED_SCALARS) or v is None:
            out[key] = v
        elif isinstance(v, (list, tuple)):
            out[key] = [str(x) if not isinstance(x, ALLOWED_SCALARS) else x for x in v][:50]
        elif isinstance(v, dict):
            out[key] = {str(kk)[:64]: (vv if isinstance(vv, ALLOWED_SCALARS) else str(vv)) for kk, vv in list(v.items())[:50]}
        else:
            out[key] = str(v)[:500]
    return out
