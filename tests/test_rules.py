"""Unit tests for the shared Silver rule and the change log, with no storage."""

from __future__ import annotations

import pandas as pd

from src.compare import change_log
from src.models import CurrentState
from src.rules import current_state


def test_repeat_delivery_collapses_and_delete_removes() -> None:
    rows = [
        {"order_id": 1, "source_seq": 1, "op": "upsert", "status": "accepted", "amount": 5, "arrived_at": "1"},
        {"order_id": 1, "source_seq": 1, "op": "upsert", "status": "accepted", "amount": 5, "arrived_at": "2"},
        {"order_id": 2, "source_seq": 1, "op": "upsert", "status": "accepted", "amount": 7, "arrived_at": "1"},
        {"order_id": 2, "source_seq": 2, "op": "delete", "status": None, "amount": None, "arrived_at": "2"},
    ]
    state = current_state(pd.DataFrame(rows))
    assert [r["order_id"] for r in state.orders] == [1]
    assert state.exceptions == []


def test_late_arrival_does_not_win() -> None:
    rows = [
        {"order_id": 9, "source_seq": 2, "op": "upsert", "status": "cancelled", "amount": 1, "arrived_at": "1"},
        {"order_id": 9, "source_seq": 1, "op": "upsert", "status": "accepted", "amount": 1, "arrived_at": "2"},
    ]
    assert current_state(pd.DataFrame(rows)).orders[0]["status"] == "cancelled"


def test_change_log_reasons_come_from_the_shared_state() -> None:
    state = CurrentState(orders=[{"order_id": 2, "status": "cancelled", "amount": 60}], exceptions=[4])
    log = change_log("sales", {2: 60, 4: 45, 5: 80}, {}, state)
    assert [(c.order_id, c.reason) for c in log] == [
        (2, "cancelled by the source; source order wins over arrival"),
        (4, "conflict at the same source position; held for review"),
        (5, "deleted by the source"),
    ]
