"""Composition root: run the shared-rule example on a local Delta table and print what happened.

Run from the repository root: python -m src.silver_rule_demo
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import deltalake

from .repository import SilverOrderChanges
from .scenario import run_scenario

CODE_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = CODE_ROOT / "data" / "order_changes.json"


def run(root: Path, seed_file: Path = SEED_FILE) -> dict[str, Any]:
    """Wire the local adapter and seed; preserve unrelated files and Delta history."""
    seed_bytes = seed_file.read_bytes()
    seed = json.loads(seed_bytes)
    out = run_scenario(SilverOrderChanges(root), seed)
    out["deltalake"] = deltalake.__version__
    out["lake_path"] = str(root.resolve())
    out["seed_file"] = seed_file.name
    out["seed_sha256"] = hashlib.sha256(seed_bytes).hexdigest()
    manifest = root / "run.json"
    manifest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


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
