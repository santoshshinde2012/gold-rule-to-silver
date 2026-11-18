"""Composition root: run the shared-rule example on a local Delta table and print what happened.

Run from the `code/` folder:  python -m src.silver_rule_demo
"""

from __future__ import annotations

from typing import Any

from .scenario import CODE_ROOT, run


def report(out: dict[str, Any]) -> list[str]:
    """The lines the article quotes, in order."""
    lines = [
        f"deltalake {out['deltalake']} on local disk; not a Databricks runtime",
        f"1. Before. Order 2: {out['order_2_before']}. Order 4: {out['order_4_before']}",
        f"2. Shared Silver current state: {out['current_state']}; held for review: {out['exceptions']}",
        f"3. Sales total before {out['sales_total']['before']}, after {out['sales_total']['after']}. Change log:",
    ]
    lines += [f"   {row}" for row in out["change_log"]]
    lines += [
        f"4. Compared without pinning, sales changes: {out['unpinned_sales_changes']}",
        f"5. Cancelled orders in operations: {out['cancelled_in_operations']}",
    ]
    return lines


def main() -> None:
    for line in report(run(CODE_ROOT / "lake")):
        print(line)


if __name__ == "__main__":
    main()
