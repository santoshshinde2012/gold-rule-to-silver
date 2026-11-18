"""The article's example, step by step. Returns every result the article quotes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import deltalake

from .compare import change_log
from .protocols import Report
from .reports import OperationsAfter, OperationsBefore, SalesAfter, SalesBefore, cancelled_count
from .repository import SilverOrderChanges
from .rules import current_state

CODE_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = CODE_ROOT / "data" / "order_changes.json"


def run(root: Path, seed_file: Path = SEED_FILE) -> dict[str, Any]:
    if root.exists():
        shutil.rmtree(root)
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    silver = SilverOrderChanges(root)
    out: dict[str, Any] = {"deltalake": deltalake.__version__}

    v0 = silver.append(seed["first_load"])
    pinned = silver.read(v0)

    # 1. Two Gold reports, each with its own copy of "pick the current version".
    before: list[Report] = [SalesBefore(), OperationsBefore()]
    sales_old, ops_old = (report.answer(pinned) for report in before)
    out["sales_before"], out["operations_before"] = sales_old, ops_old
    out["order_2_before"] = {"sales": sales_old.get(2), "operations": ops_old.get(2)}
    out["order_4_before"] = {"sales": sales_old.get(4), "operations": ops_old.get(4)}

    # 2. The shared Silver rule.
    state = current_state(pinned)
    out["current_state"] = {r["order_id"]: f"{r['status']} {int(r['amount'])}" for r in state.orders}
    out["exceptions"] = state.exceptions

    # 3. Both reports read the shared state. Compare on the same pinned version.
    after: list[Report] = [SalesAfter(), OperationsAfter()]
    sales_new, ops_new = (report.answer(pinned) for report in after)
    out["sales_total"] = {"before": sum(sales_old.values()), "after": sum(sales_new.values())}
    log = change_log("sales", sales_old, sales_new, state) + change_log("operations", ops_old, ops_new, state)
    out["change_log"] = [(c.report, c.order_id, c.old, c.new, c.reason) for c in log]

    # 4. Without pinning: new data arrives between the old run and the new one.
    v1 = silver.append(seed["later_arrival"])
    unpinned = change_log("sales", sales_old, SalesAfter().answer(silver.read(v1)), state)
    out["unpinned_sales_changes"] = [(c.order_id, c.reason) for c in unpinned]

    # 5. Moving the finance filter (accepted only) into Silver would take cancelled orders from operations.
    filtered = [r for r in state.orders if r["status"] == "accepted"]
    ops_if_filter_moved: dict[int, int | str] = {r["order_id"]: f"{r['status']} {int(r['amount'])}" for r in filtered}
    out["cancelled_in_operations"] = {
        "filter in Gold": cancelled_count(ops_new),
        "filter moved to Silver": cancelled_count(ops_if_filter_moved),
    }
    return out
