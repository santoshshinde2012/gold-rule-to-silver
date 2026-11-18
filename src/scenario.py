"""The example's orchestration, independent of storage engines and file lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .compare import change_log
from .models import CurrentState
from .protocols import ChangeStore, Report
from .reports import OperationsAfter, OperationsBefore, SalesAfter, SalesBefore, cancelled_count
from .rules import current_state


def run_scenario(store: ChangeStore, seed: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Run the comparison using injected data and a versioned change store."""
    out: dict[str, Any] = {}
    pinned_version = store.replace(seed["first_load"])
    pinned = store.read(pinned_version)

    # 1. The old reports each choose the current version of an order themselves.
    sales_before: Report[pd.DataFrame, int] = SalesBefore()
    operations_before: Report[pd.DataFrame, str] = OperationsBefore()
    sales_old = sales_before.answer(pinned)
    ops_old = operations_before.answer(pinned)
    out["sales_before"], out["operations_before"] = dict(sales_old), dict(ops_old)
    out["order_2_before"] = {"sales": sales_old.get(2), "operations": ops_old.get(2)}
    out["order_4_before"] = {"sales": sales_old.get(4), "operations": ops_old.get(4)}

    # 2. Resolve the shared Silver state once for this snapshot.
    state = current_state(pinned)
    out["current_state"] = {r["order_id"]: f"{r['status']} {int(r['amount'])}" for r in state.orders}
    out["current_state_rows"] = state.orders
    out["exceptions"] = state.exceptions

    # 3. Both new reports consume that same state and retain only their own filters.
    sales_after: Report[CurrentState, int] = SalesAfter()
    operations_after: Report[CurrentState, str] = OperationsAfter()
    sales_new = sales_after.answer(state)
    ops_new = operations_after.answer(state)
    out["sales_after"], out["operations_after"] = dict(sales_new), dict(ops_new)
    out["sales_total"] = {"before": sum(sales_old.values()), "after": sum(sales_new.values())}
    log = change_log(sales_before.name, sales_old, sales_new, state)
    log += change_log(operations_before.name, ops_old, ops_new, state)
    out["change_log"] = [(c.report, c.order_id, c.old, c.new, c.reason) for c in log]

    # 4. Compare with newer data to demonstrate why the migration pins a version.
    latest_version = store.append(seed["later_arrival"])
    latest_state = current_state(store.read(latest_version))
    unpinned = change_log(sales_after.name, sales_old, sales_after.answer(latest_state), latest_state)
    out["unpinned_sales_changes"] = [(c.order_id, c.reason) for c in unpinned]

    # 5. Moving the sales filter into Silver would remove valid operations data.
    filtered = CurrentState(
        orders=[r for r in state.orders if r["status"] == "accepted"],
        exceptions=state.exceptions,
    )
    out["cancelled_in_operations"] = {
        "filter in Gold": cancelled_count(ops_new),
        "filter moved to Silver": cancelled_count(operations_after.answer(filtered)),
    }
    out["versions"] = {"pinned": pinned_version, "latest": latest_version}
    out["seed_counts"] = {name: len(rows) for name, rows in seed.items()}
    return out
