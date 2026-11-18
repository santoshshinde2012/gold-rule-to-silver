"""Columns and small value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KEY = "order_id"
CHANGE_COLUMNS = ["order_id", "source_seq", "op", "status", "amount", "arrived_at"]


@dataclass(frozen=True)
class CurrentState:
    """The shared Silver promise: one current row per order, and the keys it could not decide."""

    orders: list[dict[str, Any]]
    exceptions: list[int]


@dataclass(frozen=True)
class Change:
    """One entry in the change log: which report, which order, the old answer, the new one, and why."""

    report: str
    order_id: int
    old: int | str | None
    new: int | str | None
    reason: str
