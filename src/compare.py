"""Compare a report's old and new answers, key by key, and give each change a reason.

The reasons come from the shared Silver state, not from the report: the report owner
should still check each one against a few real orders before signing off.
"""

from __future__ import annotations

from collections.abc import Mapping

from .models import Change, CurrentState

Answer = Mapping[int, int | str]


def explain(order_id: int, old: int | str | None, new: int | str | None, state: CurrentState) -> str:
    """Why one order's answer changed, judged from the shared current state."""
    if order_id in state.exceptions:
        return "conflict at the same source position; held for review"
    if old is None:
        return "new in Silver"
    current = {r["order_id"]: r["status"] for r in state.orders}
    if new is None and current.get(order_id) == "cancelled":
        return "cancelled by the source; source order wins over arrival"
    if new is None and order_id not in current:
        return "deleted by the source"
    return "a different version wins by source order"


def change_log(report: str, old: Answer, new: Answer, state: CurrentState) -> list[Change]:
    """Every order whose answer differs between the old and the new report, with a reason."""
    return [
        Change(report, k, old.get(k), new.get(k), explain(k, old.get(k), new.get(k), state))
        for k in sorted(set(old) | set(new))
        if old.get(k) != new.get(k)
    ]
