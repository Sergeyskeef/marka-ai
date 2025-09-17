from __future__ import annotations

from typing import Callable, List, NamedTuple


class Rule(NamedTuple):
    pattern: str
    expand: List[str]
    guard: Callable[[dict], bool]


DEFAULT_RULES: List[Rule] = [
    Rule(
        pattern="INDEX_PROJECT",
        expand=["READ_README", "SCAN_REQUIREMENTS", "MAP_MODULES"],
        guard=lambda ctx: True,
    ),
    Rule(
        pattern="RUN_TESTS",
        expand=["ENV_PREP", "PYTEST_SMOKE", "SUMMARIZE_FAILS"],
        guard=lambda ctx: True,
    ),
]

