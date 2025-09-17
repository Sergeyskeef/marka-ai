from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Budget:
    tokens: int
    time_ms: int
    tool_calls: int

    def exhausted(self) -> bool:
        return self.tokens <= 0 or self.tool_calls <= 0

    def split(self, n: int) -> "Budget":
        n = max(1, n)
        return Budget(tokens=max(1, self.tokens // n), time_ms=max(1, self.time_ms // n), tool_calls=max(1, self.tool_calls // n))

