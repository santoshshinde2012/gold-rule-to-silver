"""Ways of choosing each order's current version. Pure pandas."""

from __future__ import annotations

import pandas as pd

from .models import KEY, CurrentState


def latest_by_arrival(changes: pd.DataFrame) -> pd.DataFrame:
    """The rule copied into the sales report: the change that arrived last wins."""
    return changes.sort_values("arrived_at").groupby(KEY, as_index=False).tail(1).sort_values(KEY)


def latest_by_position_first_seen(changes: pd.DataFrame) -> pd.DataFrame:
    """The rule copied into the operations report: highest source position; on a tie, the first row read."""
    ranked = changes.sort_values(["source_seq"], ascending=False, kind="stable")
    return ranked.groupby(KEY, as_index=False).head(1).sort_values(KEY)


def current_state(changes: pd.DataFrame) -> CurrentState:
    """The shared Silver rule.

    - Exact repeat deliveries collapse to one change.
    - The highest source position wins, whatever the arrival order.
    - A delete removes the order.
    - Two different changes at the same winning position are a conflict: the order is held back and listed.
    """
    distinct = changes.drop_duplicates(subset=["order_id", "source_seq", "op", "status", "amount"])
    top = distinct[distinct["source_seq"] == distinct.groupby(KEY)["source_seq"].transform("max")]
    counts = top.groupby(KEY)["source_seq"].transform("size")
    conflicts = top[counts > 1]
    decided = top[(counts == 1) & (top["op"] != "delete")]
    return CurrentState(
        orders=decided.drop(columns=["arrived_at"]).sort_values(KEY).to_dict("records"),
        exceptions=sorted(int(k) for k in conflicts[KEY].unique()),
    )
