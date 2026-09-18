"""Constraint awareness — track uniqueness and reject invalid candidate rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConstraintTracker:
    """Per-table uniqueness ledger used while generating."""

    seen: dict[tuple[str, ...], set[tuple[Any, ...]]] = field(default_factory=dict)

    def register_keys(self, keys: list[tuple[str, ...]]) -> None:
        for key in keys:
            self.seen.setdefault(key, set())

    def accepts(self, key: tuple[str, ...], values: tuple[Any, ...]) -> bool:
        # NULL participates specially in SQL UNIQUE; treat None as always ok for uniqueness
        if any(v is None for v in values):
            return True
        return values not in self.seen.get(key, set())

    def record(self, key: tuple[str, ...], values: tuple[Any, ...]) -> None:
        if any(v is None for v in values):
            return
        self.seen.setdefault(key, set()).add(values)

    def row_ok(self, unique_keys: list[tuple[str, ...]], row: dict[str, Any]) -> bool:
        for key in unique_keys:
            values = tuple(row.get(c) for c in key)
            if not self.accepts(key, values):
                return False
        return True

    def commit_row(self, unique_keys: list[tuple[str, ...]], row: dict[str, Any]) -> None:
        for key in unique_keys:
            self.record(key, tuple(row.get(c) for c in key))


def clamp_numeric(
    value: float,
    bounds: tuple[float | None, float | None] | None,
) -> float:
    if bounds is None:
        return value
    lo, hi = bounds
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value
