"""Two Gold reports, before and after the shared rule moves to Silver."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .models import CurrentState
from .rules import latest_by_arrival, latest_by_position_first_seen


class SalesBefore:
    """Finance: sales of accepted orders. Picks the current version itself, by arrival."""

    name = "sales"

    def answer(self, source: pd.DataFrame) -> dict[int, int]:
        cur = latest_by_arrival(source)
        cur = cur[cur["status"] == "accepted"]
        return {int(r.order_id): int(r.amount) for r in cur.itertuples()}


class OperationsBefore:
    """Operations: the status of every order. Picks the current version itself, by source position."""

    name = "operations"

    def answer(self, source: pd.DataFrame) -> dict[int, str]:
        cur = latest_by_position_first_seen(source)
        cur = cur[cur["op"] != "delete"]
        return {int(r.order_id): f"{r.status} {int(r.amount)}" for r in cur.itertuples()}


class SalesAfter:
    """Finance, reading Silver's current state. Its own rule stays here: accepted orders only."""

    name = "sales"

    def answer(self, source: CurrentState) -> dict[int, int]:
        return {r["order_id"]: int(r["amount"]) for r in source.orders if r["status"] == "accepted"}


class OperationsAfter:
    """Operations, reading Silver's current state. It shows cancelled orders, so it keeps them."""

    name = "operations"

    def answer(self, source: CurrentState) -> dict[int, str]:
        return {r["order_id"]: f"{r['status']} {int(r['amount'])}" for r in source.orders}


def cancelled_count(answer: Mapping[int, int | str]) -> int:
    """How many orders a report shows as cancelled."""
    return sum(1 for v in answer.values() if str(v).startswith("cancelled"))
